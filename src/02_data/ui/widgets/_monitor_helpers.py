# -*- coding: utf-8 -*-
"""
Monitor Helpers — 시스템 모니터 표준화 헬퍼 (Phase 6, 보수적)

[목적]
    각 DB 모니터(``clickhouse/kafka/mongodb/postgres/redis/timescale``)의 탭들이
    공통적으로 필요로 하는 패턴을 제공한다. 잘 동작 중인 기존 코드를 변경하지
    않고, 신규 위젯 / 새 탭 / 회귀 핫픽스에서 *선택적으로* 사용한다.

[제공 기능]
    1. ``DEFAULT_REFRESH_INTERVAL_MS`` — 표준 폴링 주기 (15s)
    2. ``guard_start(worker, callback=None)`` — ``isRunning()`` 가드 + 시작
    3. ``stop_worker_safe(worker)`` — quit/wait 패턴 안전 종료
    4. ``ensure_single_timer(host, attr, interval_ms, slot)`` — 중복 ``QTimer``
       방지 (재호출 시 기존 타이머 stop 후 재배선)

[의존성]
    PyQt5 가 설치되지 않은 환경에서도 import 가능하도록 가드.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# 표준 폴링 주기 (메모리 룰: 성능 민감 DB 탭은 15s)
DEFAULT_REFRESH_INTERVAL_MS: int = 15_000

try:
    from PyQt5.QtCore import QTimer
    _HAS_QT = True
except ImportError:  # pragma: no cover
    QTimer = None  # type: ignore
    _HAS_QT = False


def guard_start(worker: Any, callback: Optional[Callable[[], None]] = None) -> bool:
    """``QThread`` Worker 시작 전 ``isRunning()`` 가드.

    워커가 이미 실행 중이면 새로 시작하지 않고 ``False`` 를 반환한다.
    중복 refresh 호출에 의한 자원 누수/UI 깜박임을 방지하기 위한 표준 패턴.
    """
    if worker is None:
        return False
    try:
        if hasattr(worker, "isRunning") and worker.isRunning():
            return False
        if callback is not None and hasattr(worker, "finished"):
            try:
                worker.finished.connect(callback)
            except Exception:
                pass
        if hasattr(worker, "start"):
            worker.start()
            return True
    except Exception as exc:
        logger.debug("[monitor_helpers] guard_start 실패: %s", exc)
    return False


def stop_worker_safe(worker: Any, wait_ms: int = 2000) -> None:
    """워커 안전 종료 (quit → wait → 마지막 수단으로 terminate)."""
    if worker is None:
        return
    try:
        if hasattr(worker, "isRunning") and not worker.isRunning():
            return
        if hasattr(worker, "stop"):
            try:
                worker.stop()
            except Exception:
                pass
        if hasattr(worker, "quit"):
            try:
                worker.quit()
            except Exception:
                pass
        if hasattr(worker, "wait"):
            try:
                worker.wait(int(wait_ms))
            except Exception:
                pass
        if hasattr(worker, "isRunning") and worker.isRunning():
            if hasattr(worker, "terminate"):
                try:
                    worker.terminate()
                    if hasattr(worker, "wait"):
                        worker.wait(500)
                except Exception:
                    pass
    except Exception as exc:
        logger.debug("[monitor_helpers] stop_worker_safe 실패: %s", exc)


def ensure_single_timer(
    host: Any,
    attr: str,
    interval_ms: int,
    slot: Callable[[], None],
) -> Any:
    """``host`` 에 ``attr`` 이름으로 단 하나의 ``QTimer`` 만 존재하도록 보장.

    같은 호스트에서 본 함수를 다시 호출하면 기존 타이머는 stop / disconnect
    후 재배선된다. 이로써 ``refresh_timer`` 가 중복 등록되는 흔한 회귀를
    예방한다.
    """
    if not _HAS_QT or QTimer is None:  # pragma: no cover
        return None
    existing = getattr(host, attr, None)
    if existing is not None:
        try:
            existing.stop()
        except Exception:
            pass
        try:
            existing.timeout.disconnect()
        except Exception:
            pass
    timer = QTimer(host)
    timer.setInterval(int(max(1, interval_ms)))
    timer.timeout.connect(slot)
    setattr(host, attr, timer)
    timer.start()
    return timer


__all__ = [
    "DEFAULT_REFRESH_INTERVAL_MS",
    "guard_start",
    "stop_worker_safe",
    "ensure_single_timer",
]
