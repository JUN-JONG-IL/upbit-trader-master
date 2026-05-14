"""
Models 패키지
"""

__all__ = []

# numpy/pandas 의존 모델들은 설치된 경우에만 임포트
try:
    from .gap_predictor import GapPredictorBase, create_gap_predictor
    from .adaptive_tf import AdaptiveTimeFrame
    from .anomaly_detector import AnomalyDetectorBase, create_anomaly_detector
    from .drift_monitor import DriftMonitorBase, create_drift_monitor
    _ML_MODELS_AVAILABLE = True
    __all__ += [
        "GapPredictorBase",
        "create_gap_predictor",
        "AdaptiveTimeFrame",
        "AnomalyDetectorBase",
        "create_anomaly_detector",
        "DriftMonitorBase",
        "create_drift_monitor",
    ]
except ImportError:
    _ML_MODELS_AVAILABLE = False

# db_models는 SQLAlchemy가 설치된 환경에서만 로드
try:
    from .db_models import (
        Base,
        User,
        PrioritySettings,
        MLModelSettings,
        SymbolPriorityScores,
        MLPredictions,
    )
    _DB_MODELS_AVAILABLE = True
    __all__ += [
        "Base",
        "User",
        "PrioritySettings",
        "MLModelSettings",
        "SymbolPriorityScores",
        "MLPredictions",
    ]
except ImportError:
    _DB_MODELS_AVAILABLE = False
