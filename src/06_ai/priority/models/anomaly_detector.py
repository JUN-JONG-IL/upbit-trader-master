#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
이상치 감지 모델 모듈

Isolation Forest, One-Class SVM, Autoencoder 기반 이상치 감지 모델을 제공합니다.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class AnomalyDetectorBase:
    """이상치 감지 기본 클래스"""

    def __init__(self, threshold: float = 0.95) -> None:
        if not (0 < threshold <= 1):
            raise ValueError("threshold는 (0, 1] 범위여야 합니다.")
        self.threshold = threshold
        self.model: Any = None
        self.scaler: Any = None
        self.is_fitted: bool = False

    def fit(self, X: np.ndarray) -> None:
        raise NotImplementedError

    def predict(self, X: np.ndarray) -> np.ndarray:
        """이상치 여부를 반환합니다. -1: 이상치, 1: 정상"""
        raise NotImplementedError

    def is_anomaly(self, X: np.ndarray) -> bool:
        """단일 샘플이 이상치인지 반환합니다."""
        result = self.predict(np.atleast_2d(X))
        return int(result[0]) == -1

    def _scale(self, X: np.ndarray, fit: bool = False) -> np.ndarray:
        from sklearn.preprocessing import StandardScaler  # type: ignore
        if self.scaler is None:
            self.scaler = StandardScaler()
        if fit:
            return self.scaler.fit_transform(X)
        return self.scaler.transform(X)


class IsolationForestDetector(AnomalyDetectorBase):
    """Isolation Forest 기반 이상치 감지 (빠르고 효율적, 추천)"""

    def __init__(self, threshold: float = 0.95, n_estimators: int = 100) -> None:
        super().__init__(threshold)
        try:
            from sklearn.ensemble import IsolationForest  # type: ignore
            self.model = IsolationForest(
                contamination=1.0 - threshold,
                n_estimators=n_estimators,
                random_state=42,
            )
        except ImportError:
            logger.error("scikit-learn 패키지가 설치되지 않았습니다.")
            raise

    def fit(self, X: np.ndarray) -> None:
        X = self._scale(np.asarray(X, dtype=float), fit=True)
        self.model.fit(X)
        self.is_fitted = True
        logger.info("IsolationForest 학습 완료")

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("모델이 학습되지 않았습니다.")
        X = self._scale(np.asarray(X, dtype=float), fit=False)
        return self.model.predict(X)


class OneClassSVMDetector(AnomalyDetectorBase):
    """One-Class SVM 기반 이상치 감지"""

    def __init__(self, threshold: float = 0.95) -> None:
        super().__init__(threshold)
        try:
            from sklearn.svm import OneClassSVM  # type: ignore
            self.model = OneClassSVM(
                nu=1.0 - threshold,
                kernel="rbf",
            )
        except ImportError:
            logger.error("scikit-learn 패키지가 설치되지 않았습니다.")
            raise

    def fit(self, X: np.ndarray) -> None:
        X = self._scale(np.asarray(X, dtype=float), fit=True)
        self.model.fit(X)
        self.is_fitted = True
        logger.info("OneClassSVM 학습 완료")

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("모델이 학습되지 않았습니다.")
        X = self._scale(np.asarray(X, dtype=float), fit=False)
        return self.model.predict(X)


class AutoencoderDetector(AnomalyDetectorBase):
    """딥러닝(Autoencoder) 기반 이상치 감지"""

    def __init__(self, threshold: float = 0.95, input_dim: int = 10) -> None:
        super().__init__(threshold)
        self.input_dim = input_dim
        self._recon_threshold: Optional[float] = None
        self._build_model()

    def _build_model(self) -> None:
        """PyTorch Autoencoder 모델 빌드"""
        try:
            import torch
            import torch.nn as nn

            class _Autoencoder(nn.Module):
                def __init__(self, dim: int) -> None:
                    super().__init__()
                    self.encoder = nn.Sequential(
                        nn.Linear(dim, max(4, dim // 2)),
                        nn.ReLU(),
                        nn.Linear(max(4, dim // 2), max(2, dim // 4)),
                        nn.ReLU(),
                    )
                    self.decoder = nn.Sequential(
                        nn.Linear(max(2, dim // 4), max(4, dim // 2)),
                        nn.ReLU(),
                        nn.Linear(max(4, dim // 2), dim),
                    )

                def forward(self, x: "torch.Tensor") -> "torch.Tensor":
                    return self.decoder(self.encoder(x))

            self.model = _Autoencoder(self.input_dim)
            self._torch = torch
            self._nn = nn
            logger.info("Autoencoder 모델 빌드 완료 (input_dim=%d)", self.input_dim)
        except ImportError:
            logger.error("torch 패키지가 설치되지 않았습니다.")
            self.model = None

    def fit(self, X: np.ndarray, epochs: int = 50, lr: float = 1e-3) -> None:
        if self.model is None:
            raise RuntimeError("Autoencoder 모델이 초기화되지 않았습니다.")
        import torch
        import torch.nn as nn

        X = self._scale(np.asarray(X, dtype=float), fit=True)
        tensor_X = torch.FloatTensor(X)

        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        criterion = nn.MSELoss()
        self.model.train()
        for epoch in range(epochs):
            optimizer.zero_grad()
            output = self.model(tensor_X)
            loss = criterion(output, tensor_X)
            loss.backward()
            optimizer.step()
            if epoch % 10 == 0:
                logger.debug("Autoencoder Epoch %d/%d Loss: %.6f", epoch, epochs, loss.item())

        # 재구성 오류 임계값 계산
        self.model.eval()
        with torch.no_grad():
            recon = self.model(tensor_X)
            errors = ((recon - tensor_X) ** 2).mean(dim=1).numpy()
        self._recon_threshold = float(np.percentile(errors, self.threshold * 100))
        self.is_fitted = True
        logger.info("Autoencoder 학습 완료 (recon_threshold=%.6f)", self._recon_threshold)

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted or self._recon_threshold is None:
            raise RuntimeError("모델이 학습되지 않았습니다.")
        import torch

        X = self._scale(np.asarray(X, dtype=float), fit=False)
        tensor_X = torch.FloatTensor(X)
        self.model.eval()
        with torch.no_grad():
            recon = self.model(tensor_X)
            errors = ((recon - tensor_X) ** 2).mean(dim=1).numpy()
        # 이상치: -1, 정상: 1
        return np.where(errors > self._recon_threshold, -1, 1)


def create_anomaly_detector(
    model_type: str, threshold: float = 0.95, **kwargs: Any
) -> AnomalyDetectorBase:
    """팩토리 함수: 모델 타입에 맞는 이상치 감지기를 생성합니다."""
    detectors = {
        "isolation_forest": IsolationForestDetector,
        "one_class_svm": OneClassSVMDetector,
        "autoencoder": AutoencoderDetector,
    }
    cls = detectors.get(model_type)
    if cls is None:
        raise ValueError(
            f"지원하지 않는 모델 타입: {model_type}. 사용 가능: {list(detectors)}"
        )
    return cls(threshold=threshold, **kwargs)
