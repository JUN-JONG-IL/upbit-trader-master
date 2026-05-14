"""전략 관리 위젯"""
try:
    from .ui.widget_strategy_manager import StrategyManagerWidget
    __all__ = ["StrategyManagerWidget"]
except ImportError:
    __all__ = []
