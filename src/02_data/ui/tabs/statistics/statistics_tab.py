# -*- coding: utf-8 -*-
"""
StatisticsTab (View 전용, 강화된 UI 로드/바인딩)
- 핵심 목표: .ui가 로드되어도 위젯(objectName)이 없어서 화면이 비어 보이는 문제 방지.
- 전략:
  1) load_ui_with_tab_fix 우선 시도 (있으면 .ui enum/xml 보정)
  2) PyQt uic.loadUi 폴백
  3) uic.loadUiType 폴백 (코드 생성형)
  4) 로드 후 핵심 위젯(tabWidget_main_tabs, table_tab_X 등)이 없으면 findChild 기반으로 자동 바인딩
- 이 파일은 View·시그널·경량 헬퍼만 포함합니다. 비즈니스 로직은 Controller로 이동하세요.
"""
from __future__ import annotations
import os
import logging
import importlib
import importlib.util
from typing import Any, Optional, Sequence, Dict

logger = logging.getLogger(__name__)

# PyQt import (가용성 검사)
try:
    from PyQt5 import uic
    from PyQt5.QtCore import pyqtSignal
    from PyQt5.QtWidgets import (
        QWidget, QFileDialog, QTableWidget, QTableWidgetItem, QTextEdit, QTabWidget, QLabel, QVBoxLayout
    )
    from PyQt5.QtGui import QColor
    _HAS_QT = True
except Exception:
    _HAS_QT = False

# 안전한 load_ui_with_tab_fix 시도 (절대 import 또는 파일 경로 fallback)
def _load_ui_loader() -> Optional[callable]:
    try:
        # 우선 절대 모듈 시도 (workspace가 src를 패키지 루트로 인식할 때)
        try:
            mod = importlib.import_module("src.02_data.ui_loader")
            return getattr(mod, "load_ui_with_tab_fix", None)
        except Exception:
            # 파일 경로 후보들
            cand = [
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "ui_loader.py")),
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "ui_loader.py")),
            ]
            for p in cand:
                try:
                    if os.path.exists(p):
                        spec = importlib.util.spec_from_file_location("ui_loader_local", p)
                        if spec and spec.loader:
                            mod = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(mod)
                            return getattr(mod, "load_ui_with_tab_fix", None)
                except Exception:
                    continue
    except Exception:
        pass
    return None

_load_ui_with_tab_fix = _load_ui_loader()

