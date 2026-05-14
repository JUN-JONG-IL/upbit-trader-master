"""
Hash Partitioning 관리

[Purpose]
candles 테이블의 Hash Partitioning 마이그레이션 및 파티션 통계 조회

[Responsibilities]
- candles → candles_partitioned 마이그레이션
- 파티션별 크기 통계 조회
"""
import logging

logger = logging.getLogger(__name__)


async def migrate_to_hash_partition(pool) -> None:
    """candles 데이터를 Hash Partition 테이블로 마이그레이션합니다."""
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO candles_partitioned "
            "SELECT * FROM candles ON CONFLICT DO NOTHING"
        )
        logger.info("Hash Partitioning 마이그레이션 완료")


async def get_partition_stats(pool) -> list[dict]:
    """파티션별 크기 통계를 반환합니다."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tablename,
                   pg_size_pretty(
                       pg_total_relation_size(schemaname || '.' || tablename)
                   ) AS size
            FROM   pg_tables
            WHERE  tablename LIKE 'candles_p%'
            ORDER  BY tablename
            """
        )
        return [dict(r) for r in rows]
