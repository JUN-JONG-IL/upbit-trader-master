#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ClickHouse 성능 메트릭 탭 위젯"""

import os
import logging

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QHeaderView
    from PyQt5.QtCore import QTimer, Qt
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

_UI_FILE = os.path.join(os.path.dirname(__file__), "performance_tab.ui")

# 관심 메트릭 이름 → 한국어 설명 매핑
_METRIC_DESCRIPTIONS = {
    "Query": "현재 실행 중인 쿼리 수",
    "Merge": "백그라운드 병합 수",
    "ReplicatedFetch": "복제 패치 수",
    "ReplicatedSend": "복제 전송 수",
    "BackgroundPoolTask": "백그라운드 풀 태스크 수",
    "MemoryTracking": "현재 메모리 추적 바이트",
    "DiskSpaceReservedForMerge": "병합용 예약 디스크 공간",
    "OpenFileForRead": "읽기 위해 열린 파일 수",
    "OpenFileForWrite": "쓰기 위해 열린 파일 수",
}


class PerformanceTab(QWidget if _HAS_QT else object):
    """ClickHouse 실시간 성능 메트릭을 표시하는 탭 위젯.

    1초마다 system.metrics 테이블을 조회하여 쿼리 수, 병합 수,
    메모리 사용량 등 주요 성능 지표를 갱신합니다.
    """

    def __init__(self, client=None, parent=None, conn_params=None):
        """초기화.

        Args:
            client: ClickHouse HTTP 클라이언트 인스턴스 (선택)
            parent: 부모 위젯 (선택)
            conn_params: 연결 파라미터 딕셔너리 (선택)
        """
        if not _HAS_QT:
            return
        super().__init__(parent)
        self._client = client
        self._conn_params = conn_params or {}
        uic.loadUi(_UI_FILE, self)
        self._setup_table()
        self._setup_timer()

    def _setup_table(self):
        """테이블 위젯 헤더 크기 조정 모드를 설정합니다."""
        header = self.table_metrics.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_metrics.setEditTriggers(
            self.table_metrics.NoEditTriggers
        )

    def _setup_timer(self):
        """1초 주기 자동 갱신 타이머를 설정합니다."""
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh_metrics)
        self._timer.start()

    def set_client(self, client):
        """ClickHouse 클라이언트를 교체합니다.

        Args:
            client: 새로운 ClickHouse HTTP 클라이언트 인스턴스
        """
        self._client = client
        self._refresh_metrics()

    def _refresh_metrics(self):
        """system.metrics 테이블에서 성능 메트릭을 조회하고 갱신합니다.

        클라이언트가 없거나 오류 발생 시 조용히 무시합니다.
        """
        if self._client is None:
            return
        try:
            query = (
                "SELECT metric, value, description "
                "FROM system.metrics "
                "ORDER BY metric"
            )
            rows = self._client.execute(query)
            self._populate_metrics(rows)
        except Exception as exc:
            logger.debug("성능 메트릭 조회 실패: %s", exc)

    def _populate_metrics(self, rows):
        """조회된 메트릭 데이터로 테이블 위젯을 채웁니다.

        알려진 메트릭에 대해 한국어 설명을 덮어씁니다.

        Args:
            rows: (metric, value, description) 튜플 목록
        """
        self.table_metrics.setRowCount(len(rows))
        for row_idx, (metric, value, description) in enumerate(rows):
            desc = _METRIC_DESCRIPTIONS.get(metric, description)
            for col_idx, text in enumerate((metric, str(value), desc)):
                item = QTableWidgetItem(text)
                item.setTextAlignment(
                    Qt.AlignCenter if col_idx < 2 else Qt.AlignLeft | Qt.AlignVCenter
                )
                self.table_metrics.setItem(row_idx, col_idx, item)
