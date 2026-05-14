#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL 헬스 체커 모듈.

별도 스레드에서 주기적으로 PostgreSQL 연결 상태를 확인하고
결과를 콜백 또는 내부 상태로 저장한다.
"""

import logging
import threading
import time
from typing import Callable, Optional

try:
    import psycopg2
    import psycopg2.extras

    _HAS_PSYCOPG2 = True
except ImportError:  # pragma: no cover
    _HAS_PSYCOPG2 = False

logger = logging.getLogger(__name__)


class PostgresHealthChecker:
    """PostgreSQL 연결 상태를 주기적으로 확인하는 헬스 체커.

    별도 데몬 스레드를 사용하므로 메인 스레드를 차단하지 않는다.

    Example::

        checker = PostgresHealthChecker(dsn="host=localhost dbname=mydb user=postgres")
        checker.start()
        # ... (나중에)
        checker.stop()
    """

    # 기본 폴링 주기 (초)
    DEFAULT_INTERVAL: float = 10.0

    def __init__(
        self,
        dsn: str = "",
        interval: float = DEFAULT_INTERVAL,
        on_healthy: Optional[Callable[[], None]] = None,
        on_unhealthy: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """헬스 체커를 초기화한다.

        Args:
            dsn: psycopg2 DSN 문자열 (예: ``"host=localhost dbname=mydb user=postgres"``).
            interval: 폴링 주기(초). 기본값은 10초.
            on_healthy: 연결 성공 시 호출할 콜백.
            on_unhealthy: 연결 실패 시 호출할 콜백. 예외 객체를 인자로 받는다.
        """
        self._dsn = dsn
        self._interval = interval
        self._on_healthy = on_healthy
        self._on_unhealthy = on_unhealthy

        self._is_healthy: bool = False
        self._last_error: Optional[Exception] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    @property
    def is_healthy(self) -> bool:
        """마지막으로 확인된 연결 상태를 반환한다."""
        return self._is_healthy

    @property
    def last_error(self) -> Optional[Exception]:
        """마지막으로 발생한 오류를 반환한다."""
        return self._last_error

    def start(self) -> None:
        """헬스 체크 스레드를 시작한다."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="pg-health-checker")
        self._thread.start()
        logger.info("PostgresHealthChecker 시작됨 (DSN: %s, 주기: %.1fs)", self._dsn, self._interval)

    def stop(self) -> None:
        """헬스 체크 스레드를 정지한다."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 2)
        logger.info("PostgresHealthChecker 정지됨")

    def check_once(self) -> bool:
        """단발성 헬스 체크를 수행하고 결과를 반환한다.

        Returns:
            연결 성공이면 ``True``, 실패이면 ``False``.
        """
        return self._check()

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """백그라운드 폴링 루프."""
        while not self._stop_event.is_set():
            self._check()
            self._stop_event.wait(self._interval)

    def _check(self) -> bool:
        """PostgreSQL에 연결을 시도하고 상태를 갱신한다."""
        if not _HAS_PSYCOPG2:
            logger.warning("psycopg2가 설치되어 있지 않습니다.")
            self._is_healthy = False
            return False

        try:
            conn = psycopg2.connect(self._dsn, connect_timeout=5)
            conn.close()
            self._is_healthy = True
            self._last_error = None
            if self._on_healthy:
                self._on_healthy()
            logger.debug("PostgreSQL 연결 정상")
            return True
        except Exception as exc:  # noqa: BLE001
            self._is_healthy = False
            self._last_error = exc
            if self._on_unhealthy:
                self._on_unhealthy(exc)
            logger.warning("PostgreSQL 연결 실패: %s", exc)
            return False
