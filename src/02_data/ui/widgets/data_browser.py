# -*- coding: utf-8 -*-
"""공통 데이터 브라우저 위젯

필터/정렬/페이지네이션/드릴다운을 제공하는 재사용 가능한 위젯.
"""
from __future__ import annotations
import logging
from typing import List, Tuple, Optional

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
        QHeaderView, QLineEdit, QPushButton, QLabel, QDialog, QTextEdit,
        QDialogButtonBox, QSizePolicy, QSpacerItem,
    )
    from PyQt5.QtCore import Qt, pyqtSlot
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

PAGE_SIZE = 100  # 페이지당 행 수


if _HAS_QT:
    class RowDetailDialog(QDialog):
        """행 상세 팝업 다이얼로그."""

        def __init__(self, headers: List[str], row_data: List[str], parent=None):
            super().__init__(parent)
            self.setWindowTitle("📄 행 상세 보기")
            self.resize(600, 400)
            layout = QVBoxLayout(self)

            text = QTextEdit()
            text.setReadOnly(True)
            text.setFontFamily("Consolas")
            lines = []
            for h, v in zip(headers, row_data):
                lines.append(f"[{h}]\n{v}\n")
            text.setPlainText("\n".join(lines))
            layout.addWidget(text)

            buttons = QDialogButtonBox(QDialogButtonBox.Close)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)


    class DataBrowserWidget(QWidget):
        """공통 데이터 브라우저 위젯.

        set_data(headers, rows) 로 데이터를 설정합니다.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self._all_rows: List[Tuple] = []
            self._headers: List[str] = []
            self._filtered_rows: List[Tuple] = []
            self._page: int = 0
            self._sort_col: int = -1
            self._sort_asc: bool = True
            self._build_ui()

        # ------------------------------------------------------------------
        # UI 빌드
        # ------------------------------------------------------------------

        def _build_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(4)

            # 필터 행
            filter_row = QHBoxLayout()
            self._filter_edit = QLineEdit()
            self._filter_edit.setPlaceholderText("🔍 전체 필드 검색 (Enter)")
            self._filter_edit.returnPressed.connect(self._apply_filter)
            filter_row.addWidget(QLabel("필터:"))
            filter_row.addWidget(self._filter_edit)
            btn_clear = QPushButton("지우기")
            btn_clear.setFixedWidth(60)
            btn_clear.clicked.connect(self._clear_filter)
            filter_row.addWidget(btn_clear)
            layout.addLayout(filter_row)

            # 테이블
            self._table = QTableWidget()
            self._table.setAlternatingRowColors(True)
            self._table.setSelectionBehavior(QTableWidget.SelectRows)
            self._table.setEditTriggers(QTableWidget.NoEditTriggers)
            self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            self._table.horizontalHeader().setStretchLastSection(True)
            self._table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
            self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
            self._table.setStyleSheet(
                "QTableWidget { font-size: 9pt; }"
                "QTableWidget::item:selected { background-color: #3B82F6; color: white; }"
            )
            layout.addWidget(self._table)

            # 페이지네이션 행
            page_row = QHBoxLayout()
            self._btn_first = QPushButton("◀◀")
            self._btn_prev  = QPushButton("◀")
            self._btn_next  = QPushButton("▶")
            self._btn_last  = QPushButton("▶▶")
            for btn in (self._btn_first, self._btn_prev, self._btn_next, self._btn_last):
                btn.setFixedWidth(36)
            self._btn_first.clicked.connect(self._go_first)
            self._btn_prev.clicked.connect(self._go_prev)
            self._btn_next.clicked.connect(self._go_next)
            self._btn_last.clicked.connect(self._go_last)
            self._page_label = QLabel("페이지 0 / 0")
            self._page_label.setAlignment(Qt.AlignCenter)
            page_row.addWidget(self._btn_first)
            page_row.addWidget(self._btn_prev)
            page_row.addWidget(self._page_label)
            page_row.addWidget(self._btn_next)
            page_row.addWidget(self._btn_last)
            page_row.addItem(QSpacerItem(20, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
            self._status_label = QLabel("")
            self._status_label.setStyleSheet("color: #6B7280; font-size: 8pt;")
            page_row.addWidget(self._status_label)
            layout.addLayout(page_row)

        # ------------------------------------------------------------------
        # 공개 API
        # ------------------------------------------------------------------

        def set_data(self, headers: List[str], rows: List[Tuple]) -> None:
            """데이터를 설정하고 첫 페이지를 표시합니다."""
            self._headers = list(headers)
            self._all_rows = [tuple(str(v) if v is not None else "" for v in r) for r in rows]
            self._page = 0
            self._sort_col = -1
            self._sort_asc = True
            self._apply_filter()

        def set_status(self, text: str, color: str = "#6B7280") -> None:
            """외부에서 상태 텍스트를 설정합니다."""
            self._status_label.setStyleSheet(f"color: {color}; font-size: 8pt;")
            self._status_label.setText(text)

        # ------------------------------------------------------------------
        # 필터/정렬
        # ------------------------------------------------------------------

        @pyqtSlot()
        def _apply_filter(self) -> None:
            q = self._filter_edit.text().strip().lower()
            if q:
                self._filtered_rows = [
                    r for r in self._all_rows
                    if any(q in str(v).lower() for v in r)
                ]
            else:
                self._filtered_rows = list(self._all_rows)
            if self._sort_col >= 0:
                self._sort_rows()
            self._page = 0
            self._update_page()

        @pyqtSlot()
        def _clear_filter(self) -> None:
            self._filter_edit.clear()
            self._apply_filter()

        @pyqtSlot(int)
        def _on_header_clicked(self, logical_index: int) -> None:
            if self._sort_col == logical_index:
                self._sort_asc = not self._sort_asc
            else:
                self._sort_col = logical_index
                self._sort_asc = True
            self._sort_rows()
            self._page = 0
            self._update_page()

        def _sort_rows(self) -> None:
            col = self._sort_col
            if col < 0 or col >= len(self._headers):
                return
            def _key(r):
                v = r[col] if col < len(r) else ""
                try:
                    return (0, float(v))
                except (ValueError, TypeError):
                    return (1, str(v).lower())
            self._filtered_rows.sort(key=_key, reverse=not self._sort_asc)

        # ------------------------------------------------------------------
        # 페이지네이션
        # ------------------------------------------------------------------

        @pyqtSlot()
        def _go_first(self) -> None:
            self._page = 0
            self._update_page()

        @pyqtSlot()
        def _go_prev(self) -> None:
            if self._page > 0:
                self._page -= 1
                self._update_page()

        @pyqtSlot()
        def _go_next(self) -> None:
            total_pages = max(1, (len(self._filtered_rows) + PAGE_SIZE - 1) // PAGE_SIZE)
            if self._page < total_pages - 1:
                self._page += 1
                self._update_page()

        @pyqtSlot()
        def _go_last(self) -> None:
            total_pages = max(1, (len(self._filtered_rows) + PAGE_SIZE - 1) // PAGE_SIZE)
            self._page = total_pages - 1
            self._update_page()

        def _update_page(self) -> None:
            rows = self._filtered_rows
            total = len(rows)
            total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            self._page = max(0, min(self._page, total_pages - 1))

            start = self._page * PAGE_SIZE
            end   = min(start + PAGE_SIZE, total)
            page_rows = rows[start:end]

            self._table.setColumnCount(len(self._headers))
            self._table.setHorizontalHeaderLabels(self._headers)
            self._table.setRowCount(len(page_rows))

            for r_idx, row in enumerate(page_rows):
                for c_idx, val in enumerate(row):
                    item = QTableWidgetItem(str(val))
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self._table.setItem(r_idx, c_idx, item)

            # 정렬 방향 표시
            if self._sort_col >= 0:
                order = Qt.AscendingOrder if self._sort_asc else Qt.DescendingOrder
                self._table.horizontalHeader().setSortIndicator(self._sort_col, order)
                self._table.horizontalHeader().setSortIndicatorShown(True)
            else:
                self._table.horizontalHeader().setSortIndicatorShown(False)

            self._page_label.setText(f"페이지 {self._page + 1} / {total_pages}")
            filtered_note = f" (필터 후 {total}행)" if len(self._all_rows) != total else ""
            self._status_label.setText(
                f"총 {len(self._all_rows):,}행{filtered_note}  |  "
                f"표시: {start+1 if page_rows else 0}–{end}"
            )

            # 버튼 활성/비활성
            self._btn_first.setEnabled(self._page > 0)
            self._btn_prev.setEnabled(self._page > 0)
            self._btn_next.setEnabled(self._page < total_pages - 1)
            self._btn_last.setEnabled(self._page < total_pages - 1)

        # ------------------------------------------------------------------
        # 드릴다운 (행 상세)
        # ------------------------------------------------------------------

        @pyqtSlot(int, int)
        def _on_cell_double_clicked(self, row: int, col: int) -> None:
            if not self._headers:
                return
            row_data = [
                self._table.item(row, c).text() if self._table.item(row, c) else ""
                for c in range(len(self._headers))
            ]
            dlg = RowDetailDialog(self._headers, row_data, parent=self)
            dlg.exec_()

else:
    class DataBrowserWidget:  # type: ignore[no-redef]
        def __init__(self, parent=None): pass
        def set_data(self, headers, rows): pass
        def set_status(self, text, color="#6B7280"): pass

    class RowDetailDialog:  # type: ignore[no-redef]
        def __init__(self, headers, row_data, parent=None): pass
