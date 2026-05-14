"""
[Purpose]
Core infrastructure and common modules for upbit-trader platform

[Responsibilities]
- Authentication (auth)
- Configuration management (config)
- Base infrastructure (base)
- Common utilities (utils)
- Event bus (events)
- Dependency injection (di)

[Structure]
- auth/: User authentication and login UI
- base/: Event loop and low-level infrastructure
- config/: YAML configuration loading
- events/: Central event bus (Pub/Sub)
- di/: Dependency injection container
- utils/: Common utilities (logging, debounce, throttle, etc.)

[Import Guidelines] ⚠️
- src/ 내부에서는 'src.' 접두사 사용 금지
- 올바른 예: from core.events import event_bus
- 잘못된 예: from [src].01_core.events import event_bus  # src. 접두사 금지

[Author] Copilot Workspace Refactor
[Created] 2026-03-05
"""

# 주요 모듈 re-export
from . import auth
from . import base
from . import config
from . import utils
from .events import EventBus, event_bus
from .di import DIContainer, container

__all__ = [
    'auth',
    'base',
    'config',
    'utils',
    'EventBus',
    'event_bus',
    'DIContainer',
    'container',
]