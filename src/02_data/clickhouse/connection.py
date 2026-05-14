"""
ClickHouse 클라이언트 팩토리

[Purpose]
환경 변수 기반으로 ClickHouse 클라이언트를 생성합니다.

환경 변수:
    CLICKHOUSE_HOST:     호스트 (기본값: localhost)
    CLICKHOUSE_PORT:     포트  (기본값: 9000)
    CLICKHOUSE_USER:     사용자 (기본값: trader)
    CLICKHOUSE_PASSWORD: 패스워드 (기본값: clickhouse)
    CLICKHOUSE_DB:       데이터베이스 (기본값: trading_events)
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from clickhouse_driver import Client  # type: ignore
    _CH_AVAILABLE = True
except ImportError:
    Client = None  # type: ignore
    _CH_AVAILABLE = False


def get_client() -> Optional[object]:
    """
    ClickHouse Client 인스턴스를 반환합니다.

    Returns:
        clickhouse_driver.Client | None: 드라이버 미설치 시 None 반환
    """
    if not _CH_AVAILABLE:
        logger.warning("clickhouse-driver 미설치 — ClickHouse 클라이언트 사용 불가")
        return None
    return Client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "9000")),
        user=os.getenv("CLICKHOUSE_USER", "trader"),
        password=os.getenv("CLICKHOUSE_PASSWORD", "clickhouse"),
        database=os.getenv("CLICKHOUSE_DB", "trading_events"),
    )
