"""
ClickHouse 연결 상태 확인

[Purpose]
ClickHouse HTTP 헬스 엔드포인트로 연결 상태를 확인합니다.

Returns:
    "green" | "red" | "gray"
"""
import logging
import os
import socket
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


def check_clickhouse_connection(
    host: str = "",
    http_port: int = 0,
    timeout: float = 3.0,
) -> str:
    """
    ClickHouse HTTP /ping 엔드포인트로 연결 상태를 확인합니다.

    Args:
        host:      ClickHouse 호스트 (기본값: CLICKHOUSE_HOST 환경 변수)
        http_port: HTTP 포트 (기본값: 8123)
        timeout:   요청 타임아웃 (초)

    Returns:
        "green" (정상) | "red" (실패) | "gray" (설정 없음)
    """
    host = host or os.getenv("CLICKHOUSE_HOST", "")
    if not host:
        return "gray"
    http_port = http_port or int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123"))

    url = f"http://{host}:{http_port}/ping"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode(errors="replace").strip()
            return "green" if body == "Ok." else "red"
    except urllib.error.URLError as exc:
        logger.debug("ClickHouse HTTP ping 실패 (%s): %s", url, exc)
        return "red"
    except OSError as exc:
        logger.debug("ClickHouse 연결 실패: %s", exc)
        return "red"
