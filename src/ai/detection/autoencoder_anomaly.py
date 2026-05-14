"""
AutoEncoder 기반 캔들 이상치 감지 모델

목적: OHLCV 데이터의 비정상 패턴(이상치) 자동 감지
원리: 정상 데이터로 학습 후, 복원 오차(Reconstruction Error)가
      임계값(threshold)을 초과하면 이상치로 판단

아키텍처:
  입력(5) → 인코더 → 잠재 공간(3) → 디코더 → 출력(5)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False
    logger.warning("torch 패키지가 없습니다. pip install torch 를 실행하세요.")


class CandleAutoencoder(nn.Module if _TORCH_AVAILABLE else object):
    """
    캔들 이상치 감지용 AutoEncoder

    입력: OHLCV 5차원 벡터 (정규화 필요)
    출력: 복원된 OHLCV 5차원 벡터
    """

    if _TORCH_AVAILABLE:
        def __init__(self, input_dim: int = 5, latent_dim: int = 3):
            """
            초기화

            Args:
                input_dim:  입력 차원 (기본: 5 = OHLCV)
                latent_dim: 잠재 공간 차원 (기본: 3)
            """
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Linear(input_dim, 16),
                nn.ReLU(),
                nn.Linear(16, 8),
                nn.ReLU(),
                nn.Linear(8, latent_dim),
            )
            self.decoder = nn.Sequential(
                nn.Linear(latent_dim, 8),
                nn.ReLU(),
                nn.Linear(8, 16),
                nn.ReLU(),
                nn.Linear(16, input_dim),
            )

        def forward(self, x: Any) -> Any:
            """순전파"""
            return self.decoder(self.encoder(x))


class AnomalyDetector:
    """
    AutoEncoder 기반 이상치 감지기

    Example:
        detector = AnomalyDetector(threshold=0.01)
        detector.train(normal_candles)  # shape: [N, 5] (OHLCV)

        candle = [[50000, 51000, 49500, 50500, 10.5]]
        is_anomaly, error = detector.detect(candle)
        print(f"이상치 여부: {is_anomaly}, 복원 오차: {error:.6f}")
    """

    def __init__(self, threshold: float = 0.01, input_dim: int = 5, latent_dim: int = 3):
        """
        초기화

        Args:
            threshold:  이상치 판단 복원 오차 임계값
            input_dim:  입력 차원
            latent_dim: 잠재 공간 차원
        """
        if not _TORCH_AVAILABLE:
            raise ImportError("torch 패키지를 설치하세요: pip install torch")

        self.threshold = threshold
        self.model = CandleAutoencoder(input_dim=input_dim, latent_dim=latent_dim)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
        self.criterion = nn.MSELoss()
        self._trained = False

    def train(
        self,
        data: Any,
        epochs: int = 100,
        batch_size: int = 64,
    ) -> list[float]:
        """
        정상 캔들 데이터로 모델 학습

        Args:
            data:       OHLCV 배열 (shape: [N, 5]) - 정규화 권장
            epochs:     학습 에폭 수
            batch_size: 배치 크기

        Returns:
            에폭별 손실 값 목록
        """
        tensor = torch.FloatTensor(np.array(data))
        dataset = TensorDataset(tensor)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        self.model.train()
        losses: list[float] = []

        for epoch in range(epochs):
            epoch_loss = 0.0
            for (batch,) in loader:
                reconstructed = self.model(batch)
                loss = self.criterion(reconstructed, batch)

                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()
                epoch_loss += loss.item()

            avg_loss = epoch_loss / len(loader)
            losses.append(avg_loss)
            if (epoch + 1) % 20 == 0:
                logger.info("Epoch [%d/%d] 손실: %.6f", epoch + 1, epochs, avg_loss)

        self._trained = True
        logger.info("AutoEncoder 학습 완료")
        return losses

    def detect(self, candle: Any) -> tuple[bool, float]:
        """
        단일 캔들 이상치 감지

        Args:
            candle: OHLCV 배열 (shape: [1, 5])

        Returns:
            (이상치 여부, 복원 오차)
        """
        if not self._trained:
            raise RuntimeError("먼저 train() 을 호출하세요.")

        self.model.eval()
        with torch.no_grad():
            tensor = torch.FloatTensor(np.array(candle))
            reconstructed = self.model(tensor)
            error = float(torch.mean((tensor - reconstructed) ** 2).item())

        return error > self.threshold, error

    def detect_batch(self, data: Any) -> tuple[np.ndarray, np.ndarray]:
        """
        배치 이상치 감지

        Args:
            data: OHLCV 배열 (shape: [N, 5])

        Returns:
            (이상치 마스크 bool 배열, 복원 오차 배열)
        """
        if not self._trained:
            raise RuntimeError("먼저 train() 을 호출하세요.")

        self.model.eval()
        with torch.no_grad():
            tensor = torch.FloatTensor(np.array(data))
            reconstructed = self.model(tensor)
            errors = torch.mean((tensor - reconstructed) ** 2, dim=1).numpy()

        return errors > self.threshold, errors

    def save(self, path: str) -> None:
        """모델 저장"""
        torch.save(self.model.state_dict(), path)
        logger.info("AutoEncoder 저장: %s", path)

    def load(self, path: str) -> None:
        """모델 로드"""
        self.model.load_state_dict(torch.load(path, map_location="cpu"))
        self._trained = True
        logger.info("AutoEncoder 로드: %s", path)


if __name__ == "__main__":
    try:
        import torch  # noqa: F401

        np.random.seed(42)
        # 정상 캔들 더미 데이터 (0~1 정규화)
        normal_data = np.random.uniform(0.4, 0.6, (200, 5)).astype(np.float32)

        detector = AnomalyDetector(threshold=0.01)
        detector.train(normal_data, epochs=50)

        # 정상 캔들
        normal_candle = [[0.5, 0.51, 0.49, 0.505, 0.52]]
        is_anomaly, error = detector.detect(normal_candle)
        print(f"정상 캔들 → 이상치: {is_anomaly}, 복원 오차: {error:.6f}")

        # 이상 캔들 (값 범위 벗어남)
        anomaly_candle = [[0.9, 0.95, 0.1, 0.92, 0.05]]
        is_anomaly, error = detector.detect(anomaly_candle)
        print(f"이상 캔들 → 이상치: {is_anomaly}, 복원 오차: {error:.6f}")
    except ImportError as e:
        print(f"필수 패키지 없음: {e}")
