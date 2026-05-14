#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ClickHouse 연결 상태 확인 컨트롤러"""

import threading
import logging
from typing import Callable, Optional

try:
    import urllib.request
    import urllib.error
    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False

try:
    from PyQt5.QtCore import QObject, pyqtSignal
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

# 헬스 체크 기본값
_DEFAULT_TIMEOUT = 3.0
_DEFAULT_INTERVAL = 10.0


class ClickHouseHealthChecker(QObject if _HAS_QT else object):
    """ClickHouse HTTP 엔드포인트 연결 상태를 주기적으로 확인하는 컨트롤러.

    백그라운드 스레드에서 지정된 간격으로 ClickHouse ping 엔드포인트에
    HTTP 요청을 보내 연결 가능 여부를 판단합니다.

    Signals:
        status_changed(bool, str): 연결 상태 변경 시 방출 (성공 여부, 메시지)
    """

    if _HAS_QT:
        status_changed = pyqtSignal(bool, str)

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8123,
        interval: float = _DEFAULT_INTERVAL,
        timeout: float = _DEFAULT_TIMEOUT,
        parent=None,
    ):
        """초기화.

        Args:
            host: ClickHouse 서버 호스트명 또는 IP 주소
            port: ClickHouse HTTP 포트 (기본값: 8123)
            interval: 체크 주기(초) (기본값: 10초)
            timeout: HTTP 요청 타임아웃(초) (기본값: 3초)
            parent: 부모 QObject (선택)
        """
        if _HAS_QT:
            super().__init__(parent)
        self._host = host
        self._port = port
        self._interval = interval
        self._timeout = timeout
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_status: Optional[bool] = None
        self._on_status_change: Optional[Callable[[bool, str], None]] = None

    @property
    def url(self) -> str:
        """ClickHouse ping URL을 반환합니다."""
        return f"http://{self._host}:{self._port}/ping"

    def set_connection(self, host: str, port: int) -> None:
        """연결 대상 호스트와 포트를 변경합니다.

        Args:
            host: 새로운 호스트명 또는 IP 주소
            port: 새로운 HTTP 포트 번호
        """
        self._host = host
        self._port = port
        logger.debug("헬스체크 대상 변경: %s:%d", host, port)

    def set_callback(self, callback: Callable[[bool, str], None]) -> None:
        """상태 변경 콜백 함수를 등록합니다 (비-Qt 환경용).

        Args:
            callback: (is_connected: bool, message: str) → None 형태의 콜백
        """
        self._on_status_change = callback

    def start(self) -> None:
        """백그라운드 헬스 체크 스레드를 시작합니다.

        이미 실행 중인 경우 아무 동작도 하지 않습니다.
        """
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="ch-health-checker"
        )
        self._thread.start()
        logger.info("ClickHouse 헬스 체커 시작: %s", self.url)

    def stop(self) -> None:
        """백그라운드 헬스 체크 스레드를 중지합니다."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._timeout + 1)
        logger.info("ClickHouse 헬스 체커 중지")

    def check_once(self) -> tuple:
        """연결 상태를 즉시 한 번 확인합니다.

        Returns:
            (is_connected: bool, message: str) 튜플
        """
        try:
            req = urllib.request.Request(self.url, method="GET")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode().strip()
                if resp.status == 200 and body == "Ok.":
                    return True, f"연결 성공 ({self._host}:{self._port})"
                return False, f"예상치 못한 응답: HTTP {resp.status} / {body!r}"
        except urllib.error.URLError as exc:
            return False, f"연결 실패: {exc.reason}"
        except Exception as exc:
            return False, f"오류: {exc}"

    def _run_loop(self) -> None:
        """주기적으로 헬스 체크를 실행하는 내부 루프."""
        stop_event = threading.Event()
        while self._running:
            ok, msg = self.check_once()
            if ok != self._last_status:
                self._last_status = ok
                logger.info("ClickHouse 상태 변경 → %s: %s", ok, msg)
                self._notify(ok, msg)
            stop_event.wait(timeout=self._interval)

    def _notify(self, ok: bool, msg: str) -> None:
        """상태 변경을 Qt 시그널 또는 콜백으로 전달합니다.

        Args:
            ok: 연결 성공 여부
            msg: 상태 메시지
        """
        if _HAS_QT:
            try:
                self.status_changed.emit(ok, msg)
                return
            except RuntimeError:
                pass
        if self._on_status_change:
            self._on_status_change(ok, msg)
