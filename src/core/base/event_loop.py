"""
[Purpose]
이벤트 루프 통합 관리 (중복 초기화 방지)

[Responsibilities]
- WindowsSelectorEventLoopPolicy 전역 설정
- 이벤트 루프 생성 및 관리
- 중복 초기화 방지

[Main Flow]
1. setup_event_loop() 호출 시 전역 플래그 체크
2. 이미 초기화되었으면 로그만 출력하고 리턴
3. Windows 플랫폼이면 WindowsSelectorEventLoopPolicy 설정
4. 전역 플래그 설정

[Dependencies]
- asyncio
- sys (platform detection)

[Author] Copilot Phase 5
[Created] 2026-02-04
"""

import asyncio
import sys
import logging

# 전역 초기화 플래그
_event_loop_initialized = False
_logger = logging.getLogger(__name__)


def setup_event_loop():
    """
    이벤트 루프 초기화 (Windows aiodns 문제 해결)
    
    [Purpose]
    - Windows에서 aiodns 사용 시 ProactorEventLoop 문제 해결
    - WindowsSelectorEventLoopPolicy로 변경
    
    [Usage]
    - 앱 시작 시 한 번만 호출
    - 여러 번 호출해도 중복 초기화하지 않음
    
    [Example]
    ```python
    from base.event_loop import setup_event_loop
    
    setup_event_loop()
    ```
    """
    global _event_loop_initialized
    
    if _event_loop_initialized:
        _logger.debug("[EventLoop] 이미 초기화됨 (중복 방지)")
        return
    
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        _logger.info("[EventLoop] ✅ WindowsSelectorEventLoopPolicy 설정 완료")
    else:
        _logger.info("[EventLoop] ✅ 이벤트 루프 초기화 완료 (non-Windows)")
    
    _event_loop_initialized = True


def get_event_loop():
    """
    이벤트 루프 가져오기
    
    [Purpose]
    - 현재 실행 중인 이벤트 루프 반환
    - 없으면 새로 생성
    
    [Returns]
    - asyncio.AbstractEventLoop
    
    [Usage]
    ```python
    from base.event_loop import get_event_loop
    
    loop = get_event_loop()
    loop.run_until_complete(my_coroutine())
    ```
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop


def is_initialized():
    """
    이벤트 루프가 초기화되었는지 확인
    
    [Returns]
    - bool: 초기화 여부
    """
    return _event_loop_initialized
