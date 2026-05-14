# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Dict, Any, Optional
from PyQt5.QtCore import QAbstractTableModel, Qt, QModelIndex, QSortFilterProxyModel, QVariant

# Columns: 시간, 레벨, 카테고리(비워둠), 모듈, 메시지
MODEL_COLUMNS = ["time", "level", "category", "module", "message"]

class StatisticsModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: List[Dict[str, str]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(MODEL_COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self._rows):
            return QVariant()
        item = self._rows[row]
        key = MODEL_COLUMNS[col]
        if role == Qt.DisplayRole:
            return item.get(key, "")
        if role == Qt.TextAlignmentRole:
            # 시간을 왼쪽(밀도 맞춤), 숫자 등은 가운데 등 필요시 조정
            return Qt.AlignLeft | Qt.AlignVCenter
        if role == Qt.ForegroundRole and key == "level":
            lvl = (item.get("level") or "").upper()
            if lvl == "ERROR":
                from PyQt5.QtGui import QColor
                return QColor(239, 68, 68)
            if lvl == "WARNING":
                from PyQt5.QtGui import QColor
                return QColor(251, 146, 60)
            if lvl == "INFO":
                from PyQt5.QtGui import QColor
                return QColor(34, 197, 94)
            if lvl == "DEBUG":
                from PyQt5.QtGui import QColor
                return QColor(148, 163, 184)
        return QVariant()

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return QVariant()
        if orientation == Qt.Horizontal:
            labels = ["시간", "레��", "카테고리", "모듈", "메시지"]
            if 0 <= section < len(labels):
                return labels[section]
        return QVariant()

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemIsEnabled
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    # API for appending/clearing rows
    def append_rows(self, rows: List[Dict[str, str]]) -> None:
        if not rows:
            return
        first = len(self._rows)
        last = first + len(rows) - 1
        self.beginInsertRows(QModelIndex(), first, last)
        self._rows.extend(rows)
        self.endInsertRows()

    def clear(self) -> None:
        if not self._rows:
            return
        self.beginRemoveRows(QModelIndex(), 0, len(self._rows) - 1)
        self._rows.clear()
        self.endRemoveRows()

    def row_data(self, row: int) -> Optional[Dict[str, str]]:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

class LogFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        # filters
        self.level_text: str = ""
        self.show_warnings: bool = True
        self.webhook: bool = False
        self.pipeline: bool = False
        self.gap: bool = False
        self.search_text: str = ""

    def set_filters(self, filters: Dict[str, Any]) -> None:
        try:
            self.level_text = (filters.get("level_text") or "").strip()
            self.show_warnings = bool(filters.get("show_warnings", True))
            self.webhook = bool(filters.get("websocket", False))
            self.pipeline = bool(filters.get("pipeline", False))
            self.gap = bool(filters.get("gap", False))
            self.search_text = (filters.get("search") or "").strip().lower()
            # tell model to re-evaluate
            self.invalidateFilter()
        except Exception:
            pass

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        # access source model row
        try:
            src = self.sourceModel()
            if src is None:
                return True
            row_data = src.row_data(source_row)
            if row_data is None:
                return True
            level = (row_data.get("level") or "INFO").upper()
            module = (row_data.get("module") or "").lower()
            message = (row_data.get("message") or "").lower()

            # level filters
            if self.level_text == "에러만":
                if level not in ("ERROR", "CRITICAL"):
                    return False
            elif self.level_text == "경고 이상":
                if level not in ("WARNING", "ERROR", "CRITICAL"):
                    return False
            if not self.show_warnings and level in ("WARNING", "ERROR", "CRITICAL"):
                return False

            # category filters
            if self.webhook:
                if not ("websocket" in module or "ws" in module or "realtime" in module or "socket" in module):
                    return False
            if self.pipeline:
                if "pipeline" not in module and "pipeline" not in message:
                    return False
            if self.gap:
                if "gap" not in module and "gap" not in message:
                    return False

            # search
            if self.search_text:
                if self.search_text not in module and self.search_text not in message:
                    return False

            return True
        except Exception:
            return True