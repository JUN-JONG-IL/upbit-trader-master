# -*- coding: utf-8 -*-
"""
ForwardingRegistrar 모듈
- 역할: 외부(로그 수집기, WebSocket 리스너 등)로부터 로그 엔트리를 수신하여
  등록된 콜백들에게 전달(forward)하는 책임을 가집니다.
- StatisticsTabController는 이 모듈에서 ForwardingRegistrar를 import 하여
  register(callback)로 콜백을 등록하고, 외부 소스는 registrar.forward(entry)를 호출하면 됩니다.
- 최소한의 스레드 안전성, 예외 격리, 그리고 단순한 유닛 테스트용 동작을 제공합니다.
"""
from __future__ import annotations
import logging
import threading
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# 타입 별칭: 로그 엔트리은 사전 형태로 가정
LogEntry = Dict[str, Any]
ForwardCallback = Callable[[LogEntry], None]


class ForwardingRegistrar:
    """
    ForwardingRegistrar
    - register(callback): 콜백 등록 (callback(entry: Dict) -> None)
    - unregister(callback): 등록 해제
    - forward(entry): 등록된 모든 콜백에게 entry를 안전하게 전달
    - count / has_callbacks: 상태 확인 유틸리티
    사용 예:
        f = ForwardingRegistrar()
        f.register(controller.add_log_entry)
        # 외부 소스에서
        f.forward({"time": ..., "level": "INFO", "module": "...", "message": "..."})
    """

    def __init__(self) -> None:
        # 등록된 콜백 목록(순서를 보장). 스레드 안전하게 보호됩니다.
        self._callbacks: List[ForwardCallback] = []
        self._lock = threading.RLock()

    def register(self, callback: ForwardCallback) -> None:
        """콜백을 등록합니다. callable인지 확인하고 중복 등록을 방지합니다."""
        if not callable(callback):
            logger.debug("[ForwardingRegistrar] register 호출, 그러나 callback이 callable이 아님: %r", callback)
            return
        with self._lock:
            if callback in self._callbacks:
                # 이미 등록되어 있으면 중복 추가 금지
                return
            self._callbacks.append(callback)
            logger.debug("[ForwardingRegistrar] callback 등록: %r (총 %d)", callback, len(self._callbacks))

    def unregister(self, callback: ForwardCallback) -> None:
        """콜백을 등록 해제합니다. 존재하지 않아도 안전하게 동작합니다."""
        with self._lock:
            try:
                if callback in self._callbacks:
                    self._callbacks.remove(callback)
                    logger.debug("[ForwardingRegistrar] callback 해제: %r (남음 %d)", callback, len(self._callbacks))
            except Exception as exc:
                logger.debug("[ForwardingRegistrar] unregister 예외: %s", exc)

    def forward(self, entry: LogEntry) -> None:
        """
        주어진 로그 엔트리를 모든 등록된 콜백으로 전달합니다.
        - 콜백 호출 시 발생하는 예외는 개별적으로 격리(logging)하며 다른 콜백에 영향을 주지 않습니다.
        - 콜백 호출은 동기적으로(호출한 스레드에서) 수행됩니다. 필요시 비동기/백그라운드 전송을 확장할 수 있습니다.
        """
        # 안전 방어: entry는 dict 타입인지 검사
        if not isinstance(entry, dict):
            logger.debug("[ForwardingRegistrar] 전달된 entry가 dict 아님: %r", entry)
            return

        # 복사본 사용: 호출 중 콜백 목록 변경(등록/해제)이 있더라도 안전하게 동작하게 함
        with self._lock:
            callbacks_snapshot = list(self._callbacks)

        if not callbacks_snapshot:
            # 등록된 콜백이 없으면 조용히 반환
            return

        for cb in callbacks_snapshot:
            try:
                cb(entry)
            except Exception as exc:
                # 개별 콜백 실패는 로그로 남기고 계속 진행
                try:
                    logger.debug("[ForwardingRegistrar] callback %r 실행 중 예외: %s", cb, exc, exc_info=True)
                except Exception:
                    # logging 자체에서 오류가 발생하면 무시
                    pass

    def count(self) -> int:
        """현재 등록된 콜백 수를 반환합니다."""
        with self._lock:
            return len(self._callbacks)

    def has_callbacks(self) -> bool:
        """등록된 콜백이 하나라도 있는지 여부."""
        return self.count() > 0


# 외부에서 `from .statistics_tab_forwarding import ForwardingRegistrar`로 사용되므로
# __all__을 명시합니다.
__all__ = ["ForwardingRegistrar"]