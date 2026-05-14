#!/usr/bin/env python3
"""TimescaleDB Hypertable management module."""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore
    logger.warning("asyncpg not installed; HypertableManager will be non-functional.")


class HypertableManager:
    """Manages TimescaleDB hypertable operations.

    Args:
        pool: asyncpg connection pool.
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def __aenter__(self) -> "HypertableManager":
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass

    async def list_hypertables(self) -> List[Dict[str, Any]]:
        """List all hypertables with metadata.

        Returns:
            List of dicts with hypertable info.
        """
        sql = "SELECT * FROM timescaledb_information.hypertables;"
        try:
            rows = await self._pool.fetch(sql)
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error("list_hypertables error: %s", exc)
            return []

    async def create_hypertable(
        self,
        table: str,
        time_column: str = "time",
        chunk_interval: str = "7 days",
        if_not_exists: bool = True,
    ) -> bool:
        """Create a hypertable from an existing table.

        Args:
            table: Table name.
            time_column: Name of the time partitioning column.
            chunk_interval: Chunk time interval string.
            if_not_exists: Skip if already a hypertable.

        Returns:
            True on success.
        """
        sql = (
            f"SELECT create_hypertable('{table}', '{time_column}', "
            f"chunk_time_interval => INTERVAL '{chunk_interval}', "
            f"if_not_exists => {'TRUE' if if_not_exists else 'FALSE'});"
        )
        try:
            await self._pool.execute(sql)
            logger.info("Hypertable created for %s", table)
            return True
        except Exception as exc:
            logger.error("create_hypertable(%s) error: %s", table, exc)
            return False

    async def drop_chunks(self, table: str, older_than: str) -> int:
        """Drop old chunks from a hypertable.

        Args:
            table: Hypertable name.
            older_than: Interval string, e.g. '90 days'.

        Returns:
            Number of chunks dropped.
        """
        sql = f"SELECT drop_chunks('{table}', INTERVAL '{older_than}');"
        try:
            rows = await self._pool.fetch(sql)
            count = len(rows)
            logger.info("Dropped %d chunks from %s", count, table)
            return count
        except Exception as exc:
            logger.error("drop_chunks(%s) error: %s", table, exc)
            return 0

    async def chunk_info(self, table: str) -> List[Dict[str, Any]]:
        """Get chunk details for a hypertable.

        Args:
            table: Hypertable name.

        Returns:
            List of chunk info dicts.
        """
        sql = (
            "SELECT * FROM timescaledb_information.chunks "
            f"WHERE hypertable_name = '{table}';"
        )
        try:
            rows = await self._pool.fetch(sql)
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error("chunk_info(%s) error: %s", table, exc)
            return []
