# -*- coding: utf-8 -*-
"""
StatisticsTab (View 전용, 경량)
- UI(.ui) 로드 + pyqtSignal 발행 + 최소한의 UI 헬퍼만 포함.
- 비즈니스 로직(타이머/버퍼/IO/DB)은 Controller에서 처리하세요.
"""
from __future__ import annotations
import os
import logging
from typing import Any, Optional, Sequence
try:
    from PyQt5 import uic
    from PyQt5.QtCore import pyqtSignal
    from PyQt5.QtWidgets import QWidget, QFileDialog, QTableWidget, QTableWidgetItem, QTextEdit
    from PyQt5.QtGui import QColor
    _HAS_QT = True
except Exception:
    _HAS_QT = False

logger = logging.getLogger(__name__)

# --- 간단한 안전한 load_ui_with_tab_fix 로더 시도 (절대 import or 파일 fallback) ---
load_ui_with_tab_fix = None
try:
    # 프로젝트에서 src를 패키지 루트로 쓸 때
    import importlib
    try:
        mod = importlib.import_module("src.02_data.ui_loader")
        load_ui_with_tab_fix = getattr(mod, "load_ui_with_tab_fix", None)
    except Exception:
        # 파일 경로 fallback: src/02_data/ui_loader.py 예상 위치 두 곳 시도
        import importlib.util
        candidates = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "ui_loader.py")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "ui_loader.py")),
        ]
        for p in candidates:
            try:
                if os.path.exists(p):
                    spec = importlib.util.spec_from_file_location("ui_loader_local", p)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        load_ui_with_tab_fix = getattr(mod, "load_ui_with_tab_fix", None)
                        if load_ui_with_tab_fix:
                            break
            except Exception:
                load_ui_with_tab_fix = None
except Exception:
    load_ui_with_tab_fix = None
# -------------------------------------------------------------------------

if _HAS_QT:
    class StatisticsTab(QWidget):
        # Signals (뷰는 이벤트만 방출)
        load_history_requested = pyqtSignal(str)      # 경로 지정(빈 문자열이면 기본 후보)
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
            if ui_filename is None:
                ui_filename = os.path.join(os.path.dirname(__file__), "statistics_tab.ui")

            # UI 로드: 보정함수 우선 -> uic.loadUi 폴백
            ui_loaded = False
            if load_ui_with_tab_fix is not None:
                try:
                    load_ui_with_tab_fix(ui_filename, self)
                    ui_loaded = True
                    logger.debug("[StatisticsTab] UI loaded via load_ui_with_tab_fix")
                except Exception as e:
                    logger.debug("[StatisticsTab] load_ui_with_tab_fix failed: %s", e)
            if not ui_loaded:
                try:
                    uic.loadUi(ui_filename, self)
                    ui_loaded = True
                    logger.debug("[StatisticsTab] UI loaded via uic.loadUi")
                except Exception as e:
                    logger.warning("[StatisticsTab] uic.loadUi failed: %s", e)

            if not hasattr(self, "tabWidget_main_tabs"):
                logger.warning("[StatisticsTab] 핵심 위젯(tabWidget_main_tabs) 누락 - .ui를 확인하세요")

            # 위젯 참조 캐시 (간단)
            self._tables = {i: getattr(self, f"table_tab_{i}", None) for i in range(1, 8)}
            self._raw_texts = {i: getattr(self, f"text_log_tab_{i}", None) for i in range(1, 8)}
            self._search_boxes = {i: getattr(self, f"le_tab{i}_search", None) for i in range(1, 8)}

            # 시그널 연결(뷰 레벨)
            for i in range(1, 8):
                le = self._search_boxes.get(i)
                if le is not None:
                    try:
                        le.textChanged.connect((lambda t: (lambda txt: self.search_text_changed.emit(t, (txt or "").strip().lower())))(i))
                    except Exception:
                        pass
                # per-tab buttons (existence-checked)
                try:
                    btn_show_all = getattr(self, f"btn_tab{i}_show_all", None)
                    if btn_show_all:
                        btn_show_all.clicked.connect((lambda t: (lambda: self._on_show_all_clicked(t)))(i))
                    btn_export = getattr(self, f"btn_tab{i}_export", None)
                    if btn_export:
                        btn_export.clicked.connect((lambda t: (lambda: self.export_tab_requested.emit(t)))(i))
                    btn_clear = getattr(self, f"btn_tab{i}_clear", None)
                    if btn_clear:
                        btn_clear.clicked.connect((lambda t: (lambda: self.clear_tab_requested.emit(t)))(i))
                except Exception:
                    pass

            # toolbar
            try:
                btn_pause = getattr(self, "btn_pause", None)
                if btn_pause:
                    btn_pause.clicked.connect(lambda: self.pause_toggled.emit())
                btn_refresh = getattr(self, "btn_refresh", None)
                if btn_refresh:
                    btn_refresh.clicked.connect(lambda: self.manual_refresh_requested.emit())
                btn_export_all = getattr(self, "btn_export_all", None)
                if btn_export_all:
                    btn_export_all.clicked.connect(lambda: self.export_all_requested.emit())
                btn_clear_all = getattr(self, "btn_clear_all", None)
                if btn_clear_all:
                    btn_clear_all.clicked.connect(lambda: self.clear_all_requested.emit())
                btn_load_history = getattr(self, "btn_load_history", None)
                if btn_load_history:
                    btn_load_history.clicked.connect(self._on_load_history_clicked)
            except Exception:
                pass

            # main tab change -> active_tab_changed
            try:
                main_tabs = getattr(self, "tabWidget_main_tabs", None)
                if main_tabs:
                    main_tabs.currentChanged.connect(lambda idx: self.active_tab_changed.emit(int(idx) + 1))
            except Exception:
                pass

            # 초기 상태 텍스트
            self.set_status_text("상태: 대기")

        # 뷰 레벨 핸들러(간단)
        def _on_show_all_clicked(self, tab: int) -> None:
            # 뷰는 단순히 시그널 방출(Controller가 해석)
            try:
                # Clear search box visually
                le = self._search_boxes.get(tab)
                if le:
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

        # View → Controller helper methods (minimal, side-effect 적음)
        def set_status_text(self, text: str) -> None:
            try:
                lbl = getattr(self, "lbl_toolbar_status", None)
                if lbl:
                    lbl.setText(text)
            except Exception:
                pass

        def insert_table_row(self, tab: int, cells: Sequence[Any]) -> None:
            try:
                tbl = self._tables.get(tab)
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