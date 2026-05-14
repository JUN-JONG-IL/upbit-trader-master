#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kafka 브로커 연결 상태 확인 모듈

백그라운드 스레드에서 주기적으로 Kafka 브로커의 연결 가능 여부를 점검합니다.
"""

import threading
import socket
import time
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QObject, pyqtSignal

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


class KafkaHealthChecker(QObject if _HAS_QT else object):
    """
    Kafka 브로커 연결 상태 확인 클래스

    백그라운드 스레드로 주기적으로 브로커 TCP 연결을 시도하고
    결과를 콜백 또는 Qt 시그널로 전달합니다.
    """

    if _HAS_QT:
        # 상태 변경 시 (broker_address: str, is_healthy: bool) 전달
        health_changed = pyqtSignal(str, bool)

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        interval: int = 5,
        timeout: int = 3,
        on_result: Optional[Callable[[str, bool], None]] = None,
        parent=None,
    ):
        """
        KafkaHealthChecker 초기화

        Args:
            bootstrap_servers (str): 쉼표로 구분된 Kafka 브로커 주소 목록 (기본값: "localhost:9092").
            interval (int): 점검 주기 (초, 기본값: 5).
            timeout (int): TCP 연결 타임아웃 (초, 기본값: 3).
            on_result (callable, optional): (address, is_healthy) 를 받는 콜백 함수.
            parent: 부모 QObject (기본값: None).
        """
        if _HAS_QT:
            super().__init__(parent)
        self._bootstrap_servers = bootstrap_servers
        self._interval = interval
        self._timeout = timeout
        self._on_result = on_result
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def start(self):
        """백그라운드 헬스 체크 스레드를 시작합니다."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="kafka-health-checker")
        self._thread.start()
        logger.info("KafkaHealthChecker 시작 (서버: %s, 주기: %ds)", self._bootstrap_servers, self._interval)

    def stop(self):
        """백그라운드 헬스 체크 스레드를 중지합니다."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._interval + 1)
        logger.info("KafkaHealthChecker 중지")

    def check_now(self) -> dict:
        """
        즉시 모든 브로커 연결 상태를 점검하고 결과를 반환합니다.

        Returns:
            dict: {브로커주소(str): 연결가능여부(bool)} 매핑.
        """
        results = {}
        for address in self._parse_servers():
            results[address] = self._check_broker(address)
        return results

    def set_bootstrap_servers(self, servers: str):
        """
        브로커 주소를 동적으로 변경합니다.

        Args:
            servers (str): 쉼표로 구분된 Kafka 브로커 주소 목록.
        """
        self._bootstrap_servers = servers

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------

    def _run(self):
        """헬스 체크 루프 (백그라운드 스레드 진입점)"""
        while self._running:
            for address in self._parse_servers():
                is_healthy = self._check_broker(address)
                self._notify(address, is_healthy)
            time.sleep(self._interval)

    def _parse_servers(self) -> list:
        """
        bootstrap_servers 문자열을 파싱하여 주소 목록을 반환합니다.

        Returns:
            list: "host:port" 형식의 문자열 리스트.
        """
        return [s.strip() for s in self._bootstrap_servers.split(",") if s.strip()]

    def _check_broker(self, address: str) -> bool:
        """
        단일 브로커 주소에 TCP 연결을 시도합니다.

        Args:
            address (str): "host:port" 형식의 브로커 주소.

        Returns:
            bool: 연결 성공 시 True, 실패 시 False.
        """
        try:
            host, port_str = address.rsplit(":", 1)
            port = int(port_str)
            with socket.create_connection((host, port), timeout=self._timeout):
                return True
        except (OSError, ValueError) as exc:
            logger.debug("브로커 연결 실패 (%s): %s", address, exc)
            return False

    def _notify(self, address: str, is_healthy: bool):
        """
        결과를 콜백 및 Qt 시그널로 전달합니다.

        Args:
            address (str): 브로커 주소.
            is_healthy (bool): 연결 가능 여부.
        """
        if self._on_result:
            try:
                self._on_result(address, is_healthy)
            except Exception as exc:
                logger.error("헬스 체크 콜백 오류: %s", exc)
        if _HAS_QT:
            try:
                self.health_changed.emit(address, is_healthy)
            except Exception as exc:
                logger.debug("시그널 emit 오류: %s", exc)
