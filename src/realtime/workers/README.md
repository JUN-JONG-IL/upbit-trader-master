# workers/ — 실시간 스트리밍 워커

## 개요

WebSocket 연결 유지, 자동 재연결, 데이터 버퍼링을 처리하는 백그라운드 워커 모음입니다.

## 주요 클래스

| 클래스 | 파일 | 역할 |
|---|---|---|
| `StreamWorker` | `stream_worker.py` | WebSocket 스트리밍 백그라운드 워커 |
| `ReconnectWorker` | `reconnect_worker.py` | 연결 끊김 시 자동 재연결 |
| `BufferWorker` | `buffer_worker.py` | 데이터 버퍼링 및 배치 처리 |

## 사용 예시

```python
from src.realtime.workers import StreamWorker

worker = StreamWorker(symbols=["KRW-BTC", "KRW-ETH"])
await worker.run()
```
