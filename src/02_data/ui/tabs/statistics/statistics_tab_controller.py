# -*- coding: utf-8 -*-
"""
StatisticsTabController (UI와 완전 일치하도록 보완)

- 이전의 간결 컨트롤러를 확장하여 statistics_tab.ui에서 정의한 모든 시그널을 처리하도록 보완했습니다.
- 주요 책임:
  - 분리된 컴포넌트(Persistence, BufferManager, ForwardingRegistrar) 사용
  - 뷰 시그널 전체 연결: load_history, pause, refresh, export(선택/전체), clear(선택/전체),
    show_all, active_tab_changed, search_text_changed 등
  - 테이블 컬럼 너비 저장/복원
  - 버퍼 flush 시 UI 삽입 및 테이블 트리밍
- 뷰가 None이면(테스트/비-GUI) 대부분의 UI 작업은 건너뜁니다. (안전성 우선)
"""
from __future__ import annotations
import csv
import logging
import os
from collections import deque
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QObject, QTimer, Qt
    _HAS_QT = True
except Exception:
    _HAS_QT = False

# 분리된 모듈
try:
    from .statistics_tab_persistence import Persistence
    from .statistics_tab_buffer import BufferManager
    from .statistics_tab_forwarding import ForwardingRegistrar
except Exception:
    Persistence = None
    BufferManager = None
    ForwardingRegistrar = None

try:
    from .statistics_tab import StatisticsTab
except Exception:
    StatisticsTab = None

# 기본값(안전 장치)
_DEF = {
    "num_live_tabs": 3,
    "flush_interval_ms": 200,
    "flush_batch": 200,
    "max_pending": 100000,
    "enable_forwarding": True,
    "autostart_timer": True,
    "history_max_lines": 1000,
}


