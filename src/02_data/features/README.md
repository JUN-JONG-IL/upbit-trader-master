# features — AI/ML Feature Store

## Purpose
Feature engineering and storage for AI/ML models used in the Upbit trading system.
Transforms raw market data (candles, indicators) into normalized feature vectors
for strategy models.

## Responsibilities
- Feature extraction from raw candle data (`feature_engineer.py`)
- Feature storage, versioning, and retrieval (`feature_store.py`)
- Feature normalization and scaling (`normalizer.py`)

## Directory Structure

```
features/
├── feature_engineer.py  # Extract features from candle/market data
├── feature_store.py     # Store, retrieve, and version feature sets
└── normalizer.py        # Normalize / scale feature vectors
```

## Dependencies
- `pandas`, `numpy` — numerical processing
- `scikit-learn` (optional) — scaling utilities

## Usage Example

```python
from features import FeatureStore, FeatureEngineer, Normalizer

# Extract features from raw candle DataFrame
engineer = FeatureEngineer()
features = engineer.extract(candle_df)

# Normalize features before model inference
normalizer = Normalizer()
features_scaled = normalizer.fit_transform(features)

# Store and retrieve feature sets
store = FeatureStore()
store.save("KRW-BTC_1m", features_scaled)
loaded = store.load("KRW-BTC_1m")
```

## References
- 1_단계_기관에이전트급_최신_트레이딩_시스템_가이드.md §7 Feature Engineering
