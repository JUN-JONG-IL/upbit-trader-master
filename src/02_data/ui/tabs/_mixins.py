# -*- coding: utf-8 -*-
"""탭 공통 믹스인 — 모든 탭 위젯에서 공유하는 유틸리티"""
from __future__ import annotations


class TableCopyMixin:
    """테이블 셀 복사(Ctrl+C)를 활성화하는 믹스인.

    QWidget 기반 탭 클래스에 다중 상속으로 추가합니다.
    예::

        class MyTab(TableCopyMixin, QWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                ...
                self._setup_table_copy()
    """

    def _setup_table_copy(self) -> None:
        """테이블 다중 행 복사 활성화 (Ctrl+C).

        ``table_`` 로 시작하는 모든 QTableWidget 속성에
        ExtendedSelection(다중 행 선택) 모드와 행 단위 선택을 적용합니다.
        """
        try:
            from PyQt5.QtWidgets import QAbstractItemView
        except ImportError:
            return

        for attr_name in dir(self):
            if attr_name.startswith("table_"):
                table = getattr(self, attr_name, None)
                if table is not None and hasattr(table, "setSelectionMode"):
                    # 다중 행 선택 (Ctrl/Shift 클릭)
                    table.setSelectionMode(QAbstractItemView.ExtendedSelection)
                    # 행 단위로 선택
                    table.setSelectionBehavior(QAbstractItemView.SelectRows)
