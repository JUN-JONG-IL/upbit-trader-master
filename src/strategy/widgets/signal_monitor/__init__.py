"""실시간 시그널 모니터링 위젯"""
try:
    from .ui.widget_signal_monitor import SignalMonitorWidget
    __all__ = ["SignalMonitorWidget"]
except ImportError:
    __all__ = []
