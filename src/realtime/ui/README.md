# ui/ — 실시간 데이터 표시 위젯

## 개요

실시간 시세 데이터와 스트림 연결 상태를 표시하는 PyQt5 위젯 모음입니다.

## 주요 클래스

| 클래스 | 파일 | 역할 |
|---|---|---|
| `RealtimeWidget` | `widget_realtime.py` | 실시간 데이터 표시 메인 위젯 |
| `StreamStatusWidget` | `widget_stream_status.py` | WebSocket 연결 상태 표시 |

## 사용 예시

```python
from src.realtime.ui import RealtimeWidget

widget = RealtimeWidget()
widget.show()
```
