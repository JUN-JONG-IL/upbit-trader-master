# -*- coding: utf-8 -*-
"""
실시간 지표 갱신 컨트롤러

[책임]
- WebSocket QPS, Pipeline QPS 계산 (1초 롤링 윈도우)
- 마지막 수신 심볼/시간 추적
- 1초마다 metrics_updated 시그널 발송
"""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QObject, pyqtSignal, QTimer
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    logger.debug("[MetricsUpdater] PyQt5 없음 — 더미 클래스 사용")


if _HAS_QT:
    class MetricsUpdater(QObject):
        """
        실시간 지표 갱신 컨트롤러

        - 1초마다 WebSocket/Pipeline QPS 계산
        - 마지막 수신 시간 표시
        - metrics_updated 시그널로 UI에 전달
        """

        # 시그널: (ws_qps, pipeline_qps, staging_count, last_recv_text)
        metrics_updated = pyqtSignal(int, int, int, str)

        def __init__(self, parent=None, interval_ms: int = 3000) -> None:
            super().__init__(parent)

            # 최소 3초 간격 강제 (메인 스레드 블로킹 방지)
            self._interval_ms: int = max(3000, int(interval_ms))

            # 이벤트 롤링 버퍼 (최대 60개 유지 — 순간 QPS 측정용, 1초 윈도우로 카운팅)
            self._ws_events: deque = deque(maxlen=60)
            self._pipeline_events: deque = deque(maxlen=60)
            self._last_symbol: str = ""
            self._last_time: Optional[datetime] = None

            # 외부에서 설정하는 Staging 건수 (DB 조회 결과 수신용)
            self._staging_count: int = 0

            # 3초마다 지표 갱신 타이머 (렉 방지: 1초 → 3초)
            self._timer = QTimer(self)
            self._timer.setInterval(self._interval_ms)
            self._timer.timeout.connect(self._update)

        def start(self) -> None:
            """지표 갱신 타이머 시작"""
            self._timer.start()

        def stop(self) -> None:
            """지표 갱신 타이머 중지"""
            self._timer.stop()

        def record_ws_event(self, symbol: str) -> None:
            """WebSocket 이벤트 발생 시 호출 — QPS 카운팅 및 마지막 수신 갱신"""
            now = datetime.now()
            self._ws_events.append(now)
            self._last_symbol = symbol
            self._last_time = now

        def record_pipeline_event(self) -> None:
            """Pipeline 처리 이벤트 발생 시 호출 — QPS 카운팅"""
            self._pipeline_events.append(datetime.now())

        def set_staging_count(self, count: int) -> None:
            """Staging → Candles 건수 외부 설정 (DB 조회 결과 반영용)"""
            self._staging_count = count

        def get_interval_seconds(self) -> int:
            """갱신 간격(초) 반환 (signal_handlers.py에서 QPS 계산에 사용)"""
            return max(1, int(self._interval_ms / 1000))

        def _update(self) -> None:
            """1초마다 지표 계산 후 시그널 발송"""
            now = datetime.now()
            cutoff = now.timestamp() - 1.0

            # 1초 이내 이벤트만 카운팅
            ws_qps = sum(1 for t in self._ws_events if t.timestamp() > cutoff)
            pipeline_qps = sum(1 for t in self._pipeline_events if t.timestamp() > cutoff)

            # 마지막 수신 텍스트 생성
            if self._last_time:
                elapsed = (now - self._last_time).total_seconds()
                if elapsed < 5:
                    last_text = (
                        f"{self._last_symbol} @ "
                        f"{self._last_time.strftime('%H:%M:%S')}"
                    )
                else:
                    last_text = f"수신 없음 ({int(elapsed)}초 전)"
            else:
                last_text = "대기 중..."

            self.metrics_updated.emit(ws_qps, pipeline_qps, self._staging_count, last_text)

else:
    class MetricsUpdater:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""

        def __init__(self, parent=None, interval_ms: int = 3000) -> None:
            logger.warning("[MetricsUpdater] PyQt5 미설치 — 더미 인스턴스 생성")

        def start(self) -> None:
            """더미 메서드"""

        def stop(self) -> None:
            """더미 메서드"""

        def record_ws_event(self, symbol: str) -> None:
            """더미 메서드"""

        def record_pipeline_event(self) -> None:
            """더미 메서드"""

        def set_staging_count(self, count: int) -> None:
            """더미 메서드"""

        def get_interval_seconds(self) -> int:
            """더미 메서드"""
            return 3
