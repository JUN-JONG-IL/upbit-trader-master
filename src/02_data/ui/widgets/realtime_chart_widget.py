# -*- coding: utf-8 -*-
"""
실시간 PyQtGraph 차트 위젯

[책임]
- widget_graph_container 에 실시간 데이터 수집률 그래프 삽입
- 60초 롤링 윈도우 (WebSocket / REST / Staging / Candles)
- 1초마다 update_data() 호출로 갱신
"""
from __future__ import annotations

import logging
import time as _time
from collections import deque
from typing import Deque, Tuple

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import QWidget, QVBoxLayout
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    logger.debug("[RealtimeChartWidget] PyQt5 없음 — 더미 클래스 사용")

# (timestamp, value) 쌍
_DataPoints = Deque[Tuple[float, float]]


if _HAS_QT:
    class RealtimeChartWidget(QWidget):
        """
        PyQtGraph 실시간 차트 위젯

        - 60초 롤링 윈도우
        - 수집률(WebSocket/REST)과 DB 저장 지연(Staging/Candles) 두 그래프
        - pyqtgraph 미설치 시 조용히 비활성화
        """

        _WINDOW_SEC = 60  # 롤링 윈도우 (초)

        def __init__(self, parent=None) -> None:
            super().__init__(parent)

            # 롤링 데이터 버퍼 (deque: 오래된 항목 앞에서 제거)
            self._data_ws: _DataPoints = deque()
            self._data_rest: _DataPoints = deque()
            self._data_staging: _DataPoints = deque()
            self._data_candles: _DataPoints = deque()

            # 곡선 참조 (pyqtgraph PlotDataItem)
            self._curve_ws = None
            self._curve_rest = None
            self._curve_staging = None
            self._curve_candles = None

            self._pg_available = False
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)

            self._init_graphs()

        # ------------------------------------------------------------------
        # 초기화
        # ------------------------------------------------------------------

        def _init_graphs(self) -> None:
            """pyqtgraph 그래프를 위젯 레이아웃에 삽입합니다."""
            try:
                import pyqtgraph as pg  # type: ignore

                # 수집률 그래프
                graph_collection = pg.PlotWidget(title="데이터 수집률 (건/분)")
                graph_collection.setLabel("left", "건수")
                graph_collection.setLabel("bottom", "경과 시간 (초)")
                graph_collection.showGrid(x=True, y=True, alpha=0.3)
                graph_collection.addLegend()
                self._curve_ws = graph_collection.plot(
                    pen=pg.mkPen(color="g", width=2), name="WebSocket"
                )
                self._curve_rest = graph_collection.plot(
                    pen=pg.mkPen(color="b", width=2), name="REST API"
                )
                self._layout.addWidget(graph_collection)

                # DB 저장 지연 그래프
                graph_latency = pg.PlotWidget(title="DB 저장 지연 (ms)")
                graph_latency.setLabel("left", "지연 시간 (ms)")
                graph_latency.setLabel("bottom", "경과 시간 (초)")
                graph_latency.showGrid(x=True, y=True, alpha=0.3)
                graph_latency.addLegend()
                self._curve_staging = graph_latency.plot(
                    pen=pg.mkPen(color="r", width=2), name="Staging"
                )
                self._curve_candles = graph_latency.plot(
                    pen=pg.mkPen(color="y", width=2), name="Candles"
                )
                self._layout.addWidget(graph_latency)

                self._pg_available = True
                logger.info("[RealtimeChartWidget] PyQtGraph 그래프 초기화 완료")
            except ImportError:
                logger.debug("[RealtimeChartWidget] pyqtgraph 미설치 — 그래프 비활성화")
            except Exception as exc:
                logger.warning("[RealtimeChartWidget] 그래프 초기화 실패: %s", exc)

        # ------------------------------------------------------------------
        # 공개 API
        # ------------------------------------------------------------------

        def update_data(
            self,
            ws_count: float = 0,
            rest_count: float = 0,
            staging_count: float = 0,
            candles_count: float = 0,
        ) -> None:
            """1초마다 호출하여 롤링 버퍼를 갱신하고 곡선을 다시 그립니다.

            Args:
                ws_count: WebSocket 수신 건수
                rest_count: REST API 수신 건수
                staging_count: Staging DB 건수
                candles_count: Candles DB 건수
            """
            if not self._pg_available:
                return

            now = _time.time()
            cutoff = now - self._WINDOW_SEC

            # 새 데이터 포인트 추가
            self._data_ws.append((now, ws_count))
            self._data_rest.append((now, rest_count))
            self._data_staging.append((now, staging_count))
            self._data_candles.append((now, candles_count))

            # 오래된 데이터 제거 (앞쪽의 오래된 항목만 제거 — deque 특성 활용)
            for buf in (self._data_ws, self._data_rest, self._data_staging, self._data_candles):
                while buf and buf[0][0] <= cutoff:
                    buf.popleft()

            # 곡선 갱신
            try:
                self._redraw_curve(self._curve_ws, self._data_ws)
                self._redraw_curve(self._curve_rest, self._data_rest)
                self._redraw_curve(self._curve_staging, self._data_staging)
                self._redraw_curve(self._curve_candles, self._data_candles)
            except Exception as exc:
                logger.debug("[RealtimeChartWidget] 곡선 갱신 실패: %s", exc)

        # ------------------------------------------------------------------
        # 내부 헬퍼
        # ------------------------------------------------------------------

        @staticmethod
        def _redraw_curve(curve, data: _DataPoints) -> None:
            """곡선 데이터를 갱신합니다 (시작 시간 기준 상대 시간 사용)."""
            if curve is None or not data:
                return
            t0 = data[0][0]
            xs = [t - t0 for t, _ in data]
            ys = [v for _, v in data]
            curve.setData(xs, ys)

else:
    class RealtimeChartWidget:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""

        def __init__(self, parent=None) -> None:
            logger.warning("[RealtimeChartWidget] PyQt5 미설치 — 더미 인스턴스 생성")

        def update_data(self, **kwargs) -> None:
            """더미 메서드"""
