# base/ 폴더

## 목적
플랫폼의 **기본 인프라 및 저수준 유틸리티**를 제공합니다.

## 포함 모듈

### event_loop.py
asyncio 이벤트 루프 관리 (중복 초기화 방지)

**주요 기능**:
- Windows에서 `WindowsSelectorEventLoopPolicy` 설정 (aiodns 호환성)
- 전역 이벤트 루프 관리
- 중복 초기화 방지 메커니즘

**사용법**:
```python
from base import setup_event_loop, get_event_loop

# 1. 앱 시작 시 한 번만 호출
setup_event_loop()

# 2. 이벤트 루프 필요 시
loop = get_event_loop()
loop.run_until_complete(my_async_task())
```

**주의사항**:
- `setup_event_loop()`는 앱 시작 시 **단 한 번만** 호출
- 여러 번 호출해도 안전 (내부 플래그로 중복 방지)
- Windows 환경에서 WebSocket/aiodns 사용 시 필수

## 확장 계획
- `thread_pool.py`: 스레드 풀 관리
- `process_pool.py`: 프로세스 풀 관리
- `signal_handler.py`: OS 시그널 핸들링

---

**작성**: Copilot Workspace Refactor
**날짜**: 2026-03-05
