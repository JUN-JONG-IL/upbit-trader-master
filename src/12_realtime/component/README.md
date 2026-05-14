# component/ — 실시간 스트림 컴포넌트

## 개요

WebSocket 연결, 틱 데이터 수신, 이벤트 라우팅을 담당하는 핵심 컴포넌트 모음입니다.

## 주요 클래스

| 클래스 | 파일 | 역할 |
|---|---|---|
| `RealtimeStreamManager` | `stream_manager.py` | WebSocket 스트림 연결/관리 |
| `TickReceiver` | `tick_receiver.py` | 틱 데이터 수신 및 파싱 |
| `EventRouter` | `event_router.py` | 이벤트를 구독자에게 라우팅 |

## 사용 예시

```python
from src.12_realtime.component import RealtimeStreamManager

manager = RealtimeStreamManager(symbols=["KRW-BTC"])
manager.on_tick(lambda tick: print(tick))
manager.start()
```
