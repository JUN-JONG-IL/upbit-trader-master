# -*- coding: utf-8 -*-
"""
StatisticsTab (View 전용)
- 이 파일은 UI(.ui)만 로드하고, 사용자 입력을 pyqtSignal로 전파합니다.
- 절대 비즈니스 로직(타이머, 로그 수집/포워딩, 파일 I/O, DB 등)을 포함하지 않습니다.
- Controller는 이 View를 import하여 시그널을 연결하고 모든 로직을 수행합니다.
- 간단한 UI 헬퍼(파일 다이얼로그 열기, 테이블/Raw 조작 등)를 제공함.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Sequence
import os

# PyQt import (가용성 검사)
try:
    from PyQt5 import uic
    from PyQt5.QtCore import pyqtSignal, Qt
    from PyQt5.QtGui import QColor
    from PyQt5.QtWidgets import (
        QWidget, QFileDialog, QAbstractItemView, QHeaderView,
        QTableView, QTableWidget, QTableWidgetItem, QTextEdit
    )
    _HAS_QT = True
except Exception:
    _HAS_QT = False


if _HAS_QT:
    class StatisticsTab(QWidget):
        """
        View 전용 클래스.
        - UI 요소 접근(예: btn_pause, table_tab_1 등)은 .ui에 정의된 objectName을 사용합니다.
        - 모든 사용자 액션은 시그널로 방출됩니다.
        - Controller는 시그널을 받아 비즈니스 로직(로그 수집, 파일 로드/저장, 타이머 등)을 수행합니다.
        """

        # --- Signals (권장 단일 설계: 뷰는 이벤트만 발생시킴) ---
        load_history_requested = pyqtSignal(str)      # 파일 경로(빈 문자열이면 기본 후보 사용 요청)
        settings_requested = pyqtSignal()            # 설정 다이얼로그 요청
        pause_toggled = pyqtSignal()                 # 툴바 일시정지/재개 클릭
        manual_refresh_requested = pyqtSignal()      # 수동 새로고침 요청
        export_tab_requested = pyqtSignal(int)       # 탭별 내보내기 요청 (컨트롤러에서 저장 다이���로그 열기를 권장)
        export_tab_with_path = pyqtSignal(int, str)  # (옵션) 뷰가 직접 경로를 골라서 보낼 때
        export_all_requested = pyqtSignal()          # 전체 내보내기 요청
        clear_tab_requested = pyqtSignal(int)        # 탭별 지우기 요청
        clear_all_requested = pyqtSignal()           # 전체 지우기 요청
        show_all_tab_requested = pyqtSignal(int)     # 탭별 '전체 보기' 요청
        active_tab_changed = pyqtSignal(int)         # 탭 변경 시 발생 (1..7)
        search_text_changed = pyqtSignal(int, str)   # 탭, 검색어 소문자화된 값
        # 외부 로그 입력을 뷰로 직접 전달하려는 경우(권장 아님 — controller에서 처리 권장)
        #request_append_log = pyqtSignal(dict)      # (제거 권장)

        def __init__(self, parent=None, ui_filename: Optional[str] = None):
            super().__init__(parent)

            # .ui 파일 경로 결정 (기본: 같은 디렉토리의 statistics_tab.ui)
            if ui_filename is None:
                ui_filename = os.path.join(os.path.dirname(__file__), "statistics_tab.ui")

            # UI 로드 (Designer 원본 유지)
            try:
                uic.loadUi(ui_filename, self)
            except Exception as exc:
                # UI 로드 오류는 예외로 상위에서 처리하도록 재전파
                raise RuntimeError(f"StatisticsTab: UI 로드 실패: {ui_filename}: {exc}") from exc

            # 내부 캐시: 위젯 참조 모음 (탭 1..7)
            self._tables: Dict[int, Optional[object]] = {}
            self._raw_texts: Dict[int, Optional[QTextEdit]] = {}
            self._search_boxes: Dict[int, Optional[object]] = {}
            self._chk_autoscrolls: Dict[int, Optional[object]] = {}

            for i in range(1, 8):
                self._tables[i] = getattr(self, f"table_tab_{i}", None)
                self._raw_texts[i] = getattr(self, f"text_log_tab_{i}", None)
                self._search_boxes[i] = getattr(self, f"le_tab{i}_search", None)
                self._chk_autoscrolls[i] = getattr(self, f"chk_tab{i}_autoscroll", None)

                # 검색어 변경 시 시그널 발행 (간단 유효성: string)
                if self._search_boxes[i] is not None:
                    try:
                        self._search_boxes[i].textChanged.connect((lambda t: (lambda text: self._on_search_changed(t, text)))(i))
                    except Exception:
                        pass

                # per-tab 버튼 연결(가능하면)
                try:
                    btn_show_all = getattr(self, f"btn_tab{i}_show_all", None)
                    if btn_show_all is not None:
                        btn_show_all.clicked.connect((lambda t: (lambda: self.show_all_tab_requested.emit(t)))(i))
                    btn_export = getattr(self, f"btn_tab{i}_export", None)
                    if btn_export is not None:
                        btn_export.clicked.connect((lambda t: (lambda: self.export_tab_requested.emit(t)))(i))
                    btn_clear = getattr(self, f"btn_tab{i}_clear", None)
                    if btn_clear is not None:
                        btn_clear.clicked.connect((lambda t: (lambda: self.clear_tab_requested.emit(t)))(i))
                except Exception:
                    pass

            # 툴바 버튼 연결
            try:
                btn_pause = getattr(self, "btn_pause", None)
                if btn_pause is not None:
                    btn_pause.clicked.connect(self._on_pause_clicked)
                btn_refresh = getattr(self, "btn_refresh", None)
                if btn_refresh is not None:
                    btn_refresh.clicked.connect(lambda: self.manual_refresh_requested.emit())
                btn_export_all = getattr(self, "btn_export_all", None)
                if btn_export_all is not None:
                    btn_export_all.clicked.connect(lambda: self.export_all_requested.emit())
                btn_clear_all = getattr(self, "btn_clear_all", None)
                if btn_clear_all is not None:
                    btn_clear_all.clicked.connect(lambda: self.clear_all_requested.emit())
                btn_settings = getattr(self, "btn_settings", None)
                if btn_settings is not None:
                    btn_settings.clicked.connect(lambda: self.settings_requested.emit())
                btn_load_history = getattr(self, "btn_load_history", None)
                if btn_load_history is not None:
                    btn_load_history.clicked.connect(self._on_load_history_clicked)
            except Exception:
                pass

            # 메인 탭 위젯 훅(활성 탭 변경 시 시그널 발행)
            try:
                main_tabs = getattr(self, "tabWidget_main_tabs", None)
                if main_tabs is not None:
                    main_tabs.currentChanged.connect(lambda idx: self.active_tab_changed.emit(int(idx) + 1))
            except Exception:
                pass

            # UI 초기 상태 설정 보조
            self.set_status_text("상태: 대기")
            # Pause 버튼 라벨 초기화는 컨트롤러에서 설정할 수 있으므로 뷰는 기본 텍스트만 유지

        # -------------------------
        # Internal UI handlers
        # -------------------------
        def _on_pause_clicked(self) -> None:
            # 단순히 시그널을 방출 — 컨트롤러가 현재 상태를 토글/관리함
            try:
                self.pause_toggled.emit()
            except Exception:
                pass

        def _on_load_history_clicked(self) -> None:
            """
            뷰 레벨에서 파일 선택 다이얼로그를 열고 선택된 경로(또는 빈 문자열)를 emit합니다.
            - Controller는 받은 경로를 사용하여 파일을 읽고 처리합니다.
            """
            try:
                filename, _ = QFileDialog.getOpenFileName(self, "로그 파일 선택", os.path.expanduser("~"), "Log Files (*.log *.txt);;All Files (*)")
                # 선택되지 않으면 빈 문자열을 보내서 '자동 후보' 사용을 요청할 수도 있습니다.
                path = filename or ""
                self.load_history_requested.emit(path)
            except Exception:
                # 실패시 빈 문자열로 요청을 보냄
                try:
                    self.load_history_requested.emit("")
                except Exception:
                    pass

        def _on_search_changed(self, tab: int, text: str) -> None:
            try:
                txt = (text or "").strip().lower()
                self.search_text_changed.emit(tab, txt)
            except Exception:
                pass

        # -------------------------
        # View → Controller 보조 메서드 (부작용 적음)
        # Controller는 이 메서드들을 호출하여 UI를 갱신합니다.
        # -------------------------
        def set_status_text(self, text: str) -> None:
            """툴바의 상태 라벨을 안전하게 변경합니다."""
            try:
                lbl = getattr(self, "lbl_toolbar_status", None)
                if lbl is not None:
                    lbl.setText(text)
            except Exception:
                pass

        def set_pause_button_text(self, text: str) -> None:
            """btn_pause 텍스트를 설정합니다 (예: '일시정지' / '재개')."""
            try:
                btn = getattr(self, "btn_pause", None)
                if btn is not None:
                    btn.setText(text)
            except Exception:
                pass

        def get_active_tab(self) -> int:
            try:
                idx = int(getattr(self, "tabWidget_main_tabs", None).currentIndex())
                return max(1, min(7, idx + 1))
            except Exception:
                return 1

        def clear_tab(self, tab: int) -> None:
            """뷰 내부에서 테이블과 raw 뷰를 비웁니다."""
            try:
                tbl = self._tables.get(tab)
                if isinstance(tbl, QTableWidget):
                    try:
                        tbl.setRowCount(0)
                    except Exception:
                        pass
                text = self._raw_texts.get(tab)
                if text is not None:
                    try:
                        text.clear()
                    except Exception:
                        pass
            except Exception:
                pass

        def clear_all_tabs(self) -> None:
            for t in range(1, 8):
                self.clear_tab(t)

        def insert_table_row(self, tab: int, cells: Sequence[Any]) -> None:
            """
            테이블에 한 행을 추가합니다. cells는 문자열 리스트 또는 변환 가능한 시퀀스여야 함.
            - 뷰는 단순히 텍스트를 넣습니다. 색상 등의 표현은 최소한으로 허용.
            """
            try:
                tbl = self._tables.get(tab)
                if tbl is None:
                    return
                if isinstance(tbl, QTableWidget):
                    col_count = tbl.columnCount()
                    if col_count == 0:
                        return
                    row = tbl.rowCount()
                    tbl.insertRow(row)
                    for j in range(min(len(cells), col_count)):
                        try:
                            text = "" if cells[j] is None else str(cells[j])
                            it = QTableWidgetItem(text)
                            # 간단한 레벨 색상(옵션 — 뷰에서만 표시)
                            if j == 1:
                                lvl = (text or "").upper()
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
                            tbl.setItem(row, j, it)
                        except Exception:
                            pass
                else:
                    # 모델/뷰(QTableView)인 경우는 controller가 모델을 관리하므로 뷰 레벨에서 건드리지 않습니다.
                    return
            except Exception:
                pass

        def set_table_rows(self, tab: int, rows: Sequence[Sequence[Any]]) -> None:
            """테이블을 전체 교체합니다(디자이너 컬럼이 없는 경우 동작하지 않음)."""
            try:
                tbl = self._tables.get(tab)
                if tbl is None or not isinstance(tbl, QTableWidget):
                    return
                col_count = tbl.columnCount()
                if col_count == 0:
                    return
                tbl.setRowCount(0)
                for row_cells in rows:
                    self.insert_table_row(tab, row_cells)
            except Exception:
                pass

        def append_raw_lines(self, tab: int, lines: Sequence[str]) -> None:
            """Raw 텍스트 박스에 여러 줄을 append 합니다."""
            try:
                txt = self._raw_texts.get(tab)
                if txt is not None:
                    try:
                        for ln in lines:
                            txt.append(str(ln))
                    except Exception:
                        # fallback: 전체 덮어쓰기
                        try:
                            txt.append("\n".join(map(str, lines)))
                        except Exception:
                            pass
            except Exception:
                pass

        def clear_raw(self, tab: int) -> None:
            try:
                txt = self._raw_texts.get(tab)
                if txt is not None:
                    txt.clear()
            except Exception:
                pass

        # -------------------------
        # File dialog helpers (Controller가 호출할 수 있음)
        # -------------------------
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
    # PyQt가 없는 환경에서는 뷰를 생성할 수 없음을 명확히 알립니다.
    class StatisticsTab:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PyQt5 not available; StatisticsTab (View) cannot be created in this environment.")