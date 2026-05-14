# Anomaly Detection Module (`src/ai/detection/`)

Provides anomaly detection for cryptocurrency trading patterns.

## Components

- **`anomaly_detector.py`** (`AnomalyDetector`, `Autoencoder`): Autoencoder-based anomaly detection, pump & dump detection, wash trading detection

## Usage

```python
from src.ai.detection import AnomalyDetector

detector = AnomalyDetector()
result = detector.detect(candle_data)
```
