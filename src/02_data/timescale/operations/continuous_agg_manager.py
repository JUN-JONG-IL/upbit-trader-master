#!/usr/bin/env python3
"""TimescaleDB Continuous Aggregate management module."""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ContinuousAggManager:
    """Manages TimescaleDB continuous aggregate views.

    Args:
        pool: asyncpg connection pool.
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def __aenter__(self) -> "ContinuousAggManager":
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass

    async def list_caggs(self) -> List[Dict[str, Any]]:
        """List all continuous aggregates.

        Returns:
            List of continuous aggregate metadata dicts.
        """
        sql = "SELECT * FROM timescaledb_information.continuous_aggregates;"
        try:
            rows = await self._pool.fetch(sql)
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error("list_caggs error: %s", exc)
            return []

    async def create_cagg(self, view_name: str, ddl: str) -> bool:
        """Create a continuous aggregate view.

        Args:
            view_name: Name of the materialized view to create.
            ddl: Full CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous) SQL.

        Returns:
            True on success.
        """
        try:
            await self._pool.execute(ddl)
            logger.info("Continuous aggregate '%s' created.", view_name)
            return True
        except Exception as exc:
            logger.error("create_cagg(%s) error: %s", view_name, exc)
            return False

    async def refresh_cagg(
        self,
        view_name: str,
        window_start: Optional[str] = None,
        window_end: Optional[str] = None,
    ) -> bool:
        """Manually refresh a continuous aggregate.

        Args:
            view_name: Name of the materialized view.
            window_start: Optional start of refresh window (ISO timestamp).
            window_end: Optional end of refresh window (ISO timestamp).

        Returns:
            True on success.
        """
        if window_start and window_end:
            sql = f"CALL refresh_continuous_aggregate('{view_name}', '{window_start}', '{window_end}');"
        else:
            sql = f"CALL refresh_continuous_aggregate('{view_name}', NULL, NULL);"
        try:
            await self._pool.execute(sql)
            logger.info("Refreshed continuous aggregate '%s'.", view_name)
            return True
        except Exception as exc:
            logger.error("refresh_cagg(%s) error: %s", view_name, exc)
            return False

    async def add_refresh_policy(
        self,
        view_name: str,
        start_offset: str,
        end_offset: str,
        schedule_interval: str,
    ) -> bool:
        """Add an automatic refresh policy to a continuous aggregate.

        Args:
            view_name: Name of the materialized view.
            start_offset: INTERVAL string for start offset, e.g. '30 days'.
            end_offset: INTERVAL string for end offset, e.g. '1 hour'.
            schedule_interval: INTERVAL string for schedule, e.g. '1 hour'.

        Returns:
            True on success.
        """
        sql = (
            f"SELECT add_continuous_aggregate_policy('{view_name}', "
            f"start_offset => INTERVAL '{start_offset}', "
            f"end_offset => INTERVAL '{end_offset}', "
            f"schedule_interval => INTERVAL '{schedule_interval}');"
        )
        try:
            await self._pool.execute(sql)
            logger.info("Refresh policy added to '%s'.", view_name)
            return True
        except Exception as exc:
            logger.error("add_refresh_policy(%s) error: %s", view_name, exc)
            return False

    async def drop_cagg(self, view_name: str, cascade: bool = False) -> bool:
        """Drop a continuous aggregate.

        Args:
            view_name: Name of the materialized view.
            cascade: Whether to cascade the drop.

        Returns:
            True on success.
        """
        cascade_clause = "CASCADE" if cascade else ""
        sql = f"DROP MATERIALIZED VIEW IF EXISTS {view_name} {cascade_clause};"
        try:
            await self._pool.execute(sql)
            logger.info("Dropped continuous aggregate '%s'.", view_name)
            return True
        except Exception as exc:
            logger.error("drop_cagg(%s) error: %s", view_name, exc)
            return False
