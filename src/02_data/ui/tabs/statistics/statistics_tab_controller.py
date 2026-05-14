# -*- coding: utf-8 -*-
"""
statistics_tab_controller.py

Controller for StatisticsTab View.
- Controller owns the business logic: timer, pending log buffering, persistence (settings/layout),
  log forwarding handler registration, model/proxy wiring (if statistics_model available),
  and file I/O for history/export.

한글 주석: 이 파일은 Controller 역할만 합니다. View(StatisticsTab)는 시그널만 발생시키고,
Controller가 모든 로직을 수행합니다.
"""
from __future__ import annotations
import csv
import json
import logging
import os
import threading
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

# PyQt imports
try:
    from PyQt5.QtCore import QObject, QTimer, Qt
    from PyQt5.QtWidgets import QTableView, QHeaderView
    _HAS_QT = True
except Exception:
    _HAS_QT = False

# Local imports (View + Model)
try:
    from .statistics_tab import StatisticsTab
except Exception:
    StatisticsTab = None

try:
    from .statistics_model import StatisticsModel, LogFilterProxyModel
except Exception:
    StatisticsModel = None
    LogFilterProxyModel = None

# Settings / layout persistence (같은 위치 및 기본 파일명 사용)
_LAYOUT_DIR = os.path.join(os.path.expanduser("~"), ".upbit_trader")
_LAYOUT_FILE = os.path.join(_LAYOUT_DIR, "statistics_tab_layout.json")
_SETTINGS_FILE = os.path.join(_LAYOUT_DIR, "statistics_tab_settings.json")

# 기본값 (원본과 동일한 키 사용)
_DEF = {
    "num_live_tabs": 3,
    "flush_interval_ms": 200,
    "flush_batch": 200,
    "max_pending": 100000,
    "enable_forwarding": True,
    "autostart_timer": True,
    "auto_load_history_on_start": False,
    "history_max_lines": 1000,
}


