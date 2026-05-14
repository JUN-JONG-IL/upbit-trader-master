#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Redis 연결 상태 점검 모듈"""

import threading
import time
from typing import Callable, Dict, Optional

try:
    from PyQt5.QtCore import QObject, pyqtSignal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


class RedisHealthChecker:
    """Redis 연결 상태를 주기적으로 점검하는 클래스.

    백그라운드 스레드에서 Redis ping 및 서버 정보를 수집하고,
    콜백 또는 Qt 시그널을 통해 결과를 전달합니다.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: Optional[str] = None,
        db: int = 0,
        interval: float = 5.0,
    ) -> None:
        """초기화.

        Args:
            host: Redis 서버 호스트명
            port: Redis 서버 포트
            password: 인증 비밀번호 (없으면 None)
            db: 데이터베이스 번호
            interval: 점검 주기(초)
        """
        self._host = host
        self._port = port
        self._password = password
        self._db = db
        self._interval = interval

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # 마지막 점검 결과
        self._last_result: Dict = {}
        # 결과 수신 콜백 (Dict → None)
        self._on_result: Optional[Callable[[Dict], None]] = None
        # 오류 수신 콜백 (str → None)
        self._on_error: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def set_on_result(self, callback: Callable[[Dict], None]) -> None:
        """점검 성공 시 호출할 콜백을 등록합니다."""
        self._on_result = callback

    def set_on_error(self, callback: Callable[[str], None]) -> None:
        """점검 실패 시 호출할 콜백을 등록합니다."""
        self._on_error = callback

    def start(self) -> None:
        """백그라운드 점검 스레드를 시작합니다."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """백그라운드 점검 스레드를 중지합니다."""
        with self._lock:
            self._running = False

    def check_once(self) -> Dict:
        """즉시 한 번 상태를 점검하고 결과 딕셔너리를 반환합니다."""
        return self._fetch_info()

    @property
    def last_result(self) -> Dict:
        """마지막 점검 결과를 반환합니다."""
        return dict(self._last_result)

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """점검 루프. 스레드에서 실행됩니다."""
        while self._running:
            result = self._fetch_info()
            with self._lock:
                self._last_result = result
            if "error" in result:
                if self._on_error:
                    self._on_error(result["error"])
            else:
                if self._on_result:
                    self._on_result(result)
            time.sleep(self._interval)

    def _fetch_info(self) -> Dict:
        """Redis 서버에 접속해 INFO 데이터를 수집합니다."""
        try:
            import redis  # type: ignore

            client = redis.Redis(
                host=self._host,
                port=self._port,
                password=self._password,
                db=self._db,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            info = client.info()
            client.close()
            return {
                "connected": True,
                "version": info.get("redis_version", "?"),
                "uptime_seconds": info.get("uptime_in_seconds", 0),
                "used_memory_human": info.get("used_memory_human", "?"),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "role": info.get("role", "?"),
            }
        except Exception as exc:  # noqa: BLE001
            return {"connected": False, "error": str(exc)}
