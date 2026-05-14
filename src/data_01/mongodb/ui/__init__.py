"""MongoDB UI 패키지"""

from .mongodb_settings_dialog import MongoDBSettingsDialog

__all__ = ["MongoDBSettingsDialog"]

# 모니터링 다이얼로그 안전 로드
try:
    from .mongodb_monitor import MongoDBMonitorDialog  # noqa: F401
    __all__.append("MongoDBMonitorDialog")
except Exception:
    pass
