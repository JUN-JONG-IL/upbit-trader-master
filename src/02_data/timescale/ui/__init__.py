"""TimescaleDB UI 패키지"""

from .timescale_settings_dialog import TimescaleSettingsDialog
from .widget_timescale_settings import TimescaleClusterTab

__all__ = ["TimescaleSettingsDialog", "TimescaleClusterTab"]

# 모니터링 다이얼로그 안전 로드
try:
    from .timescale_monitor import TimescaleMonitorDialog  # noqa: F401
    __all__.append("TimescaleMonitorDialog")
except Exception:
    pass

# TimescaleDB 인라인 모니터 안전 로드 (레거시 구현)
try:
    from .timescale_monitor_legacy import TimescaleMonitor  # noqa: F401
    __all__.append("TimescaleMonitor")
except Exception:
    pass
