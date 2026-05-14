"""
[Purpose]
- AI 모델 학습 파이프라인 모듈

[Responsibilities]
- 모델 학습 자동화 및 하이퍼파라미터 최적화
- 학습 이력 관리 및 MLflow 통합

[통합 내역]
- 05_ml.mlflow_feast_pipeline → training.mlflow_feast_pipeline
- 08_ml_ai.models.mlops       → training.mlops

[Usage]
    from src._06_ai.training import MLOps, MLflowFeastPipeline
"""

try:
    from .mlops import MLOpsManager  # noqa: F401
except Exception:
    pass

try:
    from .mlflow_feast_pipeline import MLflowFeastPipeline  # noqa: F401
except Exception:
    pass

__all__ = ["MLOpsManager", "MLflowFeastPipeline"]
