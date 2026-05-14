# AI Training Module (`src/ai/training/`)

AI 모델 학습 파이프라인 모듈.

## 기능

- 모델 학습 자동화 및 하이퍼파라미터 최적화
- 학습 이력 관리 및 MLflow 통합
- 자동 재학습 (Auto-retraining)

## 하위 모듈

- **`automation/`**: 자동 재학습 (`auto_retraining.py`)
- **`optimization/`**: 하이퍼파라미터 최적화 (`hyperopt.py`)
