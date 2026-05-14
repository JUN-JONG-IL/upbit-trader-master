"""
Anomaly Detection Module

[통합 내역]
- 05_ml.vae_anomaly            → detection.vae_anomaly
- 08_ml_ai.models.autoencoder_anomaly → detection.autoencoder_anomaly
- 08_ml_ai.models.drift_detector      → detection.drift_detector

[Components]
- anomaly_detector   : Autoencoder-based anomaly detection
- vae_anomaly        : VAE-based anomaly detection (from 05_ml)
- autoencoder_anomaly: Advanced autoencoder anomaly detection (from 08_ml_ai)
- drift_detector     : Data drift detection (from 08_ml_ai)
"""

from .anomaly_detector import AnomalyDetector, Autoencoder

try:
    from .vae_anomaly import VAEAnomalyDetector  # noqa: F401
except Exception:
    pass

try:
    from .drift_detector import DriftMonitor  # noqa: F401
except Exception:
    pass

__all__ = ['AnomalyDetector', 'Autoencoder', 'VAEAnomalyDetector', 'DriftMonitor']
