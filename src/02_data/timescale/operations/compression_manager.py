#!/usr/bin/env python3
"""TimescaleDB Compression policy management module."""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CompressionManager:
    """Manages TimescaleDB chunk compression policies.

    Args:
        pool: asyncpg connection pool.
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def __aenter__(self) -> "CompressionManager":
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass

    async def enable_compression(
        self,
        table: str,
        segment_by: Optional[str] = None,
        order_by: str = "time DESC",
    ) -> bool:
        """Enable compression on a hypertable.

        Args:
            table: Hypertable name.
            segment_by: Column to segment by (e.g. 'symbol').
            order_by: ORDER BY clause for compression.

        Returns:
            True on success.
        """
        segment_clause = f"timescaledb.compress_segmentby = '{segment_by}'," if segment_by else ""
        sql = (
            f"ALTER TABLE {table} SET ("
            f"timescaledb.compress, "
            f"{segment_clause}"
            f"timescaledb.compress_orderby = '{order_by}');"
        )
        try:
            await self._pool.execute(sql)
            logger.info("Compression enabled on %s", table)
            return True
        except Exception as exc:
            logger.error("enable_compression(%s) error: %s", table, exc)
            return False

    async def add_compression_policy(self, table: str, compress_after: str) -> bool:
        """Add an automatic compression policy.

        Args:
            table: Hypertable name.
            compress_after: Interval after which to compress, e.g. '30 days'.

        Returns:
            True on success.
        """
        sql = f"SELECT add_compression_policy('{table}', INTERVAL '{compress_after}');"
        try:
            await self._pool.execute(sql)
            logger.info("Compression policy added to %s (after %s)", table, compress_after)
            return True
        except Exception as exc:
            logger.error("add_compression_policy(%s) error: %s", table, exc)
            return False

    async def remove_compression_policy(self, table: str, if_exists: bool = True) -> bool:
        """Remove the compression policy from a hypertable.

        Args:
            table: Hypertable name.
            if_exists: Do not error if policy doesn't exist.

        Returns:
            True on success.
        """
        sql = f"SELECT remove_compression_policy('{table}', if_exists => {'TRUE' if if_exists else 'FALSE'});"
        try:
            await self._pool.execute(sql)
            logger.info("Compression policy removed from %s", table)
            return True
        except Exception as exc:
            logger.error("remove_compression_policy(%s) error: %s", table, exc)
            return False

    async def compress_chunk(self, chunk_schema: str, chunk_name: str) -> bool:
        """Manually compress a specific chunk.

        Args:
            chunk_schema: Schema of the chunk.
            chunk_name: Name of the chunk table.

        Returns:
            True on success.
        """
        sql = f"SELECT compress_chunk('{chunk_schema}.{chunk_name}');"
        try:
            await self._pool.execute(sql)
            return True
        except Exception as exc:
            logger.error("compress_chunk(%s.%s) error: %s", chunk_schema, chunk_name, exc)
            return False

    async def list_policies(self) -> List[Dict[str, Any]]:
        """List all compression policies.

        Returns:
            List of policy dicts.
        """
        sql = "SELECT * FROM timescaledb_information.compression_settings;"
        try:
            rows = await self._pool.fetch(sql)
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error("list_policies error: %s", exc)
            return []
