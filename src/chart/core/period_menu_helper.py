"""
Helper to build a period (timeframe) menu using QWidgetAction containing
full-row clickable checkboxes so toggling doesn't close the menu.
"""
from typing import List, Tuple, Dict, Optional

try:
    from PyQt5.QtWidgets import (
        QWidget, QWidgetAction, QCheckBox, QHBoxLayout, 
        QMenu, QVBoxLayout, QLabel
    )
    from PyQt5.QtCore import Qt, pyqtSignal
except Exception:
    from utils.qt_stub import QtCore, QtGui, QtWidgets
    QWidget = QtWidgets.QWidget
    QWidgetAction = QtWidgets.QWidgetAction
    QCheckBox = QtWidgets.QCheckBox
    QHBoxLayout = QtWidgets.QHBoxLayout
    QMenu = QtWidgets.QMenu
    QVBoxLayout = QtWidgets.QVBoxLayout
    QLabel = QtWidgets.QLabel
    Qt = QtCore.Qt
    pyqtSignal = QtCore.pyqtSignal


class PeriodCheckboxWidget(QWidget):
    """개별 Period 체크박스 위젯"""
    
    toggled = pyqtSignal(str, bool)
    
    def __init__(self, period_key: str, period_label: str, checked: bool = False, parent=None):
        super().__init__(parent)
        self.period_key = period_key
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        self.checkbox = QCheckBox(period_label)
        self.checkbox.setChecked(checked)
        self.checkbox.stateChanged.connect(self._on_toggled)
        
        layout.addWidget(self.checkbox)
        
        self.setMinimumHeight(30)
        self.setCursor(Qt.PointingHandCursor)
    
    def _on_toggled(self, state):
        checked = (state == Qt.Checked)
        self.toggled.emit(self.period_key, checked)
    
    def mousePressEvent(self, event):
        self.checkbox.setChecked(not self.checkbox.isChecked())
        super().mousePressEvent(event)
    
    def isChecked(self) -> bool:
        return self.checkbox.isChecked()
    
    def setChecked(self, checked: bool):
        self.checkbox.setChecked(checked)


def build_period_menu(
    parent,
    periods: List[Tuple[str, str]],
    initial_checked=None,
    on_change_callback=None
) -> Tuple[QMenu, Dict[str, PeriodCheckboxWidget]]:
    """
    Period 선택 메뉴 생성

    Args:
        parent: 메뉴의 부모 QWidget (ChartWidget 등)
        periods: [(label, key), ...] 형식의 period 목록
        initial_checked: 초기 체크 상태 key 컬렉션 (list/set)
        on_change_callback: 체크 상태 변경 시 호출할 콜백 함수(key, checked)

    Returns:
        (QMenu, {key: PeriodCheckboxWidget}) 튜플
    """
    if initial_checked is None:
        initial_checked = []

    menu = QMenu(parent)
    widgets = {}

    for period_label, period_key in periods:
        checked = period_key in initial_checked

        widget = PeriodCheckboxWidget(period_key, period_label, checked)

        if on_change_callback:
            widget.toggled.connect(on_change_callback)

        action = QWidgetAction(menu)
        action.setDefaultWidget(widget)
        menu.addAction(action)

        widgets[period_key] = widget

    return menu, widgets


def get_checked_periods(widgets: Dict[str, PeriodCheckboxWidget]) -> List[str]:
    """체크된 period key 리스트 반환"""
    return [key for key, widget in widgets.items() if widget.isChecked()]


def set_checked_periods(widgets: Dict[str, PeriodCheckboxWidget], checked_keys: List[str]):
    """특정 period들만 체크"""
    for key, widget in widgets.items():
        widget.setChecked(key in checked_keys)