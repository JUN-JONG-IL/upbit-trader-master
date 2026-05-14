"""
실시간 스트림 컴포넌트

[목적]
틱 데이터 수신기, 이벤트 라우터 등 실시간 스트리밍 핵심 컴포넌트를 제공합니다.

[주요 클래스]
- RealtimeStreamManager : 스트림 연결/관리
- TickReceiver          : 틱 데이터 수신기
- EventRouter           : 이벤트 라우팅
"""

__all__ = ['RealtimeStreamManager', 'TickReceiver', 'EventRouter']
