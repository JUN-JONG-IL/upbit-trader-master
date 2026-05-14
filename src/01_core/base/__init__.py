"""
[Purpose]
- Base utilities and infrastructure modules

[Responsibilities]
- Event loop management
- Common utilities shared across modules

[Author] Copilot Phase 5
[Created] 2026-02-04
"""

from .event_loop import setup_event_loop, get_event_loop

__all__ = [
    'setup_event_loop',
    'get_event_loop',
]
