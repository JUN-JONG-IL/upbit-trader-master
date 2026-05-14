# -*- coding: utf-8 -*-
"""
05_strategy package (기관급 자동매매 전략 시스템) - lazy import 버전

설계/목적:
- 패키지 임포트 시 하위 모듈들을 한꺼번에 불러와 발생하는 ModuleNotFoundError / 불필요한 초기화 비용
  등을 방지하기 위해 '지연 로딩(lazy import)'을 적용합니다.
- PEP 562의 모듈 레벨 __getattr__ / __dir__ 기법을 사용하여, 실제로 호출되는 심볼만 import 하도록 처리합니다.
- shim 생성/파일 이동은 하지 않습니다. 내부 경로는 상대 임포트(패키지 내부)로 안전하게 처리합니다.
- 우선순위 설정과 AI/ML 활성화/비활성화 관련 동작은 변경하지 않습니다(초기엔 우선순위 미설정, AI/ML 비활성화 상태 유지).

사용 예:
    from 05_strategy import SignalManager
    sm = SignalManager(...)

비고:
- 각 심볼 로드 중 ImportError가 발생하면 AttributeError로 변환되어 호출자에게 전달됩니다.
- 위 방식은 디버거/다중 환경에서 반복되는 "No module named 'utils.helpers'" 노이즈를 제거하는 데 도움이 됩니다.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Dict, Tuple, List

__all__ = [
    # Core
    "SignalManager", "BaseStrategy", "StrategyRegistry",
    # Strategies
    "VolatilityBreakoutStrategy", "VariousIndicatorStrategy",
    "MeanReversionStrategy", "TrendFollowingStrategy", "DCAStrategy",
    # Backtest
    "Backtester", "PerformanceMetrics", "ReportGenerator",
    # Widgets (선택)
    "StrategyManagerWidget", "BacktestRunnerWidget",
    "ParameterOptimizerWidget", "SignalMonitorWidget",
    # Risk
    "PositionSizer", "StopLoss", "Portfolio",
]

# 모듈 내부 로거 (패키지 로딩 초기에만 사용)
_log = logging.getLogger(__name__)

# 심볼 -> (모듈 경로(패키지 내부 상대 경로), attr name)
# 모듈 경로는 package-relative로 importlib.import_module(".<module>", package=__name__) 방식으로 로드됩니다.
_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    # core
    "SignalManager": ("core.signal_manager", "SignalManager"),
    "BaseStrategy": ("core.base_strategy", "BaseStrategy"),
    "StrategyRegistry": ("core.strategy_registry", "StrategyRegistry"),
    # strategies
    "VolatilityBreakoutStrategy": ("strategies.volatility_breakout", "VolatilityBreakoutStrategy"),
    "VariousIndicatorStrategy": ("strategies.various_indicator", "VariousIndicatorStrategy"),
    "MeanReversionStrategy": ("strategies.mean_reversion", "MeanReversionStrategy"),
    "TrendFollowingStrategy": ("strategies.trend_following", "TrendFollowingStrategy"),
    "DCAStrategy": ("strategies.dca_strategy", "DCAStrategy"),
    # backtest
    "Backtester": ("backtest", "Backtester"),
    "PerformanceMetrics": ("backtest", "PerformanceMetrics"),
    "ReportGenerator": ("backtest", "ReportGenerator"),
    # widgets (optional)
    "StrategyManagerWidget": ("widgets.strategy_manager", "StrategyManagerWidget"),
    "BacktestRunnerWidget": ("widgets.backtest_runner", "BacktestRunnerWidget"),
    "ParameterOptimizerWidget": ("widgets.parameter_optimizer", "ParameterOptimizerWidget"),
    "SignalMonitorWidget": ("widgets.signal_monitor", "SignalMonitorWidget"),
    # risk
    "PositionSizer": ("risk.position_sizer", "PositionSizer"),
    "StopLoss": ("risk.stop_loss", "StopLoss"),
    "Portfolio": ("risk.portfolio", "Portfolio"),
}

# 캐시: 한 번 로드한 심볼은 전역 네임스페이스에 직접 저장함으로써 후속 접근을 빠르게 합니다.
# (문서화: lazy import 시 로드된 심볼은 모듈 전역으로 고정됩니다.)
_loaded: Dict[str, Any] = {}

# widgets 가 사용 가능한지 여부(지연 로딩 시 결정)
_widgets_available = None  # None = 미확인, True/False = 확인 결과


def _import_symbol(name: str):
    """
    이름(name)에 해당하는 심볼을 지연 로딩하여 반환합니다.
    실패하면 AttributeError를 발생시킵니다.
    """
    if name in _loaded:
        return _loaded[name]

    meta = _EXPORT_MAP.get(name)
    if meta is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_rel, attr = meta
    try:
        # package-relative import: 예) ".core.signal_manager", package=__name__
        mod = importlib.import_module(f".{module_rel}", package=__name__)
    except Exception as exc:
        # 상세 로그는 debug 레벨로 남겨 노이즈를 줄입니다.
        _log.debug("lazy import failed for %s: import .%s (package=%s): %s", name, module_rel, __name__, exc, exc_info=False)
        raise AttributeError(f"failed to import module for {name}: {exc}") from exc

    try:
        value = getattr(mod, attr)
    except AttributeError as exc:
        _log.debug("lazy import: attribute %s not found in module %s: %s", attr, mod.__name__, exc, exc_info=False)
        raise AttributeError(f"module {mod.__name__!r} has no attribute {attr!r}") from exc

    # 캐시 및 모듈 전역에 바인딩 (다음 접근 시 모듈 속성으로 바로 사용 가능)
    globals()[name] = value
    _loaded[name] = value
    return value


def __getattr__(name: str):
    """
    PEP 562: 모듈 레벨 __getattr__으로 지연 로딩 구현.
    from 05_strategy import SignalManager 와 같은 사용에서 호출됩니다.
    """
    # 빠른 경로: 이미 로드된 심볼이면 반환
    if name in _loaded:
        return _loaded[name]

    # widgets availability 체크는 widgets에서 처음 접근할 때 결정
    global _widgets_available
    if name in (
        "StrategyManagerWidget",
        "BacktestRunnerWidget",
        "ParameterOptimizerWidget",
        "SignalMonitorWidget",
    ):
        # 지연 로딩 시 위젯 모듈이 없는 경우 ImportError -> AttributeError로 전달
        try:
            val = _import_symbol(name)
            _widgets_available = True
            return val
        except AttributeError:
            _widgets_available = False
            raise

    # 일반 심볼 처리
    try:
        return _import_symbol(name)
    except AttributeError:
        raise


def __dir__():
    """
    사용자 경험 개선을 위해 dir(05_strategy)에서 제공되는 심볼 목록을 보여줍니다.
    이미 로드된 심볼을 포함합니다.
    """
    base = set(__all__)
    base.update(name for name in _loaded.keys())
    return sorted(base)