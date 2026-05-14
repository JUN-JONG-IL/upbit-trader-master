"""
실시간 데이터 스트리밍 모듈

[목적]
WebSocket 기반 실시간 시세 스트림, 틱 데이터 수신, 실시간 UI 업데이트를 제공합니다.

[구조]
- component/ : 실시간 스트림 컴포넌트 (틱 수신기, 이벤트 라우터)
- workers/   : 백그라운드 스트리밍 워커 (WebSocket 연결 유지, 재연결)
- ui/        : 실시간 데이터 표시 위젯

[주요 컴포넌트]
- RealtimeStreamManager : 실시간 스트림 연결/관리
- TickReceiver          : 틱 데이터 수신기
- StreamWorker          : WebSocket 백그라운드 워커
"""
from . import component
from . import workers
from . import ui

__all__ = ['component', 'workers', 'ui']
