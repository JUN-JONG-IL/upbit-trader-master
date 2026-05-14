#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MongoDB 연결 상태 확인 컨트롤러 모듈"""

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class MongoHealthChecker:
    """MongoDB 연결 상태를 주기적으로 확인하는 컨트롤러.

    백그라운드 스레드에서 MongoDB 서버에 ping 명령을 보내
    연결 가능 여부를 확인합니다. 상태 변화 시 콜백을 호출합니다.

    사용 예시::

        checker = MongoHealthChecker(client, interval=10)
        checker.on_status_change = lambda ok, msg: print(ok, msg)
        checker.start()
        ...
        checker.stop()
    """

    def __init__(self, mongo_client=None, interval: int = 10):
        """초기화.

        Args:
            mongo_client: MongoDB 클라이언트 인스턴스.
            interval: 상태 확인 주기 (초). 기본값 10.
        """
        self._client = mongo_client
        self._interval = interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_status: Optional[bool] = None
        # 상태 변화 시 호출될 콜백 (is_ok: bool, message: str) -> None
        self.on_status_change: Optional[Callable[[bool, str], None]] = None

    def set_client(self, client) -> None:
        """MongoDB 클라이언트를 교체합니다.

        Args:
            client: 새 MongoDB 클라이언트.
        """
        self._client = client

    def set_interval(self, seconds: int) -> None:
        """상태 확인 주기를 변경합니다.

        Args:
            seconds: 새 주기 (초).
        """
        self._interval = max(1, seconds)

    def start(self) -> None:
        """백그라운드 상태 확인 스레드를 시작합니다."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="MongoHealthChecker"
        )
        self._thread.start()
        logger.info("MongoHealthChecker 시작 (주기: %ds)", self._interval)

    def stop(self) -> None:
        """백그라운드 상태 확인 스레드를 중지합니다."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 2)
            self._thread = None
        logger.info("MongoHealthChecker 중지")

    def check_now(self) -> tuple:
        """즉시 MongoDB 연결 상태를 확인합니다.

        Returns:
            (is_ok: bool, message: str) 튜플.
        """
        return self._ping()

    def _run_loop(self) -> None:
        """상태 확인 루프 (스레드 내에서 실행)."""
        while self._running:
            is_ok, message = self._ping()
            if is_ok != self._last_status:
                self._last_status = is_ok
                if self.on_status_change is not None:
                    try:
                        self.on_status_change(is_ok, message)
                    except Exception as exc:
                        logger.warning("상태 변화 콜백 오류: %s", exc)
            for _ in range(self._interval * 10):
                if not self._running:
                    break
                time.sleep(0.1)

    def _ping(self) -> tuple:
        """MongoDB 서버에 ping 명령을 보냅니다.

        Returns:
            (is_ok: bool, message: str) 튜플.
        """
        if self._client is None:
            return False, "클라이언트가 설정되지 않았습니다."
        try:
            self._client.admin.command("ping")
            return True, "연결 정상"
        except Exception as exc:
            return False, f"연결 실패: {exc}"
