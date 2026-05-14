# -*- coding: utf-8 -*-
"""
statistics_model.py

- Statistics 탭에서 사용할 모델 및 필터 프록시 모델 구현입니다.
- 모델은 테이블 기반의 read-only 뷰를 가정하고 구현되어 있으며,
  컬럼: 시간, 레벨, 카테고리(비워둠), 모듈, 메시지
- LogFilterProxyModel은 간단한 필터(레벨, 카테고리, 검색)를 제공합니다.
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional
from PyQt5.QtCore import QAbstractTableModel, Qt, QModelIndex, QSortFilterProxyModel, QVariant

# Columns: 시간, 레벨, 카테고리(비워둠), 모듈, 메시지
MODEL_COLUMNS = ["time", "level", "category", "module", "message"]


class StatisticsModel(QAbstractTableModel):
    """테이블 모델: 내부적으로 행(row)의 리스트를 보관"""

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
            # 시간을 왼쪽 정렬, 세로 중앙 정렬
            return Qt.AlignLeft | Qt.AlignVCenter

        if role == Qt.ForegroundRole and key == "level":
            # 레벨별 색상 표시
            lvl = (item.get("level") or "").upper()
            from PyQt5.QtGui import QColor

            if lvl == "ERROR":
                return QColor(239, 68, 68)
            if lvl == "WARNING":
                return QColor(251, 146, 60)
            if lvl == "INFO":
                return QColor(34, 197, 94)
            if lvl == "DEBUG":
                return QColor(148, 163, 184)

        return QVariant()

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        """컬럼 헤더 라벨 반환 (한글)"""
        if role != Qt.DisplayRole:
            return QVariant()
        if orientation == Qt.Horizontal:
            labels = ["시간", "레벨", "카테고리", "모듈", "메시지"]
            if 0 <= section < len(labels):
                return labels[section]
        return QVariant()

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemIsEnabled
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    # API for appending/clearing rows
    def append_rows(self, rows: List[Dict[str, str]]) -> None:
        """여러 행을 한 번에 추가 (model notifications 포함)"""
        if not rows:
            return
        first = len(self._rows)
        last = first + len(rows) - 1
        self.beginInsertRows(QModelIndex(), first, last)
        self._rows.extend(rows)
        self.endInsertRows()

    def clear(self) -> None:
        """모든 행 삭제"""
        if not self._rows:
            return
        self.beginRemoveRows(QModelIndex(), 0, len(self._rows) - 1)
        self._rows.clear()
        self.endRemoveRows()

    def row_data(self, row: int) -> Optional[Dict[str, str]]:
        """지정 행의 데이터(사전) 반환, 범위 밖이면 None"""
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None


class LogFilterProxyModel(QSortFilterProxyModel):
    """
    간단한 필터 프록시 모델
    - filters: level_text (한글 라벨 기준), show_warnings, websocket, pipeline, gap, search_text
    - set_filters로 필터 설정 → invalidateFilter() 호출
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # 필터 상태
        self.level_text: str = ""
        self.show_warnings: bool = True
        # 'websocket' 키와 일치하도록 이름을 websocket으로 사용
        self.websocket: bool = False
        self.pipeline: bool = False
        self.gap: bool = False
        self.search_text: str = ""

    def set_filters(self, filters: Dict[str, Any]) -> None:
        """외부에서 필터 설정을 전달받아 내부 상태를 갱신"""
        try:
            self.level_text = (filters.get("level_text") or "").strip()
            self.show_warnings = bool(filters.get("show_warnings", True))
            self.websocket = bool(filters.get("websocket", False))
            self.pipeline = bool(filters.get("pipeline", False))
            self.gap = bool(filters.get("gap", False))
            self.search_text = (filters.get("search") or "").strip().lower()
            # 모델에 필터 재평가를 알림
            self.invalidateFilter()
        except Exception:
            # 필터 설정 중 에러는 무시(안정성 우선)
            pass

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """각 행이 필터를 통과하는지 결정"""
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

            # 레벨 필터 (한국어 라벨 기준 일부 예시 유지)
            if self.level_text == "에러만":
                if level not in ("ERROR", "CRITICAL"):
                    return False
            elif self.level_text == "경고 이상":
                if level not in ("WARNING", "ERROR", "CRITICAL"):
                    return False

            if not self.show_warnings and level in ("WARNING", "ERROR", "CRITICAL"):
                return False

            # 카테고리(웹소켓/파이프라인/갭) 필터
            if self.websocket:
                if not ("websocket" in module or "ws" in module or "realtime" in module or "socket" in module):
                    return False
            if self.pipeline:
                if "pipeline" not in module and "pipeline" not in message:
                    return False
            if self.gap:
                if "gap" not in module and "gap" not in message:
                    return False

            # 검색 텍스트
            if self.search_text:
                if self.search_text not in module and self.search_text not in message:
                    return False

            return True
        except Exception:
            # 필터 평가 중 오류 발생 시 안전하게 통과 처리
            return True