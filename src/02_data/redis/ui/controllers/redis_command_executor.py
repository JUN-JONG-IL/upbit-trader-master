#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Redis 명령어 안전 실행 모듈"""

import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    from PyQt5.QtCore import QObject, pyqtSignal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

# 허용되지 않는 위험 명령어 목록
_BLOCKED_COMMANDS = frozenset(
    [
        "FLUSHALL",
        "FLUSHDB",
        "DEBUG",
        "CONFIG",
        "SHUTDOWN",
        "SLAVEOF",
        "REPLICAOF",
        "BGREWRITEAOF",
        "BGSAVE",
    ]
)


class RedisCommandExecutor:
    """Redis 명령어를 안전하게 실행하는 클래스.

    위험 명령어를 차단하고, 실행 결과를 정형화된 형태로 반환합니다.
    PyQt5가 설치된 경우 시그널을 통해 결과를 전달할 수도 있습니다.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: Optional[str] = None,
        db: int = 0,
    ) -> None:
        """초기화.

        Args:
            host: Redis 서버 호스트명
            port: Redis 서버 포트
            password: 인증 비밀번호 (없으면 None)
            db: 데이터베이스 번호
        """
        self._host = host
        self._port = port
        self._password = password
        self._db = db
        self._client: Any = None

    # ------------------------------------------------------------------
    # 연결 관리
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Redis 서버에 연결합니다.

        Returns:
            연결 성공 여부
        """
        try:
            import redis  # type: ignore

            self._client = redis.Redis(
                host=self._host,
                port=self._port,
                password=self._password,
                db=self._db,
                socket_connect_timeout=2,
                socket_timeout=5,
                decode_responses=True,
            )
            self._client.ping()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Redis 연결 실패: %s", exc)
            self._client = None
            return False

    def disconnect(self) -> None:
        """Redis 서버 연결을 해제합니다."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    # ------------------------------------------------------------------
    # 명령어 실행
    # ------------------------------------------------------------------

    def execute(self, command: str, *args: Any) -> Tuple[bool, Any]:
        """Redis 명령어를 안전하게 실행합니다.

        Args:
            command: 실행할 Redis 명령어 (대소문자 무관)
            *args: 명령어 인수

        Returns:
            (성공 여부, 결과 또는 오류 메시지) 튜플
        """
        upper_cmd = command.upper()
        if upper_cmd in _BLOCKED_COMMANDS:
            msg = f"차단된 명령어입니다: {command}"
            logger.warning(msg)
            return False, msg

        if self._client is None:
            if not self.connect():
                return False, "Redis 서버에 연결되어 있지 않습니다."

        try:
            result = self._client.execute_command(upper_cmd, *args)
            return True, result
        except Exception as exc:  # noqa: BLE001
            logger.error("명령어 실행 오류 [%s]: %s", command, exc)
            return False, str(exc)

    def get_keys(self, pattern: str = "*") -> List[str]:
        """패턴에 매칭되는 키 목록을 반환합니다.

        Args:
            pattern: 검색 패턴 (기본값: 전체)

        Returns:
            키 이름 목록
        """
        if self._client is None:
            self.connect()
        if self._client is None:
            return []
        try:
            return list(self._client.scan_iter(pattern))
        except Exception as exc:  # noqa: BLE001
            logger.error("키 조회 오류: %s", exc)
            return []

    def get_key_info(self, key: str) -> Dict[str, Any]:
        """특정 키의 타입, TTL, 값을 조회합니다.

        Args:
            key: 조회할 키 이름

        Returns:
            키 정보 딕셔너리
        """
        if self._client is None:
            self.connect()
        if self._client is None:
            return {}
        try:
            key_type = self._client.type(key)
            ttl = self._client.ttl(key)
            return {"key": key, "type": key_type, "ttl": ttl}
        except Exception as exc:  # noqa: BLE001
            logger.error("키 정보 조회 오류 [%s]: %s", key, exc)
            return {}
