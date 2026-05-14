# src/realtime — 실시간 데이터 스트리밍

## 개요

업비트 WebSocket API를 통해 실시간 시세 데이터를 수신하고, 틱 단위 이벤트를 처리하며, 연결 유지 및 자동 재연결을 관리하는 모듈입니다.

## 디렉토리 구조

```
src/realtime/
├── __init__.py          # 패키지 진입점
├── README.md            # 이 파일
├── component/           # 실시간 스트림 컴포넌트
│   ├── __init__.py
│   └── README.md
├── workers/             # 백그라운드 스트리밍 워커
│   ├── __init__.py
│   └── README.md
└── ui/                  # 실시간 데이터 표시 위젯
    ├── __init__.py
    └── README.md
```

## 하위 모듈 설명

### component/ — 실시간 스트림 컴포넌트

WebSocket 연결, 틱 데이터 수신기, 이벤트 라우팅 등 핵심 스트리밍 컴포넌트를 제공합니다.

**주요 클래스**:
- `RealtimeStreamManager` : 스트림 연결/관리 (업비트 WebSocket)
- `TickReceiver` : 틱 데이터 수신 및 파싱
- `EventRouter` : 수신 이벤트를 구독자에게 라우팅

### workers/ — 백그라운드 스트리밍 워커

연결 유지, 자동 재연결, 데이터 버퍼링 등 백그라운드 처리를 담당합니다.

**주요 클래스**:
- `StreamWorker` : WebSocket 스트리밍 백그라운드 워커
- `ReconnectWorker` : 연결 끊김 시 자동 재연결 워커
- `BufferWorker` : 수신 데이터 버퍼링 및 배치 처리

### ui/ — 실시간 데이터 표시 위젯

실시간 시세, 스트림 상태를 PyQt5 위젯으로 표시합니다.

**주요 클래스**:
- `RealtimeWidget` : 실시간 데이터 표시 메인 위젯
- `StreamStatusWidget` : WebSocket 연결 상태 표시 위젯

## 사용 예시

```python
from src.realtime.component import RealtimeStreamManager

manager = RealtimeStreamManager()
manager.subscribe(["KRW-BTC", "KRW-ETH"])
manager.start()
```

## 의존성

- `src/core/` : 이벤트 버스, 기본 설정
- `src/data_01/` : Redis PubSub (실시간 데이터 전달)
- `src/market/` : 시장 데이터 모델

## 참고 문서

- [`work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md`](../../work_order/1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md)
- [`work_order/DB설계.md`](../../work_order/DB설계.md) — TimescaleDB 틱 데이터 스키마
