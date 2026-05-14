# -*- coding: utf-8 -*-
"""
DB 헬스 체크 워커 — 별도 스레드에서 실행하여 UI 블로킹 방지

[책임]
- QThreadPool 을 활용한 비동기 DB 상태 체크
- 체크 완료 시 pyqtSignal 로 결과 전달 (Thread-Safe)
"""
from __future__ import annotations

import logging
from typing import Callable, Dict

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    logger.debug("[HealthChecker] PyQt5 없음 — 더미 클래스 사용")


# DB 헬스 체크 워커 풀 최대 스레드 수 (다수의 DB 동시 체크 지원)
_MAX_HEALTH_CHECK_WORKERS = 16


if _HAS_QT:
    class HealthCheckWorker(QRunnable):
        """DB 연결 상태 체크 워커 (스레드 풀에서 실행)"""

        def __init__(self, check_fn: Callable, callback: Callable) -> None:
            super().__init__()
            self.check_fn = check_fn
            self.callback = callback

        def run(self) -> None:
            """백그라운드에서 DB 체크 실행"""
            try:
                result = self.check_fn()
                self.callback(result)
            except Exception as exc:
                logger.debug("[HealthCheckWorker] 체크 실패: %s", exc)
                self.callback({})

    class HealthChecker(QObject):
        """
        DB 헬스 체크 컨트롤러

        - 별도 스레드에서 DB 연결 상태 확인 (UI 블로킹 없음)
        - 결과는 health_updated 시그널로 전달
        """

        # 시그널: {서비스명: 정상여부}
        health_updated = pyqtSignal(dict)

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.thread_pool = QThreadPool.globalInstance()
            # 최대 워커 수 설정 (다수의 DB 동시 체크 지원)
            self.thread_pool.setMaxThreadCount(_MAX_HEALTH_CHECK_WORKERS)

        def check_all_async(self, check_fn: Callable) -> None:
            """
            비동기로 모든 DB 체크 실행

            Args:
                check_fn: DB 상태를 반환하는 함수 (반환값: dict)
            """
            worker = HealthCheckWorker(
                check_fn=check_fn,
                callback=self._on_check_complete,
            )
            self.thread_pool.start(worker)

        def _on_check_complete(self, result: Dict[str, bool]) -> None:
            """체크 완료 시 시그널 발송"""
            self.health_updated.emit(result)

        def run_check(self) -> None:
            """수동으로 DB 헬스 체크를 실행합니다 (새로고침 버튼 및 자동 갱신용)."""
            try:
                from .service_checker import ServiceChecker
                checker = ServiceChecker()
                self.check_all_async(checker.check_all)
            except Exception as exc:
                logger.error("[HealthChecker] 수동 체크 실패: %s", exc, exc_info=True)
                self.health_updated.emit({})

else:
    class HealthChecker:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""

        def __init__(self, parent=None) -> None:
            logger.warning("[HealthChecker] PyQt5 미설치 — 더미 인스턴스 생성")

        def check_all_async(self, check_fn: Callable) -> None:
            """더미 메서드 (아무 동작도 하지 않음)"""

        def run_check(self) -> None:
            """더미 메서드 (아무 동작도 하지 않음)"""
