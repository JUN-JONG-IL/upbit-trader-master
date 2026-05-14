"""
src/data_01/pipeline/aggregator.py
Stage 8: CAGG Refresh (?곸쐞 ??꾪봽?덉엫 媛깆떊)

TimescaleDB CAGG(cagg_5m, cagg_1h, cagg_1d)瑜??섎룞?쇰줈 媛깆떊?⑸땲??
?쇰컲?곸쑝濡?TimescaleDB媛 ?먮룞?쇰줈 泥섎━?섏?留?
?ㅼ떆媛꾩꽦???꾩슂??寃쎌슦 紐낆떆?곸쑝濡?refresh瑜??몄텧?⑸땲??
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# CAGG ?대쫫 ???덈줈怨좎묠 ?ㅽ봽??(start, end 湲곗?)
_CAGG_CONFIG: dict[str, tuple[timedelta, timedelta]] = {
    "cagg_5m": (timedelta(minutes=10), timedelta(minutes=1)),
    "cagg_1h": (timedelta(hours=2),    timedelta(minutes=1)),
    "cagg_1d": (timedelta(days=3),      timedelta(hours=1)),
}


class CaggAggregator:
    """Continuous Aggregate瑜?紐낆떆?곸쑝濡?媛깆떊?⑸땲??"""

    def __init__(self, pool) -> None:
        self._pool = pool

    async def refresh_all(self) -> None:
        """紐⑤뱺 CAGG瑜?媛깆떊?⑸땲??"""
        now = datetime.now(tz=timezone.utc)
        for name, (start_offset, end_offset) in _CAGG_CONFIG.items():
            await self.refresh(name, now - start_offset, now - end_offset)

    async def refresh(
        self,
        cagg_name: str,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        """吏??CAGG瑜?二쇱뼱吏??쒓컙 ?덈룄?곕줈 媛깆떊?⑸땲??"""
        if cagg_name not in _CAGG_CONFIG:
            raise ValueError(f"?????녿뒗 CAGG ?대쫫: {cagg_name!r}")
        try:
            await self._pool.execute(
                "CALL refresh_continuous_aggregate($1, $2, $3)",
                cagg_name, window_start, window_end,
            )
            logger.debug("CAGG 媛깆떊 ?꾨즺: %s (%s ~ %s)", cagg_name, window_start, window_end)
        except Exception as exc:
            logger.warning("CAGG 媛깆떊 ?ㅽ뙣 (%s): %s", cagg_name, exc)

