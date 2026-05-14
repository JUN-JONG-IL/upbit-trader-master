"""
[Purpose]
- 전체 플랫폼의 중앙 이벤트 버스 (Pub/Sub 패턴)
- 모듈 간 느슨한 결합 (loose coupling)

[Responsibilities]
- 이벤트 구독/발행 관리
- 비동기 이벤트 처리
- 이벤트 히스토리 기록 (선택)

[Events]
- market.ticker: 실시간 시세 데이터
- market.orderbook: 호가 데이터
- trade.order_placed: 주문 체결
- strategy.signal: 전략 시그널
- ai.prediction: AI 예측 결과
"""
import logging
import time
from typing import Callable, Dict, List, Any
from collections import defaultdict
import asyncio

logger = logging.getLogger(__name__)


class EventBus:
    """중앙 이벤트 버스 (Pub/Sub 패턴)"""

    def __init__(self):
        self._sync_listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._async_listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._history: List[Dict[str, Any]] = []
        self._max_history = 1000

    def subscribe(self, event: str, callback: Callable, async_mode: bool = False):
        """
        이벤트 구독

        Args:
            event: 이벤트 이름 (예: "market.ticker")
            callback: 콜백 함수
            async_mode: 비동기 처리 여부
        """
        if async_mode:
            self._async_listeners[event].append(callback)
        else:
            self._sync_listeners[event].append(callback)

        logger.debug(f"Subscribed to event: {event} (async={async_mode})")

    def unsubscribe(self, event: str, callback: Callable):
        """이벤트 구독 해제"""
        if callback in self._sync_listeners[event]:
            self._sync_listeners[event].remove(callback)
        if callback in self._async_listeners[event]:
            self._async_listeners[event].remove(callback)

    def publish(self, event: str, data: Any):
        """
        이벤트 발행 (동기)

        Args:
            event: 이벤트 이름
            data: 이벤트 데이터
        """
        self._record_history(event, data)

        for callback in self._sync_listeners[event]:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Error in sync listener for {event}: {e}", exc_info=True)

    async def publish_async(self, event: str, data: Any):
        """
        이벤트 발행 (비동기)

        Args:
            event: 이벤트 이름
            data: 이벤트 데이터
        """
        self._record_history(event, data)

        tasks = []
        for callback in self._async_listeners[event]:
            tasks.append(asyncio.create_task(self._safe_async_call(callback, data, event)))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_async_call(self, callback: Callable, data: Any, event: str):
        """안전한 비동기 호출"""
        try:
            await callback(data)
        except Exception as e:
            logger.error(f"Error in async listener for {event}: {e}", exc_info=True)

    def _record_history(self, event: str, data: Any):
        """이벤트 히스토리 기록"""
        self._history.append({
            "event": event,
            "data": data,
            "timestamp": time.time(),
        })

        if len(self._history) > self._max_history:
            self._history.pop(0)

    def get_history(self, event: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """이벤트 히스토리 조회"""
        if event:
            filtered = [h for h in self._history if h["event"] == event]
            return filtered[-limit:]
        return self._history[-limit:]

    def clear_listeners(self, event: str = None):
        """리스너 초기화"""
        if event:
            self._sync_listeners[event].clear()
            self._async_listeners[event].clear()
        else:
            self._sync_listeners.clear()
            self._async_listeners.clear()


# 전역 인스턴스 (싱글톤)
event_bus = EventBus()
