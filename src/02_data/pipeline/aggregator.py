"""
src/02_data/pipeline/aggregator.py
Stage 8: CAGG Refresh (상위 타임프레임 갱신)

TimescaleDB CAGG(cagg_5m, cagg_1h, cagg_1d)를 수동으로 갱신합니다.
일반적으로 TimescaleDB가 자동으로 처리하지만,
실시간성이 필요한 경우 명시적으로 refresh를 호출합니다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# CAGG 이름 → 새로고침 오프셋 (start, end 기준)
_CAGG_CONFIG: dict[str, tuple[timedelta, timedelta]] = {
    "cagg_5m": (timedelta(minutes=10), timedelta(minutes=1)),
    "cagg_1h": (timedelta(hours=2),    timedelta(minutes=1)),
    "cagg_1d": (timedelta(days=3),      timedelta(hours=1)),
}


class CaggAggregator:
    """Continuous Aggregate를 명시적으로 갱신합니다."""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def refresh_all(self) -> None:
        """모든 CAGG를 갱신합니다."""
        now = datetime.now(tz=timezone.utc)
        for name, (start_offset, end_offset) in _CAGG_CONFIG.items():
            await self.refresh(name, now - start_offset, now - end_offset)

    async def refresh(
        self,
        cagg_name: str,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        """지정 CAGG를 주어진 시간 윈도우로 갱신합니다."""
        if cagg_name not in _CAGG_CONFIG:
            raise ValueError(f"알 수 없는 CAGG 이름: {cagg_name!r}")
        try:
            await self._pool.execute(
                "CALL refresh_continuous_aggregate($1, $2, $3)",
                cagg_name, window_start, window_end,
            )
            logger.debug("CAGG 갱신 완료: %s (%s ~ %s)", cagg_name, window_start, window_end)
        except Exception as exc:
            logger.warning("CAGG 갱신 실패 (%s): %s", cagg_name, exc)
