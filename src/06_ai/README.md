# AI/ML Trading Module (`src/06_ai/`)

Institutional-grade AI and machine learning capabilities for the Upbit Trader system.  Provides price prediction, pattern recognition, news/social sentiment analysis, and automated strategy recommendations.

---

## Architecture Overview

```
src/06_ai/
├── core/                        # Central orchestration
│   ├── engine.py                # AIEngineManager – main orchestrator
│   ├── model_registry.py        # MLflow model version management
│   └── inference.py             # Real-time inference engine (<100 ms)
├── prediction/                  # Price & anomaly prediction
│   ├── price_predictor.py       # LSTM / BiLSTM / Transformer / XGBoost
│   ├── pattern_detector.py      # Candlestick & chart pattern recognition
│   └── anomaly_detector.py      # Autoencoder anomaly detection
├── sentiment/                   # Sentiment analysis
│   ├── news_analyzer.py         # Financial news sentiment (FinBERT)
│   └── social_analyzer.py       # Twitter / Reddit sentiment
├── strategy/                    # Strategy recommendation
│   ├── recommender.py           # Market-regime-aware strategy ranking
│   └── optimizer.py             # Optuna hyperparameter optimisation
├── utils/                       # Shared utilities
│   ├── feature_engineering.py   # Technical indicators, sequences
│   └── preprocessing.py         # Scaling, splitting, cleaning
├── ai_engine/                   # LLM assistant & monitoring
│   └── ml_service.py            # MLService – Gap/Anomaly ML model selector (moved from priority/)
├── detection/                   # Pump & dump anomaly detection
├── models/                      # Base predictors (LSTM, Transformer, XGB)
├── prediction/                  # Prediction UI & ensemble logic
├── priority/                    # Priority scoring & settings (AI/ML 분리 후)
│   ├── services/
│   │   ├── priority_service.py      # 우선순위 점수 계산 (제자리)
│   │   ├── priority_db_service.py   # 우선순위 DB CRUD (제자리)
│   │   ├── ml_service.py            # [SHIM] → ai_engine/ml_service.py
│   │   └── upbit_data_provider.py   # [SHIM] → src/data_01/clients/
│   └── ui/
│       ├── priority_settings.ui     # 우선순위 설정 UI (제자리)
│       ├── priority_dashboard.ui    # 우선순위 대시보드 UI (제자리)
│       └── ml_model_selector.ui     # [MOVED] → ui/ai_engine/ml_model_selector.ui
├── ui/
│   └── ai_engine/
│       └── ml_model_selector.ui     # ML 모델 선택 UI (priority/ui/ 에서 이동)
├── rl/                          # Reinforcement learning (PPO, DQN)
└── README.md                    # This file
```

---

## Key Components

### `core/engine.py` – AIEngineManager

Main entry point for all AI signals.  Coordinates prediction, sentiment, and pattern-recognition models with Redis caching and MongoDB persistence.

```python
from src._06_ai.core import AIEngineManager

engine = AIEngineManager(
    redis_uri="redis://localhost:6379",
    mongo_uri="mongodb://localhost:27017",
)
await engine.start()

# Get price predictions (cached for 60 s)
predictions = await engine.get_predictions(["BTC/KRW", "ETH/KRW"])

# Get sentiment
sentiment = await engine.get_sentiment("BTC/KRW")

# Register a custom model
await engine.load_model("lstm", my_model)
```

### `core/model_registry.py` – ModelRegistry

MLflow-backed model versioning with in-memory fallback.

```python
from src._06_ai.core import ModelRegistry

registry = ModelRegistry("sqlite:///data/mlruns.db")
info = registry.register(
    model=my_lstm,
    name="lstm-price-predictor",
    version="1.0.0",
    model_type="pytorch",
    metrics={"mae": 0.05, "rmse": 0.08, "direction_accuracy": 62.3},
)
registry.promote("lstm-price-predictor", "1.0.0", "Production")
prod = registry.get_production_model("lstm-price-predictor")
```

### `core/inference.py` – InferenceEngine

Sub-100 ms synchronous and async prediction endpoints.

