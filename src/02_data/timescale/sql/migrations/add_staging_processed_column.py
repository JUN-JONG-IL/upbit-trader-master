# -*- coding: utf-8 -*-
"""
마이그레이션: staging_candles 테이블에 processed 컬럼 추가

실행 시점: 앱 시작 시 자동 실행
"""
import logging

logger = logging.getLogger(__name__)


async def migrate(pool) -> bool:
    """
    staging_candles 테이블에 processed 컬럼을 추가합니다.
    
    Args:
        pool: TimescaleDB 연결 풀 (asyncpg 또는 TimescaleConnector)
        
    Returns:
        bool: 마이그레이션 성공 여부
    """
    try:
        # 1. processed 컬럼 존재 여부 확인
        check_sql = """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'staging_candles' 
            AND column_name = 'processed'
        """
        
        # asyncpg 풀인지 TimescaleConnector인지 확인
        if hasattr(pool, 'fetchval'):
            # asyncpg pool
            exists = await pool.fetchval(check_sql)
        elif hasattr(pool, 'fetchone'):
            # TimescaleConnector
            result = await pool.fetchone(check_sql)
            exists = result[0] if result else None
        else:
            logger.error("[Migration] 지원되지 않는 pool 타입: %s", type(pool))
            return False
        
        if exists:
            logger.info("[Migration] ✅ staging_candles.processed 컬럼 이미 존재")
            return True
        
        # 2. processed 컬럼 추가
        logger.info("[Migration] staging_candles 테이블에 processed 컬럼 추가 중...")
        
        alter_sql = """
            ALTER TABLE staging_candles 
            ADD COLUMN IF NOT EXISTS processed BOOLEAN DEFAULT FALSE
        """
        
        if hasattr(pool, 'execute'):
            await pool.execute(alter_sql)
        else:
            logger.error("[Migration] pool.execute() 메서드 없음")
            return False
        
        logger.info("[Migration] ✅ processed 컬럼 추가 완료")
        
        # 3. 인덱스 생성 (성능 최적화)
        index_sql = """
            CREATE INDEX IF NOT EXISTS idx_staging_candles_processed 
            ON staging_candles(processed) 
            WHERE NOT processed
        """
        
        await pool.execute(index_sql)
        logger.info("[Migration] ✅ processed 인덱스 생성 완료")
        
        return True
        
    except Exception as exc:
        logger.error("[Migration] ❌ 마이그레이션 실패: %s", exc, exc_info=True)
        return False


def migrate_sync(pool) -> bool:
    """
    동기 버전 마이그레이션 (psycopg2 풀용)
    
    Args:
        pool: psycopg2 연결 풀
        
    Returns:
        bool: 마이그레이션 성공 여부
    """
    try:
        # 1. 컬럼 존재 여부 확인
        check_sql = """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'staging_candles' 
            AND column_name = 'processed'
        """
        
        if hasattr(pool, 'fetchone'):
            # TimescaleConnector 동기 메서드
            result = pool.fetchone(check_sql)
            exists = result[0] if result else None
        else:
            # psycopg2 connection
            with pool.cursor() as cur:
                cur.execute(check_sql)
                result = cur.fetchone()
                exists = result[0] if result else None
        
        if exists:
            logger.info("[Migration] ✅ staging_candles.processed 컬럼 이미 존재")
            return True
        
        # 2. processed 컬럼 추가
        logger.info("[Migration] staging_candles 테이블에 processed 컬럼 추가 중...")
        
        alter_sql = """
            ALTER TABLE staging_candles 
            ADD COLUMN IF NOT EXISTS processed BOOLEAN DEFAULT FALSE
        """
        
        if hasattr(pool, 'execute'):
            pool.execute(alter_sql)
        else:
            with pool.cursor() as cur:
                cur.execute(alter_sql)
            pool.commit()
        
        logger.info("[Migration] ✅ processed 컬럼 추가 완료")
        
        # 3. 인덱스 생성
        index_sql = """
            CREATE INDEX IF NOT EXISTS idx_staging_candles_processed 
            ON staging_candles(processed) 
            WHERE NOT processed
        """
        
        if hasattr(pool, 'execute'):
            pool.execute(index_sql)
        else:
            with pool.cursor() as cur:
                cur.execute(index_sql)
            pool.commit()
        
        logger.info("[Migration] ✅ processed 인덱스 생성 완료")
        
        return True
        
    except Exception as exc:
        logger.error("[Migration] ❌ 동기 마이그레이션 실패: %s", exc, exc_info=True)
        return False