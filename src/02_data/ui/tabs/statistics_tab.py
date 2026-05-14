# -*- coding: utf-8 -*-
"""
StatisticsTab — 완전 구현 파일
- Designer(.ui)에서 정의한 시각 속성(스타일/레이아웃)을 덮어쓰지 않습니다.
- .ui에 정의된 QTableWidget을 우선 사용하며, 헤더를 Interactive 모드로 설정합니다.
- 컬럼 너비 변경(sectionResized)을 저장/복원(탭별)합니다.
- 툴바에 존재하면 btn_load_history 를 연결하여 로그 파일(upbit-trader.log 등)을 읽어 Raw 뷰에 표시합니다.
- 부트스트랩 시 콘솔(IDE)에서 로그가 보이도록 StreamHandler를 루트 로거에 추가합니다(중복 방지).
- 성능: flush 시 ResizeToContents 등 무거운 호출을 하지 않습니다.
"""
from __future__ import annotations
import csv
import json
import logging
import os
import threading
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer, Qt
    from PyQt5.QtGui import QColor
    from PyQt5.QtWidgets import (
        QWidget, QFileDialog, QAbstractItemView, QHeaderView,
        QTableView, QTableWidget, QTableWidgetItem, QPushButton
    )
    _HAS_QT = True
except Exception:
    _HAS_QT = False

# Optional local imports (if your project has these modules)
try:
    from ._mixins import TableCopyMixin
except Exception:
    TableCopyMixin = object

try:
    from .statistics_model import StatisticsModel, LogFilterProxyModel
except Exception:
    StatisticsModel = None
    LogFilterProxyModel = None

# Persistence paths (홈 디렉터리에 숨김 디렉터리)
_LAYOUT_DIR = os.path.join(os.path.expanduser("~"), ".upbit_trader")
_LAYOUT_FILE = os.path.join(_LAYOUT_DIR, "statistics_tab_layout.json")
_SETTINGS_FILE = os.path.join(_LAYOUT_DIR, "statistics_tab_settings.json")

# 기본 설정
_DEF = {
    "num_live_tabs": 3,
    "flush_interval_ms": 200,
    "flush_batch": 200,
    "max_pending": 100000,
    "enable_forwarding": True,
    "autostart_timer": True,
    "auto_load_history_on_start": False,  # 기본 자동 히스토리 로드 비활성
    "history_max_lines": 1000,
}