```python
from src._06_ai.core import InferenceEngine
import numpy as np

engine = InferenceEngine(device="cpu")
engine.load_model("lstm", my_model, feature_dim=20)

result = await engine.predict("lstm", np.random.randn(1, 60, 20))
# → {"prediction": 50123.4, "confidence": 0.72, "latency_ms": 8.3}

metrics = engine.get_metrics("lstm")
# → {"inference_count": 42, "latency_p95_ms": 14.2, ...}
```

---

## Price Prediction

### `prediction/price_predictor.py`

Multi-architecture price prediction with confidence intervals.

```python
from src._06_ai.prediction.price_predictor import PricePredictionModel

model = PricePredictionModel(architecture="lstm", sequence_length=60)

# Train
await model.train(X_train, y_train, X_val, y_val, epochs=50)

# Predict next 5 candles
result = await model.predict("BTC/KRW", "1h", horizon=5)
# result["predictions"]       → [50000, 50200, ...]
# result["confidence_lower"]  → [49500, ...]
# result["confidence_upper"]  → [50500, ...]

# Evaluate
metrics = await model.evaluate(X_test, y_test)
# → {"mae": 123.4, "rmse": 201.0, "direction_accuracy": 58.2}
```

Supported architectures: `"lstm"`, `"bilstm"`, `"transformer"`, `"xgboost"`.

### `prediction/pattern_detector.py`

Rule-based candlestick and chart pattern detection.

```python
from src._06_ai.prediction.pattern_detector import PatternDetector

detector = PatternDetector()
result = detector.detect(open_, high, low, close, volume)
signal = detector.get_signal(result)   # −1 … +1
```

Detected patterns: Doji, Hammer, ShootingStar, BullishEngulfing, BearishEngulfing, Breakout, VolumeSpike (+ TA-Lib patterns when available).

### `prediction/anomaly_detector.py`

Autoencoder-based market anomaly detection.

```python
from src._06_ai.prediction.anomaly_detector import AnomalyDetector

detector = AnomalyDetector(input_dim=10, threshold_sigma=3.0)
detector.train(X_normal, epochs=50)

result = detector.detect(X_new)
# result["anomalies"][0] → {"index": 0, "score": 0.012, "is_anomaly": False, "severity": "low"}
```

---

## Sentiment Analysis

### `sentiment/news_analyzer.py`

FinBERT-powered financial news sentiment with keyword fallback.

```python
from src._06_ai.sentiment import NewsSentimentAnalyzer

analyzer = NewsSentimentAnalyzer(
    rss_feeds=["https://feeds.reuters.com/reuters/businessNews"],
)
result = await analyzer.analyze("BTC/KRW")
# result["sentiment_score"]               → 0.42  (-1 … +1)
# result["aggregated_metrics"]["1h_sentiment"]  → 0.31
# result["aggregated_metrics"]["news_volume"]   → 15
```

### `sentiment/social_analyzer.py`

Twitter/Reddit sentiment with influencer weighting.

```python
from src._06_ai.sentiment import SocialSentimentAnalyzer

analyzer = SocialSentimentAnalyzer(
    twitter_bearer_token="YOUR_TOKEN",
    reddit_client_id="YOUR_ID",
    reddit_client_secret="YOUR_SECRET",
)
result = await analyzer.analyze("BTC/KRW")
# result["coordinated_activity_alert"]  → False
# result["trending_hashtags"]           → ["#Bitcoin", ...]
```

---

## Strategy Recommendation

### `strategy/recommender.py`

Market-regime-aware strategy ranking.

```python
from src._06_ai.strategy import StrategyRecommender

rec = StrategyRecommender(top_n=3)
result = rec.recommend(close, volume, symbol="BTC/KRW")

for r in result["recommendations"]:
    print(r["strategy"], r["score"], r["risk_level"])
# TrendFollowing 0.9 MEDIUM
# Momentum       0.7 MEDIUM
# Breakout       0.5 HIGH
```

### `strategy/optimizer.py`

Optuna hyperparameter search with walk-forward validation.

```python
from src._06_ai.strategy import HyperparameterOptimizer

optimizer = HyperparameterOptimizer(n_trials=100)

def objective(params):
    return backtest_sharpe(params)   # your backtest function

result = optimizer.optimize(
    objective,
    search_space={
        "fast_ma":   ("int",   5, 30),
        "slow_ma":   ("int",  20, 100),
        "stop_loss": ("float", 0.01, 0.05),
    },
)
print(result["best_params"])
```

