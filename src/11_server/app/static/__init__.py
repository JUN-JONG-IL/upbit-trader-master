"""
[Purpose]
- static 패키지 인입점(전역 상수와 상태/객체 내보냄)
[Responsibilities]
- from static import log, config, MIN_TRADE_PRICE, ... 등 편리한 외부 참조 지원
[Expose]
- 상수/객체/핵심 매니저 인스턴스 일괄 노출
"""
from .static import (
    MIN_TRADE_PRICE, FEES, FIAT, BASE_TIME_FORMAT, UPBIT_TIME_FORMAT,
    STRATEGY_DAILY_FINISH_TIME, EXTERNAL_TIMEOUT, INTERNAL_TIMEOUT, REQUEST_LIMIT, PING_INTERVAL,
    config, log, upbit, chart, account, signal_manager, signal_queue, strategy, data_manager, settings_start,
    realtime_manager,
)