if _HAS_QT:
    class StatisticsTab(QWidget):
        # View-only signals
        load_history_requested = pyqtSignal(str)
        pause_toggled = pyqtSignal()
        manual_refresh_requested = pyqtSignal()
        export_tab_requested = pyqtSignal(int)
        export_all_requested = pyqtSignal()
        clear_tab_requested = pyqtSignal(int)
        clear_all_requested = pyqtSignal()
        active_tab_changed = pyqtSignal(int)
        search_text_changed = pyqtSignal(int, str)

        def __init__(self, parent=None, ui_filename: Optional[str] = None):
            super().__init__(parent)

            # default ui path
            if ui_filename is None:
                ui_filename = os.path.join(os.path.dirname(__file__), "statistics_tab.ui")

            # Try loading UI robustly
            loaded = self._robust_load_ui(ui_filename)

            # If load failed or critical widgets missing, place a visible warning widget so user sees UI
            if not loaded or not self._has_core_widgets():
                logger.warning("[StatisticsTab] UI 로드 또는 바인딩 불완전 — 자동 바인딩 시도 및 경고 라벨 표시")
                self._attempt_find_widgets()
                if not self._has_core_widgets():
                    self._show_ui_warning(f"StatisticsTab UI 로드 실패 또는 핵심 위젯 누락: {os.path.basename(ui_filename)}")

            # build caches
            self._tables: Dict[int, Optional[QTableWidget]] = {}
            self._raw_texts: Dict[int, Optional[QTextEdit]] = {}
            self._search_boxes: Dict[int, Optional[object]] = {}

            for i in range(1, 8):
                # objectName expected: table_tab_1 .. text_log_tab_1 .. le_tab1_search
                self._tables[i] = self._find_widget_by_name(QTableWidget, f"table_tab_{i}")
                self._raw_texts[i] = self._find_widget_by_name(QTextEdit, f"text_log_tab_{i}") or self._find_widget_by_name(QTextEdit, f"plain_log_tab_{i}")
                self._search_boxes[i] = self.findChild(type(getattr(self, f"le_tab{i}_search", None) or object), f"le_tab{i}_search") or self._find_widget_by_name(object, f"le_tab{i}_search")

            # Connect simple view-level signals
            for i in range(1, 8):
                le = self._search_boxes.get(i)
                if le is not None and hasattr(le, "textChanged"):
                    try:
                        le.textChanged.connect((lambda t: (lambda txt: self.search_text_changed.emit(t, (txt or "").strip().lower())))(i))
                    except Exception:
                        pass

                # per-tab buttons
                try:
                    btn_show_all = self._find_widget_by_name(QWidget, f"btn_tab{i}_show_all") or getattr(self, f"btn_tab{i}_show_all", None)
                    if btn_show_all and hasattr(btn_show_all, "clicked"):
                        btn_show_all.clicked.connect((lambda t: (lambda: self._on_show_all_clicked(t)))(i))
                except Exception:
                    pass
                try:
                    btn_export = self._find_widget_by_name(QWidget, f"btn_tab{i}_export") or getattr(self, f"btn_tab{i}_export", None)
                    if btn_export and hasattr(btn_export, "clicked"):
                        btn_export.clicked.connect((lambda t: (lambda: self.export_tab_requested.emit(t)))(i))
                except Exception:
                    pass
                try:
                    btn_clear = self._find_widget_by_name(QWidget, f"btn_tab{i}_clear") or getattr(self, f"btn_tab{i}_clear", None)
                    if btn_clear and hasattr(btn_clear, "clicked"):
                        btn_clear.clicked.connect((lambda t: (lambda: self.clear_tab_requested.emit(t)))(i))
                except Exception:
                    pass

            # toolbar buttons
            try:
                btn_pause = self._find_widget_by_name(QWidget, "btn_pause") or getattr(self, "btn_pause", None)
                if btn_pause and hasattr(btn_pause, "clicked"):
                    btn_pause.clicked.connect(lambda: self.pause_toggled.emit())
            except Exception:
                pass
            try:
                btn_refresh = self._find_widget_by_name(QWidget, "btn_refresh") or getattr(self, "btn_refresh", None)
                if btn_refresh and hasattr(btn_refresh, "clicked"):
                    btn_refresh.clicked.connect(lambda: self.manual_refresh_requested.emit())
            except Exception:
                pass
            try:
                btn_load_history = self._find_widget_by_name(QWidget, "btn_load_history") or getattr(self, "btn_load_history", None)
                if btn_load_history and hasattr(btn_load_history, "clicked"):
                    btn_load_history.clicked.connect(self._on_load_history_clicked)
            except Exception:
                pass

            # main tab changed
            try:
                main_tabs: Optional[QTabWidget] = self._find_widget_by_name(QTabWidget, "tabWidget_main_tabs") or self._find_first_child(QTabWidget)
                if main_tabs is not None:
                    main_tabs.currentChanged.connect(lambda idx: self.active_tab_changed.emit(int(idx) + 1))
            except Exception:
                pass

            # initial status label if present
            self.set_status_text("상태: 대기")

        # -------------------------
        # Robust UI load helpers
        # -------------------------
        def _robust_load_ui(self, ui_path: str) -> bool:
            """Try load_ui_with_tab_fix, then uic.loadUi, then uic.loadUiType as final fallback."""
            try:
                if _load_ui_with_tab_fix is not None:
                    try:
                        _load_ui_with_tab_fix(ui_path, self)
                        logger.info("[StatisticsTab] UI 로드 성공 (load_ui_with_tab_fix)")
                        return True
                    except Exception as e:
                        logger.debug("[StatisticsTab] load_ui_with_tab_fix 실패: %s", e)
                # Try uic.loadUi
                try:
                    uic.loadUi(ui_path, self)
                    logger.info("[StatisticsTab] UI 로드 성공 (uic.loadUi)")
                    return True
                except Exception as e:
                    logger.debug("[StatisticsTab] uic.loadUi 실패: %s", e)
                # Try loadUiType fallback
                try:
                    form_class, base_class = uic.loadUiType(ui_path)
                    # form_class has setupUi(self)
                    form = form_class()
                    form.setupUi(self)
                    logger.info("[StatisticsTab] UI 로드 성공 (uic.loadUiType 폴백)")
                    return True
                except Exception as e:
                    logger.warning("[StatisticsTab] uic.loadUiType 폴백 실패: %s", e)
                    return False
            except Exception as exc:
                logger.exception("[StatisticsTab] UI 로드 중 예외: %s", exc)
                return False

        def _has_core_widgets(self) -> bool:
            """Check for presence of primary expected widgets."""
            if hasattr(self, "tabWidget_main_tabs") and getattr(self, "tabWidget_main_tabs") is not None:
                return True
            # fallback: any table or text_log present
            for name in ("table_tab_1", "text_log_tab_1"):
                if hasattr(self, name) and getattr(self, name) is not None:
                    return True
            return False

        def _attempt_find_widgets(self) -> None:
            """Try to auto-bind expected widget names via findChild if attributes missing."""
            # Bind tabWidget_main_tabs
            if not hasattr(self, "tabWidget_main_tabs") or getattr(self, "tabWidget_main_tabs") is None:
                tab = self._find_first_child(QTabWidget)
                if tab is not None:
                    try:
                        setattr(self, "tabWidget_main_tabs", tab)
                        logger.debug("[StatisticsTab] tabWidget_main_tabs 자동 바인딩 됨 (%s)", tab.objectName())
                    except Exception:
                        pass
            # For tables/texts: attempt findChild by name patterns
            for i in range(1, 8):
                if not hasattr(self, f"table_tab_{i}") or getattr(self, f"table_tab_{i}") is None:
                    w = self._find_widget_by_name(QTableWidget, f"table_tab_{i}")
                    if w is not None:
                        try:
                            setattr(self, f"table_tab_{i}", w)
                            logger.debug("[StatisticsTab] table_tab_%d 자동 바인딩 (%s)", i, w.objectName())
                        except Exception:
                            pass
                if not hasattr(self, f"text_log_tab_{i}") or getattr(self, f"text_log_tab_{i}") is None:
                    w = self._find_widget_by_name(QTextEdit, f"text_log_tab_{i}")
                    if w is not None:
                        try:
                            setattr(self, f"text_log_tab_{i}", w)
                            logger.debug("[StatisticsTab] text_log_tab_%d 자동 바인딩 (%s)", i, w.objectName())
                        except Exception:
                            pass

        def _find_widget_by_name(self, cls, name: str):
            """Wrapper around findChild with None-safe behavior."""
            try:
                obj = self.findChild(cls, name)
                if obj is not None:
                    return obj
                # sometimes objectName might have different casing or prefixes; fallback search
                for child in self.findChildren(cls):
                    try:
                        if name in (child.objectName() or ""):
                            return child
                    except Exception:
                        continue
            except Exception:
                pass
            return None

        def _find_first_child(self, cls):
            try:
                childs = self.findChildren(cls)
                if childs:
                    return childs[0]
            except Exception:
                pass
            return None

        def _show_ui_warning(self, text: str) -> None:
            """If UI hasn't proper widgets, show a small label so user sees something."""
            try:
                # don't override if actual UI present
                if self._has_core_widgets():
                    return
                layout = QVBoxLayout(self)
                lbl = QLabel(text, self)
                lbl.setStyleSheet("color: red; font-weight: bold;")
                layout.addWidget(lbl)
                self.setLayout(layout)
            except Exception:
                pass

        # -------------------------
        # 뷰 레벨 단순 핸들러 / 헬퍼
        # -------------------------
        def _on_show_all_clicked(self, tab: int) -> None:
            try:
                le = self._search_boxes.get(tab)
                if le and hasattr(le, "clear"):
                    try:
                        le.clear()
                    except Exception:
                        pass
                self.search_text_changed.emit(tab, "")
            except Exception:
                pass

        def _on_load_history_clicked(self) -> None:
            try:
                filename, _ = QFileDialog.getOpenFileName(self, "로그 파일 선택", os.path.expanduser("~"), "Log Files (*.log *.txt);;All Files (*)")
                self.load_history_requested.emit(filename or "")
            except Exception:
                try:
                    self.load_history_requested.emit("")
                except Exception:
                    pass

        def set_status_text(self, text: str) -> None:
            try:
                lbl = getattr(self, "lbl_toolbar_status", None)
                if lbl is not None:
                    lbl.setText(text)
            except Exception:
                pass

        def insert_table_row(self, tab: int, cells: Sequence[Any]) -> None:
            try:
                tbl: Optional[QTableWidget] = self._tables.get(tab)
                if tbl is None or not isinstance(tbl, QTableWidget):
                    return
                col_count = tbl.columnCount()
                if col_count == 0:
                    return
                row = tbl.rowCount()
                tbl.insertRow(row)
                for j in range(min(len(cells), col_count)):
                    txt = "" if cells[j] is None else str(cells[j])
                    it = QTableWidgetItem(txt)
                    if j == 1:
                        lvl = (txt or "").upper()
                        color = None
                        if lvl == "ERROR":
                            color = QColor(239, 68, 68)
                        elif lvl == "WARNING":
                            color = QColor(251, 146, 60)
                        elif lvl == "INFO":
                            color = QColor(34, 197, 94)
                        if color is not None:
                            try:
                                it.setForeground(color)
                            except Exception:
                                pass
                    tbl.setItem(row, j, it)
            except Exception:
                pass

        def clear_tab(self, tab: int) -> None:
            try:
                tbl = self._tables.get(tab)
                if isinstance(tbl, QTableWidget):
                    tbl.setRowCount(0)
                txt = self._raw_texts.get(tab)
                if txt is not None:
                    try:
                        txt.clear()
                    except Exception:
                        pass
            except Exception:
                pass

        def append_raw_lines(self, tab: int, lines: Sequence[str]) -> None:
            try:
                txt = self._raw_texts.get(tab)
                if txt is None:
                    return
                try:
                    for ln in lines:
                        txt.append(str(ln))
                except Exception:
                    try:
                        txt.setPlainText("\n".join(map(str, lines)))
                    except Exception:
                        pass
            except Exception:
                pass

        # 파일 다이얼로그 헬퍼
        def get_open_file_path(self, caption: str = "파일 선택", directory: Optional[str] = None, filter: str = "All Files (*)") -> str:
            try:
                directory = directory or os.path.expanduser("~")
                filename, _ = QFileDialog.getOpenFileName(self, caption, directory, filter)
                return filename or ""
            except Exception:
                return ""

        def get_save_file_path(self, caption: str = "파일 저장", default_name: str = "", filter: str = "All Files (*)") -> str:
            try:
                filename, _ = QFileDialog.getSaveFileName(self, caption, default_name, filter)
                return filename or ""
            except Exception:
                return ""

else:
    class StatisticsTab:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PyQt5 not available; StatisticsTab (View) cannot be created in this environment.")