---

## Utilities

### `utils/feature_engineering.py`

```python
from src._06_ai.utils import FeatureEngineer

fe = FeatureEngineer()
features, names = fe.build_features(open_, high, low, close, volume)
X, y = fe.create_sequences(features, targets, seq_len=60, horizon=1)
```

### `utils/preprocessing.py`

```python
from src._06_ai.utils import DataPreprocessor

prep = DataPreprocessor(scaler_type="standard")
X_train, X_val, X_test, y_train, y_val, y_test = prep.split_and_scale(features, targets)
```

---

## Performance Targets

| Component           | Latency (P95) | Accuracy Target             |
|---------------------|---------------|-----------------------------|
| Price prediction    | < 100 ms      | Directional accuracy > 55 % |
| Pattern detection   | < 200 ms      | Precision > 70 %            |
| Sentiment analysis  | < 500 ms      | Correlation > 0.6           |
| Strategy recommendation | < 1 s    | Sharpe ratio > 1.5          |

---

## Redis Pub/Sub Channels

| Channel                        | Purpose                         |
|--------------------------------|---------------------------------|
| `ai:prediction:{symbol}`       | Real-time price prediction      |
| `ai:sentiment:{symbol}`        | Aggregated sentiment score      |
| `ai:pattern:{symbol}`          | Detected chart patterns         |
| `ai:strategy:{symbol}`         | Strategy recommendations        |

---

## MongoDB Collections

| Collection        | Purpose                                  |
|-------------------|------------------------------------------|
| `ai_predictions`  | Historical prediction records (TimescaleDB-compatible) |
| `ai_sentiment`    | Sentiment history per symbol             |
| `ai_patterns`     | Detected pattern history                 |
| `ai_model_meta`   | Model metadata and performance tracking  |

---

## Dependencies

Key AI/ML packages (see `requirements.txt`):

```
torch>=2.0.0          # Deep learning
transformers>=4.30.0  # HuggingFace NLP
scikit-learn>=1.3.0   # Traditional ML
xgboost>=2.0.0        # Gradient boosting
lightgbm>=4.0.0       # Fast gradient boosting
optuna>=3.4.0         # Hyperparameter optimisation
mlflow>=2.8.0         # Model tracking
pandas-ta>=0.3.14     # Technical indicators
prophet>=1.1.0        # Time series forecasting
```

---

## Deployment

### Docker Compose

```bash
# Start all services including AI engine and MLflow
docker compose -f docker-compose.yml up -d

# AI engine only
docker compose up ai-engine
```

See `docker-compose.yml` for the `ai-engine` and `mlflow` service definitions.

### Environment Variables

| Variable                  | Default                          | Description               |
|---------------------------|----------------------------------|---------------------------|
| `MONGODB_URI`             | `mongodb://localhost:27017`      | MongoDB connection URI    |
| `REDIS_URI`               | `redis://localhost:6379`         | Redis connection URI      |
| `MLFLOW_TRACKING_URI`     | `http://localhost:5000`          | MLflow tracking URI       |
| `AI_PREDICTION_THRESHOLD` | `0.55`                           | Minimum signal confidence |
| `OPENAI_API_KEY`          | –                                | GPT-4o API key            |
| `GOOGLE_API_KEY`          | –                                | Gemini API key            |

---

## Monitoring

Prometheus metrics are registered automatically:

- `ai_prediction_latency_seconds` (histogram, by model_type)
- `ai_prediction_accuracy` (gauge, by symbol/timeframe)
- `ai_sentiment_latency_seconds` (histogram)
- `ai_sentiment_score` (gauge, by symbol)
- `ai_training_duration_seconds` (histogram, by model_type)

---

## Model Lifecycle

```
Data Collection → Feature Engineering → Training (Optuna HPO)
    → MLflow Registration → Staging Validation → Production Promotion
    → Real-time Inference → Drift Detection → Auto-Retraining
```

Drift detection is handled by `ai_engine/engine/drift_detector.py`.
Auto-retraining is scheduled via `ai_engine/training/automation/auto_retraining.py`.
