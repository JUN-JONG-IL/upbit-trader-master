# -*- coding: utf-8 -*-
"""
Drawing Tools - 차트 드로잉 툴 모음
추세선, 피보나치, 채널, 사각형 등 그리기 도구

Unified from widgets/advanced/logic/drawing_tools.py → chart/drawing_tools.py
"""
from enum import Enum
try:
    from PyQt5.QtWidgets import QWidget, QAction
    from PyQt5.QtCore import Qt, QPointF
except Exception:
    from utils.qt_stub import QtCore, QtWidgets  # type: ignore[assignment]
    QWidget = QtWidgets.QWidget  # type: ignore[attr-defined]
    QAction = QtWidgets.QAction  # type: ignore[attr-defined]
    Qt = QtCore.Qt  # type: ignore[attr-defined]
    QPointF = QtCore.QPointF  # type: ignore[attr-defined]


class DrawingToolType(Enum):
    """드로잉 툴 타입"""
    NONE = "none"
    TREND_LINE = "trend_line"
    HORIZONTAL_LINE = "horizontal_line"
    VERTICAL_LINE = "vertical_line"
    FIBONACCI = "fibonacci"
    CHANNEL = "channel"
    RECTANGLE = "rectangle"
    ELLIPSE = "ellipse"
    ARROW = "arrow"
    TEXT = "text"
    PITCHFORK = "pitchfork"
    GANN_FAN = "gann_fan"
    BRUSH = "brush"
    ERASER = "eraser"
    MEASURE = "measure"
    ZOOM = "zoom"
    PAN = "pan"


class DrawingTools:
    """드로잉 툴 관리자"""

    ALL_TOOLS = [
        (DrawingToolType.TREND_LINE, "추세선"),
        (DrawingToolType.HORIZONTAL_LINE, "수평선"),
        (DrawingToolType.VERTICAL_LINE, "수직선"),
        (DrawingToolType.FIBONACCI, "피보나치"),
        (DrawingToolType.CHANNEL, "채널"),
        (DrawingToolType.RECTANGLE, "사각형"),
        (DrawingToolType.ELLIPSE, "타원"),
        (DrawingToolType.ARROW, "화살표"),
        (DrawingToolType.TEXT, "텍스트"),
        (DrawingToolType.PITCHFORK, "앤드류 피치포크"),
        (DrawingToolType.GANN_FAN, "갠 팬"),
        (DrawingToolType.BRUSH, "브러시"),
        (DrawingToolType.ERASER, "지우개"),
        (DrawingToolType.MEASURE, "측정"),
        (DrawingToolType.ZOOM, "줌"),
        (DrawingToolType.PAN, "이동"),
    ]

    def __init__(self):
        self._active_tool: DrawingToolType = DrawingToolType.NONE
        self._drawings: list = []

    @property
    def active_tool(self) -> DrawingToolType:
        return self._active_tool

    def set_tool(self, tool: DrawingToolType) -> None:
        """드로잉 툴 설정"""
        self._active_tool = tool

    def clear_all(self) -> None:
        """모든 드로잉 제거"""
        self._drawings.clear()