if _HAS_QT:
    class StatisticsTab(TableCopyMixin, QWidget):
        _RAW_VIEW_MAX_LINES = 2000

        def __init__(self, parent=None):
            super().__init__(parent)

            # .ui 로드
            ui_path = os.path.join(os.path.dirname(__file__), "statistics_tab.ui")
            try:
                uic.loadUi(ui_path, self)
            except Exception as exc:
                logger.warning("[StatisticsTab] UI 파일 로드 실패: %s", exc)

            # mixin 초기화가 있으면 호출 (없는 경우 예외 무시)
            try:
                self._setup_table_copy()
            except Exception:
                pass

            # 설정 불러오기
            self._settings: Dict[str, Any] = {}
            self._load_settings_file_or_defaults()

            # 내부 버퍼 및 락
            self._pending_logs: "deque[Dict[str, str]]" = deque()
            self._pending_lock = threading.Lock()

            # 탭별 표시 버퍼 및 뷰/모델 캐시
            self._displayed_logs_by_tab: Dict[int, deque] = {i: deque() for i in range(1, 8)}
            self._models: Dict[int, Optional[StatisticsModel]] = {}
            self._proxies: Dict[int, Optional[LogFilterProxyModel]] = {}
            self._views: Dict[int, Optional[object]] = {}  # QTableWidget or QTableView
            self._orig_tablewidgets: Dict[int, object] = {}

            # UI 위젯 캐시
            self._text_logs: Dict[int, Optional[object]] = {}
            self._search_boxes: Dict[int, Optional[object]] = {}
            self._spin_max_rows: Dict[int, Optional[object]] = {}
            self._chk_autoscrolls: Dict[int, Optional[object]] = {}
            self._chk_ws: Dict[int, Optional[object]] = {}
            self._chk_pipeline: Dict[int, Optional[object]] = {}
            self._chk_gap: Dict[int, Optional[object]] = {}
            self._chk_show_warnings: Dict[int, Optional[object]] = {}
            self._combo_levels: Dict[int, Optional[object]] = {}

            # 컬럼 레이아웃(탭별) 로드
            self._column_layouts: Dict[str, List[int]] = {}
            self._load_column_layouts()

            # 각 탭의 테이블을 바인딩하고 헤더를 Interactive로 바꿈(가능한 경우)
            for i in range(1, 8):
                tbl_widget = getattr(self, f"table_tab_{i}", None)
                self._orig_tablewidgets[i] = tbl_widget
                self._text_logs[i] = getattr(self, f"text_log_tab_{i}", None)
                self._search_boxes[i] = getattr(self, f"le_tab{i}_search", None)
                self._spin_max_rows[i] = getattr(self, f"sb_tab{i}_max_rows", None)
                self._chk_autoscrolls[i] = getattr(self, f"chk_tab{i}_autoscroll", None)
                self._chk_ws[i] = getattr(self, f"chk_tab{i}_ws", None)
                self._chk_pipeline[i] = getattr(self, f"chk_tab{i}_exchange_api", None)
                self._chk_gap[i] = getattr(self, f"chk_tab{i}_quotation_api", None)
                self._chk_show_warnings[i] = getattr(self, f"chk_tab{i}_warning", None)
                self._combo_levels[i] = getattr(self, f"combo_tab{i}_log_level", None) or getattr(self, "combo_log_level", None)

                try:
                    self._replace_table_widget_with_view(i, tbl_widget)
                except Exception as exc:
                    logger.debug("[StatisticsTab] _replace_table_widget_with_view 실패(tab=%s): %s", i, exc)

                # 검색 입력 연결
                try:
                    if self._search_boxes[i] is not None:
                        self._search_boxes[i].textChanged.connect(lambda _, tab=i: self._update_proxy_filters(tab))
                except Exception:
                    pass

                # per-tab 버튼 연결
                try:
                    btn_show_all = getattr(self, f"btn_tab{i}_show_all", None)
                    if btn_show_all is not None:
                        btn_show_all.clicked.connect(lambda _, tab=i: self._on_show_all_tab(tab))
                    btn_export = getattr(self, f"btn_tab{i}_export", None)
                    if btn_export is not None:
                        btn_export.clicked.connect(lambda _, tab=i: self._on_export_tab(tab))
                    btn_clear = getattr(self, f"btn_tab{i}_clear", None)
                    if btn_clear is not None:
                        btn_clear.clicked.connect(lambda _, tab=i: self.clear_tab(tab))
                except Exception:
                    pass

            # 툴바 버튼 연결(존재하면)
            try:
                btn_pause = getattr(self, "btn_pause", None)
                if btn_pause is not None:
                    btn_pause.clicked.connect(self._on_toggle_pause)
                btn_refresh = getattr(self, "btn_refresh", None)
                if btn_refresh is not None:
                    btn_refresh.clicked.connect(lambda: self._on_manual_refresh())
                btn_export_all = getattr(self, "btn_export_all", None)
                if btn_export_all is not None:
                    btn_export_all.clicked.connect(lambda: self._on_export_all())
                btn_clear_all = getattr(self, "btn_clear_all", None)
                if btn_clear_all is not None:
                    btn_clear_all.clicked.connect(lambda: self.clear_all_tabs())
                btn_settings = getattr(self, "btn_settings", None)
                if btn_settings is not None:
                    btn_settings.clicked.connect(self._open_settings_dialog)
                # Load history button 연결 (ui에 추가되어 있으면 연결)
                btn_load_history = getattr(self, "btn_load_history", None)
                if btn_load_history is not None:
                    try:
                        btn_load_history.clicked.connect(self._on_load_history)
                        # 스타일을 .ui에 넣었으므로 여기서는 스타일 변경하지 않음
                    except Exception:
                        pass
            except Exception:
                pass

            # 타이머 설정
            self._timer = QTimer(self)
            self._timer.setInterval(int(self._settings.get("flush_interval_ms", _DEF["flush_interval_ms"])))
            self._timer.timeout.connect(self._on_timer_flush)

            # 메인 탭 위젯 훅
            self._main_tabwidget = getattr(self, "tabWidget_main_tabs", None)
            try:
                if self._main_tabwidget is not None:
                    self._main_tabwidget.currentChanged.connect(lambda idx: self._on_active_tab_changed())
            except Exception:
                pass

            # 로거 핸들러(자동 등록 시도)
            self._log_handler = None
            self._auto_log_handler = None
            self._forwarding_handler = None
            self._setup_auto_log_handler()

            # 콘솔(디버거) StreamHandler 추가 (중복 방지)
            self._add_bootstrap_stream_handler()

            # 자동 타이머 시작
            try:
                if bool(self._settings.get("autostart_timer", _DEF["autostart_timer"])) and not self._timer.isActive():
                    self._timer.start()
                    logger.info("[StatisticsTab] 타이머 자동 시작")
            except Exception:
                pass

            # 자동 히스토리 로드 설정이 켜져 있으면 시작 시 로드
            try:
                if bool(self._settings.get("auto_load_history_on_start", _DEF["auto_load_history_on_start"])):
                    self.load_history(max_lines=int(self._settings.get("history_max_lines", _DEF["history_max_lines"])))
            except Exception:
                pass

        # -------------------------
        # 설정 파일 로드/저장
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
                logger.debug("[StatisticsTab] _load_settings_file_or_defaults 실패: %s", exc)

        def _save_settings_file(self) -> None:
            try:
                if not os.path.isdir(_LAYOUT_DIR):
                    os.makedirs(_LAYOUT_DIR, exist_ok=True)
                with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._settings, f, ensure_ascii=False, indent=2)
            except Exception as exc:
                logger.debug("[StatisticsTab] _save_settings_file 실패: %s", exc)

        # -------------------------
        # 컬럼 레이아웃 저장/복원
        # -------------------------
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
        # .ui에서 제공한 QTableWidget을 보존하면서 헤더를 Interactive로 설정
        # -------------------------
        def _replace_table_widget_with_view(self, tab: int, orig_widget) -> None:
            try:
                if orig_widget is not None and isinstance(orig_widget, QTableWidget):
                    tbl: QTableWidget = orig_widget
                    # 헤더를 Interactive로 바꿔 사용자 수동 조절 허용
                    try:
                        header = tbl.horizontalHeader()
                        header.setSectionsClickable(True)
                        try:
                            header.setSectionResizeMode(QHeaderView.Interactive)
                        except Exception:
                            # older Qt/PyQt 버전 호환성
                            pass
                        # 섹션 리사이즈 이벤트를 저장
                        try:
                            header.sectionResized.connect((lambda t: (lambda logical, old, new: self._on_section_resized(t, logical, old, new)))(tab))
                        except Exception:
                            pass
                    except Exception:
                        pass

                    # 복원된 너비가 있으면 적용
                    key = str(tab)
                    if key in self._column_layouts:
                        widths = self._column_layouts[key]
                        for col, w in enumerate(widths):
                            try:
                                if w > 0 and col < tbl.columnCount():
                                    tbl.setColumnWidth(col, int(w))
                            except Exception:
                                pass

                    self._views[tab] = tbl
                    self._models[tab] = None
                    self._proxies[tab] = None
                    return

                # .ui에 QTableWidget이 없으면 모델/뷰 방식으로 대체 (가능하면)
                if StatisticsModel is not None and LogFilterProxyModel is not None:
                    model = StatisticsModel(self)
                    proxy = LogFilterProxyModel(self)
                    proxy.setSourceModel(model)

                    view = QTableView(self)
                    view.setModel(proxy)
                    view.setSelectionBehavior(QAbstractItemView.SelectRows)
                    view.setEditTriggers(QAbstractItemView.NoEditTriggers)
                    view.setAlternatingRowColors(True)
                    header = view.horizontalHeader()
                    header.setSectionsClickable(True)
                    header.setSectionResizeMode(QHeaderView.Interactive)
                    try:
                        header.sectionResized.connect((lambda t: (lambda logical, old, new: self._on_section_resized(t, logical, old, new)))(tab))
                    except Exception:
                        pass

                    # 레이아웃 교체: orig_widget이 있으면 그 위치에 view 삽입
                    if orig_widget is not None and hasattr(orig_widget, "parent"):
                        layout = orig_widget.parent().layout()
                        if layout is not None:
                            for i in range(layout.count()):
                                it = layout.itemAt(i)
                                w = it.widget() if it is not None else None
                                if w is orig_widget:
                                    layout.removeWidget(orig_widget)
                                    try:
                                        orig_widget.hide()
                                    except Exception:
                                        pass
                                    layout.insertWidget(i, view)
                                    break

                    # 저장된 너비가 있으면 적용
                    key = str(tab)
                    if key in self._column_layouts:
                        widths = self._column_layouts[key]
                        for col, w in enumerate(widths):
                            try:
                                if w > 0:
                                    view.setColumnWidth(col, int(w))
                            except Exception:
                                pass

                    self._models[tab] = model
                    self._proxies[tab] = proxy
                    self._views[tab] = view
                    return

                # 아무 것도 못하는 경우: 빈 슬롯으로 둠
                self._views[tab] = orig_widget
                self._models[tab] = None
                self._proxies[tab] = None

            except Exception as exc:
                logger.debug("[StatisticsTab] _replace_table_widget_with_view 예외: %s", exc)

        def _on_section_resized(self, tab: int, logicalIndex: int, oldSize: int, newSize: int) -> None:
            try:
                key = str(tab)
                widths = self._column_layouts.get(key, [])
                view = self._views.get(tab)
                cnt = 0
                try:
                    if isinstance(view, QTableWidget):
                        cnt = view.columnCount()
                    elif hasattr(view, "model") and view.model() is not None:
                        cnt = view.model().columnCount()
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
                logger.debug("[StatisticsTab] _on_section_resized 실패: %s", exc)

        # -------------------------
        # 로그 핸들러 연결 및 포워딩
        # -------------------------
        def set_log_handler(self, handler) -> None:
            try:
                self._log_handler = handler
                # 다양한 핸들러 인터페이스에 최대한 대응해서 콜백을 등록
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
                logger.debug("[StatisticsTab] set_log_handler 실패: %s", exc)

        def _on_external_signal_received(self, entry: Optional[Dict[str, str]]) -> None:
            if entry is None:
                return
            self.add_log_entry(entry)

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
                                "message": self.format(record)
                            }
                            self._cb(entry)
                        except Exception:
                            pass

                fh = _ForwardingHandler(self.add_log_entry)
                fmt = logging.Formatter("%(asctime)s [%(name)s] [%(levelname)s] %(message)s")
                fh.setFormatter(fmt)
                root_logger.addHandler(fh)
                self._forwarding_handler = fh
                logger.info("[StatisticsTab] 포워딩 로그 핸들러 등록 완료")
            except Exception as exc:
                logger.debug("[StatisticsTab] _register_forwarding_handler 실패: %s", exc)

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
                logger.info("[StatisticsTab] 포워딩 로그 핸들러 제거됨")
            except Exception as exc:
                logger.debug("[StatisticsTab] _unregister_forwarding_handler 실패: %s", exc)

        def _setup_auto_log_handler(self) -> None:
            try:
                # 프로젝트 내 UILogHandler가 있으면 사용 시도
                from ..controllers.log_handler import UILogHandler  # type: ignore
                handler = UILogHandler()
                self.set_log_handler(handler)
                self._auto_log_handler = handler
                try:
                    logging.getLogger().addHandler(handler)
                except Exception:
                    pass
                logger.info("[StatisticsTab] UILogHandler 등록 시도")
            except Exception:
                # 허용된 실패: 없을 수 있음
                logger.debug("[StatisticsTab] UILogHandler 없음 또는 등록 실패 (무시)")

            try:
                if bool(self._settings.get("enable_forwarding", _DEF["enable_forwarding"])):
                    self._register_forwarding_handler()
            except Exception as exc:
                logger.debug("[StatisticsTab] forwarding handler setup 실패: %s", exc)

        # -------------------------
        # 부트스트랩: 콘솔 StreamHandler 추가 (디버깅 시 유용)
        # -------------------------
        def _add_bootstrap_stream_handler(self) -> None:
            try:
                root = logging.getLogger()
                # 이미 StreamHandler가 존재하면 추가하지 않음(중복 방지)
                has_stream = any(isinstance(h, logging.StreamHandler) for h in root.handlers)
                if not has_stream:
                    sh = logging.StreamHandler()
                    sh.setLevel(logging.DEBUG)
                    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
                    sh.setFormatter(fmt)
                    root.addHandler(sh)
                    logger.debug("[StatisticsTab] bootstrap StreamHandler 추가됨")
            except Exception:
                pass

        # -------------------------
        # 로그 수집/버퍼링/flush
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
                        # 큐 과도 시 일부 제거 (80%까지)
                        while len(self._pending_logs) > int(max_pending * 0.8):
                            self._pending_logs.popleft()
            except Exception as exc:
                logger.debug("[StatisticsTab] add_log_entry 실패: %s", exc)

        def _get_live_tabs(self) -> List[int]:
            try:
                active = self._active_tab()
                n = int(self._settings.get("num_live_tabs", _DEF["num_live_tabs"]))
                n = max(1, min(7, n))
                tabs = []
                for i in range(n):
                    t = ((active - 1 + i) % 7) + 1
                    tabs.append(t)
                return tabs
            except Exception:
                return [self._active_tab()]

        def _on_timer_flush(self) -> None:
            try:
                batch = []
                with self._pending_lock:
                    flush_batch = int(self._settings.get("flush_batch", _DEF["flush_batch"]))
                    for _ in range(min(flush_batch, len(self._pending_logs))):
                        batch.append(self._pending_logs.popleft())

                if not batch:
                    lbl = getattr(self, "lbl_toolbar_status", None)
                    if lbl is not None:
                        try:
                            lbl.setText("상태: 대기")
                        except Exception:
                            pass
                    return

                live_tabs = set(self._get_live_tabs())

                for tab, view in list(self._views.items()):
                    try:
                        if tab not in live_tabs:
                            continue
                        tbl = view
                        if tbl is None:
                            continue

                        buf = self._displayed_logs_by_tab.get(tab)
                        if buf is None:
                            buf = deque()
                            self._displayed_logs_by_tab[tab] = buf

                        filters = self._collect_filters_for_tab(tab)

                        for item in batch:
                            try:
                                if not self._filter_log_item(item, filters):
                                    continue
                                buf.append(item)

                                # .ui에서 정의된 QTableWidget이 있으면 그대로 사용
                                if isinstance(tbl, QTableWidget):
                                    col_count = tbl.columnCount()
                                    if col_count == 0:
                                        # 디자이너가 컬럼을 정의하지 않았다면 UI 변경을 피함
                                        continue
                                    row = tbl.rowCount()
                                    tbl.insertRow(row)
                                    cells = [item.get("time", ""), item.get("level", ""), "", item.get("module", ""), item.get("message", "")]
                                    for j in range(min(len(cells), col_count)):
                                        it = QTableWidgetItem(str(cells[j]))
                                        if j == 1:
                                            lvl = (item.get("level") or "").upper()
                                            color = None
                                            if lvl == "ERROR":
                                                color = QColor(239, 68, 68)
                                            elif lvl == "WARNING":
                                                color = QColor(251, 146, 60)
                                            elif lvl == "INFO":
                                                color = QColor(34, 197, 94)
                                            elif lvl == "DEBUG":
                                                color = QColor(148, 163, 184)
                                            if color is not None:
                                                try:
                                                    it.setForeground(color)
                                                except Exception:
                                                    pass
                                        try:
                                            tbl.setItem(row, j, it)
                                        except Exception:
                                            pass
                                else:
                                    model = self._models.get(tab)
                                    if model is not None:
                                        try:
                                            model.append_rows([item])
                                        except Exception:
                                            pass
                            except Exception:
                                continue

                        # 오래된 행 제거 (trim)
                        try:
                            if isinstance(tbl, QTableWidget):
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

                        # 자동 스크롤
                        try:
                            chk = self._chk_autoscrolls.get(tab)
                            if chk is None or chk.isChecked():
                                try:
                                    if isinstance(tbl, QTableWidget):
                                        vscroll = tbl.verticalScrollBar()
                                        if vscroll is not None:
                                            maxv = vscroll.maximum()
                                            curv = vscroll.value()
                                            if maxv - curv <= 20:
                                                tbl.scrollToBottom()
                                        else:
                                            tbl.scrollToBottom()
                                    else:
                                        tbl.scrollToBottom()
                                except Exception:
                                    try:
                                        tbl.scrollToBottom()
                                    except Exception:
                                        pass
                        except Exception:
                            pass

                    except Exception:
                        pass

                # 상태 표시
                try:
                    lbl = getattr(self, "lbl_toolbar_status", None)
                    if lbl is not None:
                        lbl.setText(f"상태: 수신 {len(batch)}건")
                        QTimer.singleShot(500, lambda: lbl.setText("상태: 대기"))
                except Exception:
                    pass

            except Exception as exc:
                logger.debug("[StatisticsTab] _on_timer_flush 실패: %s", exc)

        # -------------------------
        # 필터 수집/업데이트 등 UI 보조
        # -------------------------
        def _collect_filters_for_tab(self, tab: int) -> Dict[str, Any]:
            try:
                ws = bool(self._chk_ws.get(tab) and self._chk_ws[tab].isChecked())
            except Exception:
                ws = False
            try:
                pl = bool(self._chk_pipeline.get(tab) and self._chk_pipeline[tab].isChecked())
            except Exception:
                pl = False
            try:
                gap = bool(self._chk_gap.get(tab) and self._chk_gap[tab].isChecked())
            except Exception:
                gap = False
            try:
                show_warnings = bool(self._chk_show_warnings.get(tab) and self._chk_show_warnings[tab].isChecked())
            except Exception:
                show_warnings = True
            try:
                combo = self._combo_levels.get(tab)
                level_text = combo.currentText() if combo is not None else ""
            except Exception:
                level_text = ""
            try:
                le = self._search_boxes.get(tab)
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

        def _update_proxy_filters(self, tab: int) -> None:
            try:
                proxy = self._proxies.get(tab)
                if proxy is not None:
                    filters = self._collect_filters_for_tab(tab)
                    proxy.set_filters(filters)
                else:
                    self._do_rebuild_table_for_tab(tab)
            except Exception as exc:
                logger.debug("[StatisticsTab] _update_proxy_filters 실패: %s", exc)

        # -------------------------
        # UI 액션들
        # -------------------------
        def _on_toggle_pause(self) -> None:
            try:
                if self._timer.isActive():
                    self._timer.stop()
                    lbl = getattr(self, "lbl_toolbar_status", None)
                    if lbl is not None:
                        lbl.setText("상태: 일시정지")
                    btn = getattr(self, "btn_pause", None)
                    if btn is not None:
                        try:
                            btn.setText("재개")
                        except Exception:
                            pass
                else:
                    self._timer.start()
                    lbl = getattr(self, "lbl_toolbar_status", None)
                    if lbl is not None:
                        lbl.setText("상태: 수신 대기")
                    btn = getattr(self, "btn_pause", None)
                    if btn is not None:
                        try:
                            btn.setText("일시정지")
                        except Exception:
                            pass
            except Exception as exc:
                logger.debug("[StatisticsTab] _on_toggle_pause 실패: %s", exc)

        def _on_manual_refresh(self) -> None:
            try:
                t = self._active_tab()
                self._do_rebuild_table_for_tab(t)
            except Exception as exc:
                logger.debug("[StatisticsTab] _on_manual_refresh 실패: %s", exc)

        def _on_export_all(self) -> None:
            self._on_export_tab(self._active_tab())

        def clear_all_tabs(self) -> None:
            for t in range(1, 8):
                self.clear_tab(t)

        def _on_active_tab_changed(self) -> None:
            t = self._active_tab()
            try:
                view = self._views.get(t)
                key = str(t)
                if view is not None and key in self._column_layouts:
                    widths = self._column_layouts[key]
                    for i, w in enumerate(widths):
                        try:
                            if w > 0:
                                # QTableWidget / QTableView 모두 setColumnWidth 지원
                                view.setColumnWidth(i, int(w))
                        except Exception:
                            pass
            except Exception:
                pass
            self._mark_rebuild_tab(t)

        def _active_tab(self) -> int:
            try:
                idx = int(self._main_tabwidget.currentIndex()) + 1
                return max(1, min(7, idx))
            except Exception:
                return 1

        def _do_rebuild_table_for_tab(self, tab: int) -> None:
            try:
                view = self._views.get(tab)
                if view is None:
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

                if isinstance(view, QTableWidget):
                    tbl = view
                    col_count = tbl.columnCount()
                    if col_count == 0:
                        # 디자이너가 컬럼을 지정하지 않은 경우 시각 변경을 피한다
                        return
                    tbl.setRowCount(0)
                    for item in filtered:
                        row = tbl.rowCount()
                        tbl.insertRow(row)
                        cells = [item.get("time", ""), item.get("level", ""), "", item.get("module", ""), item.get("message", "")]
                        for j in range(min(len(cells), col_count)):
                            it = QTableWidgetItem(str(cells[j]))
                            if j == 1:
                                level = (item.get("level","") or "").upper()
                                color = None
                                if level == "ERROR":
                                    color = QColor(239, 68, 68)
                                elif level == "WARNING":
                                    color = QColor(251, 146, 60)
                                elif level == "INFO":
                                    color = QColor(34, 197, 94)
                                elif level == "DEBUG":
                                    color = QColor(148, 163, 184)
                                if color is not None:
                                    try:
                                        it.setForeground(color)
                                    except Exception:
                                        pass
                            try:
                                tbl.setItem(row, j, it)
                            except Exception:
                                pass
                    try:
                        chk = self._chk_autoscrolls.get(tab)
                        if chk is None or chk.isChecked():
                            tbl.scrollToBottom()
                    except Exception:
                        pass
                else:
                    model = self._models.get(tab)
                    if model is not None:
                        try:
                            model.clear()
                            model.append_rows(filtered)
                        except Exception:
                            pass
            except Exception as exc:
                logger.debug("[StatisticsTab] _do_rebuild_table_for_tab 실패: %s", exc)

        def _on_export_tab(self, tab: int) -> None:
            tbl_view = self._views.get(tab)
            if tbl_view is None:
                return
            filename, _ = QFileDialog.getSaveFileName(
                self,
                f"로그 CSV 저장 (탭{tab})",
                f"logs_tab{tab}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "CSV Files (*.csv)",
            )
            if not filename:
                return
            try:
                if isinstance(tbl_view, QTableWidget):
                    cols = tbl_view.columnCount()
                    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.writer(f)
                        headers = []
                        for c in range(cols):
                            try:
                                headers.append(tbl_view.horizontalHeaderItem(c).text() if tbl_view.horizontalHeaderItem(c) is not None else "")
                            except Exception:
                                headers.append("")
                        writer.writerow(headers)
                        for r in range(tbl_view.rowCount()):
                            row_data = []
                            for c in range(cols):
                                item = tbl_view.item(r, c)
                                row_data.append(item.text() if item is not None else "")
                            writer.writerow(row_data)
                else:
                    # 모델 기반 뷰의 경우 프록시/모델에서 추출
                    proxy = self._proxies.get(tab)
                    model = proxy or self._models.get(tab)
                    if model is None:
                        return
                    cols = model.columnCount()
                    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.writer(f)
                        headers = [model.headerData(c, Qt.Horizontal, Qt.DisplayRole) for c in range(cols)]
                        writer.writerow(headers)
                        for r in range(model.rowCount()):
                            row_data = [model.data(model.index(r, c), Qt.DisplayRole) for c in range(cols)]
                            writer.writerow(row_data)
                logger.info("[StatisticsTab] 탭%d CSV 저장 완료: %s", tab, filename)
            except Exception as exc:
                logger.error("[StatisticsTab] _on_export_tab 저장 실패: %s", exc, exc_info=True)

        def _on_show_all_tab(self, tab: int) -> None:
            try:
                for cb in (self._chk_ws.get(tab), self._chk_pipeline.get(tab), self._chk_gap.get(tab), self._chk_show_warnings.get(tab)):
                    try:
                        if cb is not None:
                            cb.setChecked(True)
                    except Exception:
                        pass
                combo = self._combo_levels.get(tab)
                if combo is not None:
                    try:
                        combo.setCurrentIndex(0)
                    except Exception:
                        pass
                le = self._search_boxes.get(tab)
                if le is not None:
                    try:
                        le.clear()
                    except Exception:
                        pass
                self._update_proxy_filters(tab)
            except Exception as exc:
                logger.debug("[StatisticsTab] _on_show_all_tab 실패: %s", exc)

        def clear_tab(self, tab: int) -> None:
            try:
                view = self._views.get(tab)
                if isinstance(view, QTableWidget):
                    try:
                        view.setRowCount(0)
                    except Exception:
                        pass
                model = self._models.get(tab)
                if model is not None:
                    try:
                        model.clear()
                    except Exception:
                        pass
                try:
                    self._displayed_logs_by_tab[tab].clear()
                except Exception:
                    pass
                text = self._text_logs.get(tab)
                if text is not None:
                    try:
                        text.clear()
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[StatisticsTab] clear_tab 실패: %s", exc)

        def _mark_rebuild_tab(self, tab: int) -> None:
            try:
                QTimer.singleShot(0, lambda t=tab: self._do_rebuild_table_for_tab(t))
            except Exception:
                pass

        # -------------------------
        # 히스토리 로드 기능 (Load history 버튼 및 수동 호출)
        # -------------------------
        def _on_load_history(self) -> None:
            try:
                filename, _ = QFileDialog.getOpenFileName(self, "로그 파일 선택", os.path.expanduser("~"), "Log Files (*.log *.txt);;All Files (*)")
                if not filename:
                    return
                max_lines = int(self._settings.get("history_max_lines", _DEF["history_max_lines"]))
                self.load_history(path=filename, max_lines=max_lines)
            except Exception as exc:
                logger.debug("[StatisticsTab] _on_load_history 실패: %s", exc)

        def load_history(self, path: Optional[str] = None, max_lines: int = 1000) -> None:
            """지정된 로그 파일에서 마지막 max_lines 줄을 읽어 탭1 Raw 뷰에 넣습니다."""
            try:
                candidates = []
                if path is not None:
                    candidates.append(path)
                # 기본 후보 경로
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
                    logger.info("[StatisticsTab] load_history: 로그 파일을 찾을 수 없음 (path=%s)", path)
                    return
                # 마지막 N줄만 읽기 (메모리 절약을 위해 deque 사용)
                lines = deque(maxlen=max_lines)
                with open(chosen, "r", encoding="utf-8", errors="replace") as f:
                    for ln in f:
                        lines.append(ln.rstrip("\n"))
                raw_widget = self._text_logs.get(1)
                if raw_widget is not None:
                    try:
                        raw_widget.clear()
                        raw_widget.append("\n".join(lines))
                    except Exception:
                        pass
                logger.info("[StatisticsTab] load_history: %d lines loaded from %s", len(lines), chosen)
            except Exception as exc:
                logger.debug("[StatisticsTab] load_history 실패: %s", exc)

else:
    # GUI 미사용 환경용 더미 클래스
    class StatisticsTab:
        def __init__(self, parent=None):
            pass
        def start_updates(self, interval_ms: int = 3000) -> None:
            pass
        def stop_updates(self) -> None:
            pass
        def set_log_handler(self, handler) -> None:
            pass
        def update_log_table(self, logs) -> None:
            pass
        def clear_logs(self) -> None:
            pass