if _HAS_QT and StatisticsTab is not None:
    class StatisticsTabController(QObject):
        """StatisticsTab의 Controller.

        책임:
        - view 인스턴스 생성·소유
        - view.signals -> controller.slots 연결
        - 로그 수집(버퍼) 및 주기적 flush
        - persistence(settings/layout) 관리
        - 로그 포워딩(handler) 등록
        - 모델/프록시(StatisticsModel) 연결(가능한 경우)
        """

        def __init__(self, view: Optional[StatisticsTab] = None, parent=None):
            super().__init__(parent)
            # view 소유
            self.view = view or StatisticsTab(parent=parent)

            # 설정
            self._settings: Dict[str, Any] = dict(_DEF)
            self._load_settings_file_or_defaults()

            # 내부 버퍼 및 락
            self._pending_logs: Deque[Dict[str, Any]] = deque()
            self._pending_lock = threading.Lock()

            # 표시 버퍼(탭별)
            self._displayed_logs_by_tab: Dict[int, Deque] = {i: deque() for i in range(1, 8)}

            # 모델/프록시 캐시
            self._models: Dict[int, Optional[StatisticsModel]] = {}
            self._proxies: Dict[int, Optional[LogFilterProxyModel]] = {}
            self._views: Dict[int, Optional[object]] = {}  # QTableWidget 또는 QTableView

            # 컬럼 레이아웃
            self._column_layouts: Dict[str, List[int]] = {}
            self._load_column_layouts()

            # 타이머
            self._timer = QTimer(self)
            self._timer.setInterval(int(self._settings.get("flush_interval_ms", _DEF["flush_interval_ms"])))
            self._timer.timeout.connect(self._on_timer_flush)

            # logging forwarding handler
            self._forwarding_handler = None

            # view 시그널 연결
            self._connect_view_signals()

            # 테이블 헤더 이벤트 연결(컬럼 너비 저장)
            self._attach_header_listeners()

            # 자동 타이머 시작
            try:
                if bool(self._settings.get("autostart_timer", _DEF["autostart_timer"])) and not self._timer.isActive():
                    self._timer.start()
                    logger.info("[StatisticsTabController] 타이머 자동 시작")
            except Exception:
                pass

            # 포워딩 핸들러 등록
            try:
                if bool(self._settings.get("enable_forwarding", _DEF["enable_forwarding"])):
                    self._register_forwarding_handler()
            except Exception as exc:
                logger.debug("[StatisticsTabController] forwarding setup 실패: %s", exc)

        # -------------------------
        # View 연결
        # -------------------------
        def _connect_view_signals(self) -> None:
            try:
                v = self.view
                v.load_history_requested.connect(self._on_load_history_requested)
                v.pause_toggled.connect(self._on_pause_toggled)
                v.manual_refresh_requested.connect(self._on_manual_refresh)
                v.export_tab_requested.connect(self._on_export_tab_requested)
                v.export_tab_with_path.connect(self._on_export_tab_with_path)
                v.export_all_requested.connect(self._on_export_all)
                v.clear_tab_requested.connect(self.clear_tab)
                v.clear_all_requested.connect(self.clear_all_tabs)
                v.show_all_tab_requested.connect(self._on_show_all_tab)
                v.active_tab_changed.connect(self._on_active_tab_changed)
                v.search_text_changed.connect(self._on_search_text_changed)
            except Exception:
                pass

        # -------------------------
        # Settings / Layout persistence
        # -------------------------
        def _load_settings_file_or_defaults(self) -> None:
            self._settings = dict(_DEF)
            try:
                if os.path.exists(_SETTINGS_FILE):
                    with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        self._settings.update(data)
            except Exception as exc:
                logger.debug("[StatisticsTabController] _load_settings_file_or_defaults 실패: %s", exc)

        def _save_settings_file(self) -> None:
            try:
                if not os.path.isdir(_LAYOUT_DIR):
                    os.makedirs(_LAYOUT_DIR, exist_ok=True)
                with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._settings, f, ensure_ascii=False, indent=2)
            except Exception as exc:
                logger.debug("[StatisticsTabController] _save_settings_file 실패: %s", exc)

        def _load_column_layouts(self) -> None:
            try:
                if os.path.exists(_LAYOUT_FILE):
                    with open(_LAYOUT_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        self._column_layouts = {k: list(map(int, v)) for k, v in data.items() if isinstance(v, (list, tuple))}
            except Exception:
                self._column_layouts = {}

        def _save_column_layouts(self) -> None:
            try:
                if not os.path.isdir(_LAYOUT_DIR):
                    os.makedirs(_LAYOUT_DIR, exist_ok=True)
                with open(_LAYOUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._column_layouts, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        # -------------------------
        # Header listeners (컬럼 너비 저장)
        # -------------------------
        def _attach_header_listeners(self) -> None:
            try:
                for tab in range(1, 8):
                    tbl = getattr(self.view, f"table_tab_{tab}", None)
                    if tbl is None:
                        continue
                    try:
                        header = tbl.horizontalHeader()
                        # connect to controller handler
                        header.sectionResized.connect((lambda t: (lambda logical, old, new: self._on_section_resized(t, logical, old, new)))(tab))
                    except Exception:
                        pass
            except Exception:
                pass

        def _on_section_resized(self, tab: int, logicalIndex: int, oldSize: int, newSize: int) -> None:
            try:
                key = str(tab)
                widths = self._column_layouts.get(key, [])
                # determine column count
                cnt = 0
                try:
                    tbl = getattr(self.view, f"table_tab_{tab}", None)
                    if tbl is not None and hasattr(tbl, "columnCount"):
                        cnt = tbl.columnCount()
                    else:
                        cnt = max(len(widths), logicalIndex + 1)
                except Exception:
                    cnt = max(len(widths), logicalIndex + 1)

                if len(widths) < cnt:
                    widths = widths + [0] * (cnt - len(widths))
                if logicalIndex >= len(widths):
                    widths.extend([0] * (logicalIndex - len(widths) + 1))
                widths[logicalIndex] = int(newSize)
                self._column_layouts[key] = widths
                self._save_column_layouts()
            except Exception as exc:
                logger.debug("[StatisticsTabController] _on_section_resized 실패: %s", exc)

        # -------------------------
        # Log forwarding handler 등록
        # -------------------------
        def _register_forwarding_handler(self) -> None:
            try:
                root_logger = logging.getLogger()
                marker_name = "_StatisticsTabForwardingHandler"
                for h in list(root_logger.handlers):
                    if getattr(h, "name", "") == marker_name:
                        self._forwarding_handler = h
                        return

                class _ForwardingHandler(logging.Handler):
                    def __init__(self, target_cb):
                        super().__init__()
                        self.name = marker_name
                        self._cb = target_cb
                        self.setLevel(logging.DEBUG)

                    def emit(self, record):
                        try:
                            ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
                            entry = {
                                "time": ts,
                                "level": record.levelname,
                                "module": record.name,
                                "message": self.format(record),
                            }
                            self._cb(entry)
                        except Exception:
                            pass

                fh = _ForwardingHandler(self.add_log_entry)
                fmt = logging.Formatter("%(asctime)s [%(name)s] [%(levelname)s] %(message)s")
                fh.setFormatter(fmt)
                root_logger.addHandler(fh)
                self._forwarding_handler = fh
                logger.info("[StatisticsTabController] 포워딩 로그 핸들러 등록 완료")
            except Exception as exc:
                logger.debug("[StatisticsTabController] _register_forwarding_handler 실패: %s", exc)

        def _unregister_forwarding_handler(self) -> None:
            try:
                if self._forwarding_handler is None:
                    return
                root_logger = logging.getLogger()
                try:
                    root_logger.removeHandler(self._forwarding_handler)
                except Exception:
                    pass
                self._forwarding_handler = None
                logger.info("[StatisticsTabController] ��워딩 로그 핸들러 제거됨")
            except Exception as exc:
                logger.debug("[StatisticsTabController] _unregister_forwarding_handler 실패: %s", exc)

        # -------------------------
        # 외부 로그 소스 연결
        # -------------------------
        def set_log_handler(self, handler) -> None:
            """다양한 핸들러 인터페이스를 허용하여 콜백 등록을 시도합니다."""
            try:
                if handler is None:
                    return
                try:
                    if hasattr(handler, "set_new_log_callback"):
                        handler.set_new_log_callback(self.add_log_entry)
                    elif hasattr(handler, "set_new_log_cb"):
                        handler.set_new_log_cb(self.add_log_entry)
                    elif hasattr(handler, "register_new_log_callback"):
                        handler.register_new_log_callback(self.add_log_entry)
                    elif hasattr(handler, "new_log_callback"):
                        try:
                            handler.new_log_callback = self.add_log_entry
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception as exc:
                logger.debug("[StatisticsTabController] set_log_handler 실패: %s", exc)

        # -------------------------
        # 로그 수집/버퍼링
        # -------------------------
        def add_log_entry(self, entry: Dict[str, Any]) -> None:
            try:
                ts = entry.get("time") or datetime.now().strftime("%H:%M:%S.%f")[:-3]
                level = (entry.get("level") or "INFO").upper()
                module = entry.get("module") or entry.get("logger", "") or ""
                msg = entry.get("message") or entry.get("msg") or str(entry.get("msg", "")) or ""
                log_item = {"time": ts, "level": level, "category": "", "module": module, "message": msg}

                with self._pending_lock:
                    self._pending_logs.append(log_item)
                    max_pending = int(self._settings.get("max_pending", _DEF["max_pending"]))
                    if len(self._pending_logs) > max_pending:
                        while len(self._pending_logs) > int(max_pending * 0.8):
                            self._pending_logs.popleft()
            except Exception as exc:
                logger.debug("[StatisticsTabController] add_log_entry 실패: %s", exc)

        # -------------------------
        # Flush logic (timer)
        # -------------------------
        def _get_live_tabs(self) -> List[int]:
            try:
                active = self.view.get_active_tab()
                n = int(self._settings.get("num_live_tabs", _DEF["num_live_tabs"]))
                n = max(1, min(7, n))
                tabs = []
                for i in range(n):
                    t = ((active - 1 + i) % 7) + 1
                    tabs.append(t)
                return tabs
            except Exception:
                return [self.view.get_active_tab()]

        def _on_timer_flush(self) -> None:
            try:
                batch = []
                with self._pending_lock:
                    flush_batch = int(self._settings.get("flush_batch", _DEF["flush_batch"]))
                    for _ in range(min(flush_batch, len(self._pending_logs))):
                        batch.append(self._pending_logs.popleft())

                if not batch:
                    try:
                        self.view.set_status_text("상태: 대기")
                    except Exception:
                        pass
                    return

                live_tabs = set(self._get_live_tabs())

                for tab in range(1, 8):
                    try:
                        if tab not in live_tabs:
                            continue

                        filters = self._collect_filters_for_tab(tab)
                        buf = self._displayed_logs_by_tab.get(tab)
                        if buf is None:
                            buf = deque()
                            self._displayed_logs_by_tab[tab] = buf

                        for item in batch:
                            try:
                                if not self._filter_log_item(item, filters):
                                    continue
                                buf.append(item)
                                # 뷰에 행 삽입 호출
                                cells = [item.get("time", ""), item.get("level", ""), "", item.get("module", ""), item.get("message", "")]
                                self.view.insert_table_row(tab, cells)
                            except Exception:
                                continue

                        # trim rows for QTableWidget if necessary
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

                    except Exception:
                        pass

                # 상태 표시
                try:
                    self.view.set_status_text(f"상태: 수신 {len(batch)}건")
                    QTimer.singleShot(500, lambda: self.view.set_status_text("상태: 대기"))
                except Exception:
                    pass

            except Exception as exc:
                logger.debug("[StatisticsTabController] _on_timer_flush 실패: %s", exc)

        # -------------------------
        # UI 관련 헬퍼 (Controller가 뷰의 상태를 읽음)
        # -------------------------
        def _collect_filters_for_tab(self, tab: int) -> Dict[str, Any]:
            # 뷰의 체크박스/콤보/검색창을 직접 조회
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
            """간단 필터링: 검색어/레벨 기반(원본과 동일한 규칙 일부만 구현)."""
            try:
                search = (filters.get("search") or "").strip().lower()
                if search:
                    txt = (item.get("message", "") + " " + item.get("module", "")).lower()
                    if search not in txt:
                        return False
                # level 필터 (비어있으면 모두 허용)
                level_text = (filters.get("level_text") or "").strip().upper()
                if level_text:
                    lvl = (item.get("level", "") or "").upper()
                    if level_text != "ALL" and lvl != level_text:
                        return False
                # 기타 체크박스(웹소켓/파이프라인 등)는 사용자가 추가 구현 가능
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
        # View signal slots
        # -------------------------
        def _on_load_history_requested(self, path: str) -> None:
            # path가 비어있으면 기본 후보를 사용
            try:
                self.load_history(path=path or None, max_lines=int(self._settings.get("history_max_lines", _DEF["history_max_lines"])))
            except Exception as exc:
                logger.debug("[StatisticsTabController] _on_load_history_requested 실패: %s", exc)

        def _on_pause_toggled(self) -> None:
            try:
                if self._timer.isActive():
                    self._timer.stop()
                    self.view.set_status_text("상태: 일시정지")
                    self.view.set_pause_button_text("재개")
                else:
                    self._timer.start()
                    self.view.set_status_text("상태: 수신 대기")
                    self.view.set_pause_button_text("일시정지")
            except Exception as exc:
                logger.debug("[StatisticsTabController] _on_pause_toggled 실패: %s", exc)

        def _on_manual_refresh(self) -> None:
            try:
                t = self.view.get_active_tab()
                self._do_rebuild_table_for_tab(t)
            except Exception as exc:
                logger.debug("[StatisticsTabController] _on_manual_refresh 실패: %s", exc)

        def _on_export_tab_requested(self, tab: int) -> None:
            # 뷰에게 저장 경로를 물어본 뒤 저장 수행
            try:
                default = f"logs_tab{tab}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                path = self.view.get_save_file_path(f"로그 CSV 저장 (탭{tab})", default, "CSV Files (*.csv)")
                if not path:
                    return
                self._export_tab_to_path(tab, path)
            except Exception as exc:
                logger.debug("[StatisticsTabController] _on_export_tab_requested 실패: %s", exc)

        def _on_export_tab_with_path(self, tab: int, path: str) -> None:
            try:
                if not path:
                    return
                self._export_tab_to_path(tab, path)
            except Exception as exc:
                logger.debug("[StatisticsTabController] _on_export_tab_with_path 실패: %s", exc)

        def _on_export_all(self) -> None:
            try:
                # 단순 구현: export 현재 활성 탭
                self._on_export_tab_requested(self.view.get_active_tab())
            except Exception as exc:
                logger.debug("[StatisticsTabController] _on_export_all 실패: %s", exc)

        def _on_show_all_tab(self, tab: int) -> None:
            try:
                # 뷰의 체크박스들을 모두 켜고 리빌드
                for name in (f"chk_tab{tab}_ws", f"chk_tab{tab}_exchange_api", f"chk_tab{tab}_quotation_api", f"chk_tab{tab}_warning"):
                    try:
                        cb = getattr(self.view, name, None)
                        if cb is not None:
                            cb.setChecked(True)
                    except Exception:
                        pass
                # 검색 박스 클리어
                try:
                    le = getattr(self.view, f"le_tab{tab}_search", None)
                    if le is not None:
                        le.clear()
                except Exception:
                    pass
                self._do_rebuild_table_for_tab(tab)
            except Exception as exc:
                logger.debug("[StatisticsTabController] _on_show_all_tab 실패: %s", exc)

        def _on_active_tab_changed(self, tab: int) -> None:
            try:
                # 컬럼 너비 복원
                key = str(tab)
                if key in self._column_layouts:
                    widths = self._column_layouts[key]
                    tbl = getattr(self.view, f"table_tab_{tab}", None)
                    if tbl is not None:
                        for i, w in enumerate(widths):
                            try:
                                if w > 0 and hasattr(tbl, "setColumnWidth"):
                                    tbl.setColumnWidth(i, int(w))
                            except Exception:
                                pass
                # rebuild
                self._do_rebuild_table_for_tab(tab)
            except Exception:
                pass

        def _on_search_text_changed(self, tab: int, text: str) -> None:
            try:
                # 즉시 프록시 필터 업데이트를 시도하거나 리빌드를 예약
                proxy = self._proxies.get(tab)
                if proxy is not None and hasattr(proxy, "set_filters"):
                    filters = self._collect_filters_for_tab(tab)
                    try:
                        proxy.set_filters(filters)
                    except Exception:
                        self._do_rebuild_table_for_tab(tab)
                else:
                    self._do_rebuild_table_for_tab(tab)
            except Exception as exc:
                logger.debug("[StatisticsTabController] _on_search_text_changed 실패: %s", exc)

        # -------------------------
        # Table rebuild (전체 재구성)
        # -------------------------
        def _do_rebuild_table_for_tab(self, tab: int) -> None:
            try:
                tbl = getattr(self.view, f"table_tab_{tab}", None)
                if tbl is None:
                    return
                with self._pending_lock:
                    pending_snapshot = list(self._pending_logs)
                filters = self._collect_filters_for_tab(tab)
                combined = list(self._displayed_logs_by_tab.get(tab, deque())) + pending_snapshot
                filtered = [li for li in combined if self._filter_log_item(li, filters)]
                max_rows = self._get_max_rows_for_tab(tab)
                if len(filtered) > max_rows:
                    filtered = filtered[-max_rows:]
                self._displayed_logs_by_tab[tab] = deque(filtered, maxlen=max_rows)

                # View에 전체 행 설정
                rows = [[it.get("time", ""), it.get("level", ""), "", it.get("module", ""), it.get("message", "")] for it in filtered]
                self.view.set_table_rows(tab, rows)
            except Exception as exc:
                logger.debug("[StatisticsTabController] _do_rebuild_table_for_tab 실패: %s", exc)

        # -------------------------
        # 파일/히스토리 로드
        # -------------------------
        def load_history(self, path: Optional[str] = None, max_lines: int = 1000) -> None:
            """로그 파일에서 마지막 max_lines 줄을 읽어 탭1 Raw 뷰에 넣음."""
            try:
                candidates = []
                if path is not None:
                    candidates.append(path)
                candidates.extend([
                    os.path.join(os.path.expanduser("~"), "upbit-trader.log"),
                    os.path.join(os.getcwd(), "upbit-trader.log"),
                    os.path.join(os.path.expanduser("~"), ".upbit_trader", "upbit-trader.log"),
                ])
                chosen = None
                for p in candidates:
                    if p and os.path.exists(p):
                        chosen = p
                        break
                if chosen is None:
                    logger.info("[StatisticsTabController] load_history: 로그 파일을 찾을 수 없음 (path=%s)", path)
                    return
                lines = deque(maxlen=max_lines)
                with open(chosen, "r", encoding="utf-8", errors="replace") as f:
                    for ln in f:
                        lines.append(ln.rstrip("\n"))
                # 탭1 Raw 뷰에 추가
                try:
                    self.view.clear_raw(1)
                    self.view.append_raw_lines(1, list(lines))
                except Exception:
                    pass
                logger.info("[StatisticsTabController] load_history: %d lines loaded from %s", len(lines), chosen)
            except Exception as exc:
                logger.debug("[StatisticsTabController] load_history 실패: %s", exc)

        # -------------------------
        # Export helpers
        # -------------------------
        def _export_tab_to_path(self, tab: int, filename: str) -> None:
            try:
                tbl_view = getattr(self.view, f"table_tab_{tab}", None)
                if tbl_view is None:
                    return
                # QTableWidget 기반일 경우
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
                else:
                    # 모델 기반이라면 controller가 모델에서 직접 추출 (간단 대응)
                    model = self._models.get(tab)
                    proxy = self._proxies.get(tab)
                    src = proxy or model
                    if src is None:
                        return
                    cols = src.columnCount()
                    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.writer(f)
                        headers = [src.headerData(c, Qt.Horizontal, Qt.DisplayRole) for c in range(cols)]
                        writer.writerow(headers)
                        for r in range(src.rowCount()):
                            row_data = [src.data(src.index(r, c), Qt.DisplayRole) for c in range(cols)]
                            writer.writerow(row_data)
                logger.info("[StatisticsTabController] 탭%d CSV 저장 완료: %s", tab, filename)
            except Exception as exc:
                logger.error("[StatisticsTabController] _export_tab_to_path 실패: %s", exc, exc_info=True)

        # -------------------------
        # 기타 유틸
        # -------------------------
        def clear_tab(self, tab: int) -> None:
            try:
                self.view.clear_tab(tab)
                try:
                    self._displayed_logs_by_tab[tab].clear()
                except Exception:
                    pass
            except Exception as exc:
                logger.debug("[StatisticsTabController] clear_tab 실패: %s", exc)

        def clear_all_tabs(self) -> None:
            try:
                self.view.clear_all_tabs()
                for t in range(1, 8):
                    try:
                        self._displayed_logs_by_tab[t].clear()
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[StatisticsTabController] clear_all_tabs 실패: %s", exc)

else:
    # PyQt 미사용 환경용 더미 컨트롤러
    class StatisticsTabController:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PyQt5 not available; StatisticsTabController cannot be created in this environment.")