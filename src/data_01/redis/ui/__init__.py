# Safe package init for src.data_01.redis.ui
# Avoid hard import errors when some UI classes are missing during headless imports.

from __future__ import annotations

import logging
logger = logging.getLogger("src.data_01.redis.ui")

# Try to import optional UI components; tolerate failures (headless/IDE runs).
try:
    from .redis_settings_dialog import RedisSettingsDialog  # type: ignore
except Exception as e:
    RedisSettingsDialog = None
    logger.debug("redis_settings_dialog not importable: %s", e)

try:
    from .widget_redis_settings import RedisClusterTab  # type: ignore
except Exception as e:
    RedisClusterTab = None
    logger.debug("widget_redis_settings.RedisClusterTab not importable: %s", e)

__all__ = []
if RedisSettingsDialog is not None:
    __all__.append("RedisSettingsDialog")
if RedisClusterTab is not None:
    __all__.append("RedisClusterTab")

# Î™®Îãà?∞ÎßÅ ?§Ïù¥?ºÎ°úÍ∑??àÏ†Ñ Î°úÎìú
try:
    from .redis_monitor import RedisMonitorDialog  # type: ignore  # noqa: F401
    __all__.append("RedisMonitorDialog")
except Exception as e:
    logger.debug("redis_monitor.RedisMonitorDialog not importable: %s", e)

