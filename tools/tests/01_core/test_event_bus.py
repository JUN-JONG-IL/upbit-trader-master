"""
EventBus 테스트
"""
import pytest
from events import EventBus


def test_event_bus_sync():
    """동기 이벤트 테스트"""
    bus = EventBus()
    received = []

    def handler(data):
        received.append(data)

    bus.subscribe("test.event", handler)
    bus.publish("test.event", {"value": 123})

    assert len(received) == 1
    assert received[0]["value"] == 123


def test_event_bus_unsubscribe():
    """구독 해제 테스트"""
    bus = EventBus()
    received = []

    def handler(data):
        received.append(data)

    bus.subscribe("test.unsub", handler)
    bus.unsubscribe("test.unsub", handler)
    bus.publish("test.unsub", {"value": 999})

    assert len(received) == 0


def test_event_bus_multiple_listeners():
    """다중 리스너 테스트"""
    bus = EventBus()
    results = []

    def handler_a(data):
        results.append(("a", data))

    def handler_b(data):
        results.append(("b", data))

    bus.subscribe("test.multi", handler_a)
    bus.subscribe("test.multi", handler_b)
    bus.publish("test.multi", "hello")

    assert len(results) == 2
    assert ("a", "hello") in results
    assert ("b", "hello") in results


def test_event_bus_history():
    """이벤트 히스토리 테스트"""
    bus = EventBus()
    bus.publish("hist.event", {"x": 1})
    bus.publish("hist.event", {"x": 2})

    history = bus.get_history("hist.event")
    assert len(history) == 2
    assert history[0]["data"]["x"] == 1
    assert history[1]["data"]["x"] == 2


def test_event_bus_clear_listeners():
    """리스너 초기화 테스트"""
    bus = EventBus()
    received = []

    def handler(data):
        received.append(data)

    bus.subscribe("clear.event", handler)
    bus.clear_listeners("clear.event")
    bus.publish("clear.event", "data")

    assert len(received) == 0


def test_event_bus_error_isolation():
    """리스너 예외 격리 테스트 - 하나가 실패해도 다음 리스너 실행"""
    bus = EventBus()
    results = []

    def bad_handler(data):
        raise ValueError("intentional error")

    def good_handler(data):
        results.append(data)

    bus.subscribe("err.event", bad_handler)
    bus.subscribe("err.event", good_handler)
    bus.publish("err.event", "test")

    assert len(results) == 1
    assert results[0] == "test"


@pytest.mark.asyncio
async def test_event_bus_async():
    """비동기 이벤트 테스트"""
    bus = EventBus()
    received = []

    async def handler(data):
        received.append(data)

    bus.subscribe("test.async", handler, async_mode=True)
    await bus.publish_async("test.async", {"value": 456})

    assert len(received) == 1
    assert received[0]["value"] == 456


@pytest.mark.asyncio
async def test_event_bus_async_multiple():
    """비동기 다중 리스너 테스트"""
    bus = EventBus()
    results = []

    async def handler_a(data):
        results.append(("a", data))

    async def handler_b(data):
        results.append(("b", data))

    bus.subscribe("async.multi", handler_a, async_mode=True)
    bus.subscribe("async.multi", handler_b, async_mode=True)
    await bus.publish_async("async.multi", "ping")

    assert len(results) == 2
