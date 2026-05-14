"""
Kafka 연결 상태 확인 (IPv4 강제 연결)

[Purpose]
Kafka 브로커에 KafkaAdminClient로 연결을 시도하여 상태를 반환합니다.
IPv6 환경에서도 IPv4(127.0.0.1)로 강제 연결합니다.
kafka-python 미설치 시 소켓으로 직접 확인합니다.

Returns:
    "green" | "red" | "gray"
"""
import logging
import os
import socket

logger = logging.getLogger(__name__)


def check_kafka_connection(host: str = "", port: int = 0, timeout: float = 3.0) -> str:
    """
    Kafka 브로커에 연결을 시도하여 상태를 반환합니다 (IPv4 강제).

    Args:
        host:    브로커 호스트 (기본값: KAFKA_BOOTSTRAP_SERVERS 환경 변수)
        port:    브로커 포트 (기본값: 9092)
        timeout: 연결 타임아웃 (초)

    Returns:
        "green" (연결 성공) | "red" (연결 실패) | "gray" (설정 없음)
    """
    # 원본 getaddrinfo 백업 (IPv4 강제 후 반드시 복원)
    original_getaddrinfo = socket.getaddrinfo

    try:
        from kafka import KafkaAdminClient  # type: ignore

        # IPv4 강제 설정 (localhost → 127.0.0.1)
        def _force_ipv4_getaddrinfo(host_, port_, family=0, socktype=0, proto=0, flags=0):
            """IPv4 주소만 반환하도록 강제"""
            if host_ == "localhost":
                host_ = "127.0.0.1"
            return original_getaddrinfo(host_, port_, socket.AF_INET, socktype, proto, flags)

        socket.getaddrinfo = _force_ipv4_getaddrinfo

        bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")
        if not bootstrap_servers:
            return "gray"

        timeout_ms = int(timeout * 1000)
        admin = KafkaAdminClient(
            bootstrap_servers=[bootstrap_servers],
            request_timeout_ms=timeout_ms,
            api_version_auto_timeout_ms=timeout_ms,
        )
        topics = admin.list_topics()
        admin.close()
        logger.debug("Kafka 연결 성공 (토픽 %d개)", len(topics))
        return "green"

    except ImportError:
        # kafka-python 미설치 시 소켓으로 폴백
        pass
    except Exception as exc:
        logger.debug("Kafka 연결 실패: %s", exc)
        return "red"
    finally:
        # 원본 getaddrinfo 복원 (다른 모듈에 영향 방지)
        socket.getaddrinfo = original_getaddrinfo

    # kafka-python 미설치 시 소켓 직접 연결로 폴백
    if not host:
        broker = os.getenv("KAFKA_BOOTSTRAP_SERVERS", os.getenv("KAFKA_BROKERS", "")).split(",")[0].strip()
        if not broker:
            return "gray"
        if ":" in broker:
            host, _port = broker.rsplit(":", 1)
            port = int(_port) if _port.isdigit() else 9092
        else:
            host = broker
            port = port or 9092

    # localhost를 127.0.0.1로 교체하여 IPv4 강제
    host = "127.0.0.1" if (not host or host == "localhost") else host
    port = port or 9092

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "green"
    except OSError as exc:
        logger.debug("Kafka 소켓 연결 실패 (%s:%s): %s", host, port, exc)
        return "red"