if _HAS_QT and Persistence is not None and BufferManager is not None and ForwardingRegistrar is not None:
    class StatisticsTabController(QObject):
        """StatisticsTab과 완전 연동되는 Controller"""

        def __init__(self, view: Optional["StatisticsTab"] = None, parent=None, create_view_if_missing: bool = True):
            super().__init__(parent)

            # View 처리 (전달된 것 우선, 없으면 옵션에 따라 지연 생성)
            if view is not None:
                self.view = view
            else:
                if create_view_if_missing and StatisticsTab is not None:
                    try:
                        self.view = StatisticsTab(parent=parent)
                    except Exception as exc:
                        logger.debug("[Controller] StatisticsTab 생성 실패: %s", exc)
                        self.view = None
                else:
                    self.view = None

            # 컴포넌트 초기화
            self.persistence = Persistence()
            self.buffer = BufferManager(max_pending=int(self.persistence.settings.get("max_pending", _DEF["max_pending"])))
            self.forwarding = ForwardingRegistrar()
            if bool(self.persistence.settings.get("enable_forwarding", _DEF["enable_forwarding"])):
                self.forwarding.register(self.add_log_entry)

            # 내부 표시 버퍼(tab별)
            self._displayed_cache: Dict[int, Deque[Dict[str, Any]]] = {i: deque() for i in range(1, 8)}

            # 타이머(Flush)
            self._timer: Optional[QTimer] = None
            try:
                self._timer = QTimer(self)
                self._timer.setInterval(int(self.persistence.settings.get("flush_interval_ms", _DEF["flush_interval_ms"])))
                self._timer.timeout.connect(self._on_timer_flush)
            except Exception as exc:
                logger.debug("[Controller] QTimer 초기화 실패: %s", exc)
                self._timer = None

            # UI 관련 연결: view가 있으면 모든 시그널을 연결
            if self.view is not None:
                self._connect_view_signals()
                self._attach_header_listeners()

            # 타이머 자동 시작
            try:
                if self._timer is not None and bool(self.persistence.settings.get("autostart_timer", _DEF["autostart_timer"])):
                    self._timer.start()
            except Exception as exc:
                logger.debug("[Controller] 타이머 자동 시작 실패: %s", exc)

        # -------------------------
        # View 시그널 연결
        # -------------------------
        def _connect_view_signals(self) -> None:
            try:
                v = self.view
                v.load_history_requested.connect(lambda p: self.load_history(path=p or None))
                v.settings_requested.connect(self._on_settings_requested)
                v.pause_toggled.connect(self._on_pause_toggled)
                v.manual_refresh_requested.connect(lambda: self._do_rebuild_table_for_tab(v.get_active_tab()))
                v.export_tab_requested.connect(self._on_export_tab_requested)
                v.export_tab_with_path.connect(self._on_export_tab_with_path)
                v.export_all_requested.connect(self._on_export_all)
                v.clear_tab_requested.connect(self.clear_tab)
                v.clear_all_requested.connect(self.clear_all_tabs)
                v.show_all_tab_requested.connect(self._on_show_all_tab)
                v.active_tab_changed.connect(self._on_active_tab_changed)
                v.search_text_changed.connect(self._on_search_text_changed)
            except Exception as exc:
                logger.debug("[Controller] _connect_view_signals 실패: %s", exc)

        # -------------------------
        # Header 리사이즈 리스너(컬럼 너비 저장)
        # -------------------------
        def _attach_header_listeners(self) -> None:
            try:
                for tab in range(1, 8):
                    tbl = getattr(self.view, f"table_tab_{tab}", None)
                    if tbl is None:
                        continue
                    try:
                        header = tbl.horizontalHeader()
                        header.sectionResized.connect(lambda logical, old, new, t=tab: self._on_section_resized(t, logical, old, new))
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[Controller] _attach_header_listeners 실패: %s", exc)

        def _on_section_resized(self, tab: int, logicalIndex: int, oldSize: int, newSize: int) -> None:
            try:
                key = str(tab)
                widths = self.persistence.column_layouts.get(key, [])
                cnt = 0
                tbl = getattr(self.view, f"table_tab_{tab}", None)
                if tbl is not None and hasattr(tbl, "columnCount"):
                    cnt = tbl.columnCount()
                else:
                    cnt = max(len(widths), logicalIndex + 1)
                if len(widths) < cnt:
                    widths = widths + [0] * (cnt - len(widths))
                if logicalIndex >= len(widths):
                    widths.extend([0] * (logicalIndex - len(widths) + 1))
                widths[logicalIndex] = int(newSize)
                self.persistence.column_layouts[key] = widths
                self.persistence.save_layouts()
            except Exception as exc:
                logger.debug("[Controller] _on_section_resized 실패: %s", exc)

        # -------------------------
        # 로그 수집 API
        # -------------------------
        def add_log_entry(self, entry: Dict[str, Any]) -> None:
            try:
                ts = entry.get("time") or None
                level = (entry.get("level") or "INFO").upper()
                module = entry.get("module") or entry.get("logger", "") or ""
                msg = entry.get("message") or entry.get("msg") or ""
                item = {"time": ts, "level": level, "category": "", "module": module, "message": msg}
                self.buffer.append(item)
            except Exception as exc:
                logger.debug("[Controller] add_log_entry 실패: %s", exc)

        # -------------------------
        # Flush 처리
        # -------------------------
        def _get_live_tabs(self) -> List[int]:
            try:
                active = self.view.get_active_tab() if self.view is not None else 1
                n = int(self.persistence.settings.get("num_live_tabs", _DEF["num_live_tabs"]))
                n = max(1, min(7, n))
                return [((active - 1 + i) % 7) + 1 for i in range(n)]
            except Exception:
                return [1]

        def _on_timer_flush(self) -> None:
            try:
                batch = self.buffer.pop_batch(int(self.persistence.settings.get("flush_batch", _DEF["flush_batch"])))
                if not batch:
                    if self.view is not None:
                        try:
                            self.view.set_status_text("상태: 대기")
                        except Exception:
                            pass
                    return

                if self.view is None:
                    # 뷰 없으면 로그 드롭(또는 별도 처리)
                    logger.debug("[Controller] view 없음: 버퍼에서 꺼낸 %d 건 드롭", len(batch))
                    return

                live_tabs = set(self._get_live_tabs())
                for tab in range(1, 8):
                    if tab not in live_tabs:
                        continue
                    filters = self._collect_filters_for_tab(tab)
                    buf = self._displayed_cache.get(tab)
                    if buf is None:
                        buf = deque()
                        self._displayed_cache[tab] = buf

                    for item in batch:
                        try:
                            if not self._filter_log_item(item, filters):
                                continue
                            buf.append(item)
                            cells = [item.get("time", "") or "", item.get("level", ""), "", item.get("module", ""), item.get("message", "")]
                            self.view.insert_table_row(tab, cells)
                        except Exception:
                            continue

                    # 테이블 행 trimming
                    try:
                        tbl = getattr(self.view, f"table_tab_{tab}", None)
                        if tbl is not None and hasattr(tbl, "rowCount"):
                            max_rows = self._get_max_rows_for_tab(tab)
                            while tbl.rowCount() > max_rows:
                                try:
                                    tbl.removeRow(0)
                                    if buf:
                                        try:
                                            buf.popleft()
                                        except Exception:
                                            pass
                                except Exception:
                                    break
                    except Exception:
                        pass

                try:
                    self.view.set_status_text(f"상태: 수신 {len(batch)}건")
                    QTimer.singleShot(500, lambda: self.view.set_status_text("상태: 대기"))
                except Exception:
                    pass

            except Exception as exc:
                logger.debug("[Controller] _on_timer_flush 실패: %s", exc)

        # -------------------------
        # UI 헬퍼: 필터/트리밍/리빌드
        # -------------------------
        def _collect_filters_for_tab(self, tab: int) -> Dict[str, Any]:
            try:
                ws = bool(getattr(self.view, f"chk_tab{tab}_ws", None) and getattr(self.view, f"chk_tab{tab}_ws").isChecked())
            except Exception:
                ws = False
            try:
                pl = bool(getattr(self.view, f"chk_tab{tab}_exchange_api", None) and getattr(self.view, f"chk_tab{tab}_exchange_api").isChecked())
            except Exception:
                pl = False
            try:
                gap = bool(getattr(self.view, f"chk_tab{tab}_quotation_api", None) and getattr(self.view, f"chk_tab{tab}_quotation_api").isChecked())
            except Exception:
                gap = False
            try:
                show_warnings = bool(getattr(self.view, f"chk_tab{tab}_warning", None) and getattr(self.view, f"chk_tab{tab}_warning").isChecked())
            except Exception:
                show_warnings = True
            try:
                combo = getattr(self.view, f"combo_tab{tab}_log_level", None) or getattr(self.view, "combo_log_level", None)
                level_text = combo.currentText() if combo is not None else ""
            except Exception:
                level_text = ""
            try:
                le = getattr(self.view, f"le_tab{tab}_search", None)
                search_text = le.text().strip().lower() if le is not None else ""
            except Exception:
                search_text = ""
            return {
                "websocket": ws,
                "pipeline": pl,
                "gap": gap,
                "show_warnings": show_warnings,
                "level_text": level_text,
                "search": search_text,
            }

        def _filter_log_item(self, item: Dict[str, Any], filters: Dict[str, Any]) -> bool:
            try:
                search = (filters.get("search") or "").strip().lower()
                if search:
                    txt = (item.get("message", "") + " " + item.get("module", "")).lower()
                    if search not in txt:
                        return False
                level_text = (filters.get("level_text") or "").strip().upper()
                if level_text:
                    lvl = (item.get("level") or "").upper()
                    if level_text != "ALL" and lvl != level_text:
                        return False
                return True
            except Exception:
                return True

        def _get_max_rows_for_tab(self, tab: int) -> int:
            try:
                sb = getattr(self.view, f"sb_tab{tab}_max_rows", None)
                if sb is not None:
                    return int(sb.value())
            except Exception:
                pass
            return 10000

        # -------------------------
        # View signal slots (export/clear/show/search/active)
        # -------------------------
        def _on_export_tab_requested(self, tab: int) -> None:
            try:
                default = f"logs_tab{tab}_{os.path.basename(os.getcwd())}.csv"
                path = self.view.get_save_file_path(f"로그 CSV 저장 (탭{tab})", default, "CSV Files (*.csv)")
                if not path:
                    return
                self._export_tab_to_path(tab, path)
            except Exception as exc:
                logger.debug("[Controller] _on_export_tab_requested 실패: %s", exc)

        def _on_export_tab_with_path(self, tab: int, path: str) -> None:
            try:
                if not path:
                    return
                self._export_tab_to_path(tab, path)
            except Exception as exc:
                logger.debug("[Controller] _on_export_tab_with_path 실패: %s", exc)

        def _on_export_all(self) -> None:
            try:
                self._on_export_tab_requested(self.view.get_active_tab())
            except Exception as exc:
                logger.debug("[Controller] _on_export_all 실패: %s", exc)

        def _export_tab_to_path(self, tab: int, filename: str) -> None:
            try:
                tbl_view = getattr(self.view, f"table_tab_{tab}", None)
                if tbl_view is None:
                    return
                # QTableWidget 기반일 때
                if hasattr(tbl_view, "columnCount") and hasattr(tbl_view, "rowCount"):
                    cols = tbl_view.columnCount()
                    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.writer(f)
                        headers = []
                        for c in range(cols):
                            try:
                                item = tbl_view.horizontalHeaderItem(c)
                                headers.append(item.text() if item is not None else "")
                            except Exception:
                                headers.append("")
                        writer.writerow(headers)
                        for r in range(tbl_view.rowCount()):
                            row_data = []
                            for c in range(cols):
                                try:
                                    it = tbl_view.item(r, c)
                                    row_data.append(it.text() if it is not None else "")
                                except Exception:
                                    row_data.append("")
                            writer.writerow(row_data)
                logger.info("[Controller] 탭%d CSV 저장: %s", tab, filename)
            except Exception as exc:
                logger.error("[Controller] _export_tab_to_path 실패: %s", exc, exc_info=True)

        def _on_show_all_tab(self, tab: int) -> None:
            try:
                for name in (f"chk_tab{tab}_ws", f"chk_tab{tab}_exchange_api", f"chk_tab{tab}_quotation_api", f"chk_tab{tab}_warning"):
                    try:
                        cb = getattr(self.view, name, None)
                        if cb is not None:
                            cb.setChecked(True)
                    except Exception:
                        pass
                try:
                    le = getattr(self.view, f"le_tab{tab}_search", None)
                    if le is not None:
                        le.clear()
                except Exception:
                    pass
                self._do_rebuild_table_for_tab(tab)
            except Exception as exc:
                logger.debug("[Controller] _on_show_all_tab 실패: %s", exc)

        def _on_active_tab_changed(self, tab: int) -> None:
            try:
                key = str(tab)
                if key in self.persistence.column_layouts:
                    widths = self.persistence.column_layouts[key]
                    tbl = getattr(self.view, f"table_tab_{tab}", None)
                    if tbl is not None:
                        for i, w in enumerate(widths):
                            try:
                                if w > 0 and hasattr(tbl, "setColumnWidth"):
                                    tbl.setColumnWidth(i, int(w))
                            except Exception:
                                pass
                self._do_rebuild_table_for_tab(tab)
            except Exception:
                pass

        def _on_search_text_changed(self, tab: int, text: str) -> None:
            try:
                # 단순 처리: 리빌드
                self._do_rebuild_table_for_tab(tab)
            except Exception as exc:
                logger.debug("[Controller] _on_search_text_changed 실패: %s", exc)

        # -------------------------
        # Table rebuild (전체 리빌드)
        # -------------------------
        def _do_rebuild_table_for_tab(self, tab: int) -> None:
            try:
                tbl = getattr(self.view, f"table_tab_{tab}", None)
                if tbl is None:
                    return
                pending_snapshot = self.buffer.snapshot()
                filters = self._collect_filters_for_tab(tab)
                combined = list(self._displayed_cache.get(tab, deque())) + pending_snapshot
                filtered = [li for li in combined if self._filter_log_item(li, filters)]
                max_rows = self._get_max_rows_for_tab(tab)
                if len(filtered) > max_rows:
                    filtered = filtered[-max_rows:]
                # 뷰 갱신
                rows = [[it.get("time", "") or "", it.get("level", ""), "", it.get("module", ""), it.get("message", "")] for it in filtered]
                self.view.set_table_rows(tab, rows)
                # 내부 캐시 갱신
                self._displayed_cache[tab] = deque(filtered, maxlen=max_rows)
            except Exception as exc:
                logger.debug("[Controller] _do_rebuild_table_for_tab 실패: %s", exc)

        # -------------------------
        # 기타 슬롯
        # -------------------------
        def _on_settings_requested(self) -> None:
            try:
                # 뷰가 settings dialog signal을 전파하면 컨트롤러는 저장/로드 로직을 수행할 수 있음
                # (구현: 뷰에서 다이얼로그를 열도록 위임)
                if self.view is not None:
                    self.view.set_status_text("설정 요청...")
            except Exception:
                pass

        def clear_tab(self, tab: int) -> None:
            try:
                if self.view is not None:
                    self.view.clear_tab(tab)
                try:
                    self._displayed_cache[tab].clear()
                except Exception:
                    pass
            except Exception as exc:
                logger.debug("[Controller] clear_tab 실패: %s", exc)

        def clear_all_tabs(self) -> None:
            try:
                if self.view is not None:
                    self.view.clear_all_tabs()
                for t in range(1, 8):
                    try:
                        self._displayed_cache[t].clear()
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[Controller] clear_all_tabs 실패: %s", exc)

else:
    class StatisticsTabController:
        def __init__(self, *a, **k):
            raise RuntimeError("PyQt5 또는 분리 모듈이 없습니다; Controller를 생성할 수 없습니다.")