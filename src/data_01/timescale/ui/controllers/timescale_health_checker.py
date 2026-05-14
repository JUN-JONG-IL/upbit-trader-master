#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TimescaleDB 연결 상태 헬스 체커"""

import threading
import logging
from typing import Callable, Optional

try:
    from PyQt5.QtCore import QObject, pyqtSignal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

# 헬스 상태 상수
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_UNKNOWN = "unknown"


class _HealthCheckerBase:
    """PyQt5 없는 환경을 위한 기반 클래스."""

    def __init__(self):
        self._callbacks: list[Callable] = []

    def health_updated_connect(self, callback: Callable):
        """상태 변경 콜백을 등록합니다."""
        self._callbacks.append(callback)

    def _emit_health(self, status: str, message: str):
        for cb in self._callbacks:
            try:
                cb(status, message)
            except Exception as exc:
                logger.debug("헬스 콜백 오류: %s", exc)


if _HAS_QT:
    class _QtBase(QObject):
        health_updated = pyqtSignal(str, str)

        def _emit_health(self, status: str, message: str):
            self.health_updated.emit(status, message)

    _Base = _QtBase
else:
    _Base = _HealthCheckerBase


class TimescaleHealthChecker(_Base):
    """TimescaleDB 연결 상태를 주기적으로 확인하는 컨트롤러.

    별도의 스레드에서 연결을 시도하고, 결과를 health_updated 시그널
    (PyQt5 사용 시) 또는 등록된 콜백으로 전달합니다.

    Example::

        checker = TimescaleHealthChecker(db_conn=conn, interval=5)
        checker.health_updated.connect(lambda s, m: print(s, m))
        checker.start()
        ...
        checker.stop()
    """

    def __init__(self, db_conn=None, interval: int = 10):
        """초기화.

        Args:
            db_conn: TimescaleDB 연결 객체 (psycopg2 connection 등)
            interval: 헬스 체크 주기 (초)
        """
        if _HAS_QT:
            super().__init__()
        else:
            _HealthCheckerBase.__init__(self)

        self._db_conn = db_conn
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # 공개 인터페이스
    # ------------------------------------------------------------------

    def start(self):
        """헬스 체크 스레드를 시작합니다."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="TimescaleHealthChecker"
        )
        self._thread.start()
        logger.info("TimescaleHealthChecker 시작 (간격: %ds)", self._interval)

    def stop(self):
        """헬스 체크 스레드를 중지합니다."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._interval + 2)
        logger.info("TimescaleHealthChecker 중지")

    def check_once(self) -> tuple[str, str]:
        """단발 헬스 체크를 수행합니다.

        Returns:
            (status, message) 튜플
        """
        return self._check()

    # ------------------------------------------------------------------
    # 내부 로직
    # ------------------------------------------------------------------

    def _run(self):
        """백그라운드 스레드 루프."""
        while not self._stop_event.wait(self._interval):
            status, message = self._check()
            self._emit_health(status, message)

    def _check(self) -> tuple[str, str]:
        """실제 DB 연결 확인을 수행합니다.

        Returns:
            (STATUS_OK | STATUS_ERROR | STATUS_UNKNOWN, 설명 메시지) 튜플
        """
        if self._db_conn is None:
            return STATUS_UNKNOWN, "DB 연결이 설정되지 않았습니다."

        try:
            with self._db_conn.cursor() as cur:
                cur.execute("SELECT 1;")
            return STATUS_OK, "연결 정상"
        except Exception as exc:
            logger.warning("TimescaleDB 헬스 체크 실패: %s", exc)
            return STATUS_ERROR, str(exc)
