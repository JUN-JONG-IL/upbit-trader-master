# -*- coding: utf-8 -*-
"""
Smart Alert System - DB 모니터링 알림 관리

[기능]
- Redis Pub/Sub 기반 실시간 알림 수신
- 시스템 트레이 알림 표시
- 알림 레벨별 색상 구분 (오류/경고/정보)
- 알림 히스토리 관리 (최대 1000건)

[사용 예시]
    alert_manager = AlertManager()
    alert_manager.start_listening()  # 백그라운드 수신 시작
    alert_manager.stop_listening()   # 수신 중지

[Author] Copilot Workspace
[Created] 2026-04-15
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# Redis Pub/Sub 사용 가능 여부 확인
try:
    import redis  # type: ignore
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False
    logger.debug("[AlertManager] redis-py 없음 - Pub/Sub 비활성화")

# PyQt5 사용 가능 여부 확인
try:
    from PyQt5.QtCore import QObject, pyqtSignal, QTimer
    from PyQt5.QtWidgets import QSystemTrayIcon, QApplication
    from PyQt5.QtGui import QIcon
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    logger.debug("[AlertManager] PyQt5 없음 - 트레이 알림 비활성화")

# 알림 채널 설정
_ALERT_CHANNELS = [
    "alerts:critical",   # 긴급 알림
    "alerts:warning",    # 경고 알림
    "alerts:info",       # 정보 알림
]

# 최대 알림 히스토리 건수
_MAX_HISTORY = 1000


class AlertRecord:
    """알림 기록 데이터 클래스."""

    def __init__(self, level: str, source: str, message: str) -> None:
        """초기화.

        Args:
            level: 알림 레벨 ("ERROR", "WARNING", "INFO")
            source: 알림 소스 (DB명 또는 컴포넌트명)
            message: 알림 메시지
        """
        self.timestamp: datetime = datetime.now()
        self.level: str = level
        self.source: str = source
        self.message: str = message

    def formatted_time(self) -> str:
        """포맷된 시간 문자열 반환."""
        return self.timestamp.strftime("%H:%M:%S.%f")[:-3]

    def __repr__(self) -> str:
        return (
            f"AlertRecord({self.level}, {self.source}, "
            f"{self.formatted_time()}: {self.message})"
        )


if _HAS_QT:

    class AlertManager(QObject):
        """
        Smart Alert System - DB 모니터링 알림 관리자.

        Redis Pub/Sub으로 알림을 수신하여 시스템 트레이로 표시합니다.
        알림 히스토리를 관리하고 콜백을 통해 UI에 전달합니다.
        """

        # 알림 수신 시그널 (level, source, message)
        alert_received = pyqtSignal(str, str, str)

        def __init__(
            self,
            redis_host: str = "localhost",
            redis_port: int = 6379,
            parent: Optional[QObject] = None,
        ) -> None:
            """초기화.

            Args:
                redis_host: Redis 호스트 주소
                redis_port: Redis 포트 번호
                parent: 부모 QObject (선택)
            """
            super().__init__(parent)
            self._redis_host = redis_host
            self._redis_port = redis_port
            self._redis_client = None
            self._pubsub = None
            self._listen_thread: Optional[threading.Thread] = None
            self._running: bool = False
            self._history: List[AlertRecord] = []
            self._callbacks: List[Callable] = []
            self._tray_icon: Optional[QSystemTrayIcon] = None
            # 알림 수신 시 콜백 연결
            self.alert_received.connect(self._on_alert_received)

        def start_listening(self) -> None:
            """Redis Pub/Sub 수신을 시작합니다 (백그라운드 스레드)."""
            if not _HAS_REDIS:
                logger.warning("[AlertManager] redis-py 미설치 - 알림 수신 불가")
                return
            if self._running:
                logger.debug("[AlertManager] 이미 수신 중")
                return
            try:
                self._redis_client = redis.Redis(
                    host=self._redis_host,
                    port=self._redis_port,
                    decode_responses=True,
                    socket_connect_timeout=3,
                )
                self._pubsub = self._redis_client.pubsub()
                self._pubsub.subscribe(*_ALERT_CHANNELS)
                self._running = True
                self._listen_thread = threading.Thread(
                    target=self._listen_loop,
                    daemon=True,
                    name="AlertManager-Listen",
                )
                self._listen_thread.start()
                logger.info("[AlertManager] Redis Pub/Sub 수신 시작: %s:%d", self._redis_host, self._redis_port)
            except Exception as exc:
                logger.warning("[AlertManager] Redis 연결 실패: %s", exc)
                self._running = False

        def stop_listening(self) -> None:
            """Redis Pub/Sub 수신을 중지합니다."""
            self._running = False
            if self._pubsub:
                try:
                    self._pubsub.unsubscribe()
                    self._pubsub.close()
                except Exception:
                    pass
                self._pubsub = None
            if self._redis_client:
                try:
                    self._redis_client.close()
                except Exception:
                    pass
                self._redis_client = None
            logger.info("[AlertManager] 수신 중지")

        def _listen_loop(self) -> None:
            """백그라운드 스레드에서 Redis 메시지를 수신합니다."""
            try:
                for message in self._pubsub.listen():
                    if not self._running:
                        break
                    if message and message.get("type") == "message":
                        channel = message.get("channel", "")
                        data = message.get("data", "")
                        # 채널에 따라 레벨 결정
                        if "critical" in channel:
                            level = "ERROR"
                        elif "warning" in channel:
                            level = "WARNING"
                        else:
                            level = "INFO"
                        # 메인 스레드에 시그널 전송
                        self.alert_received.emit(level, channel, str(data))
            except Exception as exc:
                if self._running:
                    logger.warning("[AlertManager] 수신 루프 오류: %s", exc)

        def _on_alert_received(self, level: str, source: str, message: str) -> None:
            """알림 수신 처리 (메인 스레드에서 실행).

            Args:
                level: 알림 레벨
                source: 알림 소스
                message: 알림 메시지
            """
            # 히스토리에 추가 (최대 1000건 초과 시 오래된 것 삭제)
            record = AlertRecord(level, source, message)
            self._history.append(record)
            if len(self._history) > _MAX_HISTORY:
                self._history.pop(0)
            # 시스템 트레이 알림 표시
            self._show_tray_notification(level, message)
            # 등록된 콜백 호출
            for callback in self._callbacks:
                try:
                    callback(record)
                except Exception as exc:
                    logger.debug("[AlertManager] 콜백 오류: %s", exc)

        def _show_tray_notification(self, level: str, message: str) -> None:
            """시스템 트레이 알림을 표시합니다.

            Args:
                level: 알림 레벨
                message: 표시할 메시지
            """
            if not _HAS_QT:
                return
            try:
                app = QApplication.instance()
                if app is None:
                    return
                if self._tray_icon is None:
                    self._tray_icon = QSystemTrayIcon(app)
                    self._tray_icon.show()
                # 레벨별 아이콘 설정
                if level == "ERROR":
                    icon_type = QSystemTrayIcon.Critical
                    title = "🔴 긴급 알림"
                elif level == "WARNING":
                    icon_type = QSystemTrayIcon.Warning
                    title = "⚠ 경고"
                else:
                    icon_type = QSystemTrayIcon.Information
                    title = "ℹ 정보"
                self._tray_icon.showMessage(title, message, icon_type, 5000)
            except Exception as exc:
                logger.debug("[AlertManager] 트레이 알림 실패: %s", exc)

        def add_alert_callback(self, callback: Callable) -> None:
            """알림 수신 시 호출할 콜백을 등록합니다.

            Args:
                callback: AlertRecord를 인자로 받는 콜백 함수
            """
            if callback not in self._callbacks:
                self._callbacks.append(callback)

        def remove_alert_callback(self, callback: Callable) -> None:
            """등록된 콜백을 제거합니다.

            Args:
                callback: 제거할 콜백 함수
            """
            if callback in self._callbacks:
                self._callbacks.remove(callback)

        def publish_alert(
            self, level: str, source: str, message: str
        ) -> None:
            """알림을 Redis Pub/Sub으로 발행합니다.

            Args:
                level: 알림 레벨 ("ERROR", "WARNING", "INFO")
                source: 알림 소스
                message: 알림 메시지
            """
            if not _HAS_REDIS or not self._redis_client:
                # Redis 없으면 직접 로컬 처리
                self.alert_received.emit(level, source, message)
                return
            try:
                if level == "ERROR":
                    channel = "alerts:critical"
                elif level == "WARNING":
                    channel = "alerts:warning"
                else:
                    channel = "alerts:info"
                self._redis_client.publish(channel, f"[{source}] {message}")
            except Exception as exc:
                logger.debug("[AlertManager] 알림 발행 실패: %s", exc)
                # 발행 실패 시 로컬 처리
                self.alert_received.emit(level, source, message)

        def get_history(self, level: Optional[str] = None) -> List[AlertRecord]:
            """알림 히스토리를 반환합니다.

            Args:
                level: 필터링할 레벨 (None이면 전체 반환)

            Returns:
                AlertRecord 목록 (최신순)
            """
            if level:
                filtered = [r for r in self._history if r.level == level]
                return list(reversed(filtered))
            return list(reversed(self._history))

        def clear_history(self) -> None:
            """알림 히스토리를 초기화합니다."""
            self._history.clear()

else:

    class AlertManager:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 알림 관리자."""

        def __init__(self, *args, **kwargs) -> None:
            logger.warning("[AlertManager] PyQt5 미설치 - 더미 클래스 사용")
            self._history: List[AlertRecord] = []
            self._callbacks: List[Callable] = []

        def start_listening(self) -> None:
            """더미 구현."""
            pass

        def stop_listening(self) -> None:
            """더미 구현."""
            pass

        def add_alert_callback(self, callback: Callable) -> None:
            """더미 구현."""
            pass

        def remove_alert_callback(self, callback: Callable) -> None:
            """더미 구현."""
            pass

        def publish_alert(self, level: str, source: str, message: str) -> None:
            """더미 구현."""
            pass

        def get_history(self, level: Optional[str] = None) -> List[AlertRecord]:
            """더미 구현."""
            return []

        def clear_history(self) -> None:
            """더미 구현."""
            pass
