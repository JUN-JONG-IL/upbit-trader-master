# -*- coding: utf-8 -*-
"""
[Purpose]
TimescaleDB 압축/보존 정책 동적 변경 관리자

[Responsibilities]
- 설정 UI에서 변경된 압축 정책을 TimescaleDB에 즉시 적용
- 보존 정책 동적 변경 (삭제 주기 설정)
- 영구 보관 모드 지원 (retention_days=0)
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class TimescalePolicyManager:
    """TimescaleDB 압축/보존 정책 동적 변경 관리자."""

    def __init__(self, db_pool: Any) -> None:
        """
        Args:
            db_pool: asyncpg.Pool 인스턴스
        """
        self.pool = db_pool

    async def update_compression_policy(self, days: int = 1) -> None:
        """
        압축 정책 업데이트.

        Args:
            days: 압축 시작까지의 일수. 0이면 즉시 압축.
        """
        days = max(int(days), 0)
        interval = f"{days} days" if days > 0 else "0 seconds"
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "SELECT remove_compression_policy('candles', if_exists => true)"
                )
                await conn.execute(
                    "SELECT add_compression_policy('candles', $1::interval)",
                    interval,
                )
            logger.info("[TimescalePolicy] 압축 정책 업데이트: %s 후", interval)
        except Exception as exc:
            logger.error("[TimescalePolicy] 압축 정책 업데이트 실패: %s", exc)
            raise

    async def update_retention_policy(self, days: int = 90) -> None:
        """
        보존 정책 업데이트.

        Args:
            days: 보관 일수. 0이면 영구 보관 (삭제 정책 없음).
        """
        days = max(int(days), 0)
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "SELECT remove_retention_policy('candles', if_exists => true)"
                )
                if days > 0:
                    await conn.execute(
                        "SELECT add_retention_policy('candles', $1::interval)",
                        f"{days} days",
                    )
                    logger.info("[TimescalePolicy] 보존 정책 업데이트: %d일", days)
                else:
                    logger.info("[TimescalePolicy] 영구 보관 모드 (삭제 정책 없음)")
        except Exception as exc:
            logger.error("[TimescalePolicy] 보존 정책 업데이트 실패: %s", exc)
            raise
