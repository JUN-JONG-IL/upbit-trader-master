#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
주문 내역(체결/미체결) 테이블을 표시하는 위젯입니다.

[Responsibilities]
- order_history.ui 로드
- 주문 내역 테이블 컬럼 설정 및 데이터 업데이트
- 주문 취소 버튼 이벤트 처리

[UI Binding]
- order_history.ui (src/10_trade/ui/order_history/order_history.ui)
"""
from __future__ import annotations

import os

try:
    from PyQt5.QtWidgets import QWidget
    from PyQt5 import uic
except Exception:
    class QWidget:  # type: ignore[no-redef]
        """Minimal QWidget stub for non-GUI environments."""
        def __init__(self, parent=None):
            pass

    class uic:  # type: ignore[no-redef]
        @staticmethod
        def loadUi(path, widget):
            pass


class OrderHistoryWidget(QWidget):
    """주문 내역 표시 위젯."""

    def __init__(self, parent=None):
        super().__init__(parent)
        ui_path = os.path.join(os.path.dirname(__file__), "order_history.ui")
        if os.path.exists(ui_path):
            uic.loadUi(ui_path, self)

    def refresh(self) -> None:
        """주문 내역 갱신."""
        pass

    def set_orders(self, orders: list) -> None:
        """주문 목록을 테이블에 표시합니다.

        Args:
            orders: 주문 딕셔너리 리스트.
        """
        pass
