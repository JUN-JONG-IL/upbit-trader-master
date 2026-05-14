"""
src/06_ai/detection/vae_anomaly.py

VAE (Variational Autoencoder) 기반 이상 탐지 시스템
용도: 비정상 캔들/거래 패턴 자동 탐지

의존성:
  pip install torch>=2.0.0 numpy
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn


class VAE(nn.Module):
    """
    Variational Autoencoder for Anomaly Detection

    입력을 잠재 공간(latent space)으로 압축 후 재구성하여
    재구성 오차를 이상치 점수로 활용합니다.
    """

    def __init__(self, input_dim: int, latent_dim: int = 20) -> None:
        super().__init__()

        # Encoder
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 64),
            nn.ReLU(),
        )

        self.fc_mu = nn.Linear(64, latent_dim)
        self.fc_logvar = nn.Linear(64, latent_dim)

        # Decoder
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 128),
            nn.ReLU(),
            nn.Linear(128, input_dim),
        )

    def encode(
        self, x: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """인코딩: 평균(mu)과 로그분산(logvar) 반환"""
        h = self.encoder(x)
        return self.fc_mu(h), self.fc_logvar(h)

    def reparameterize(
        self, mu: torch.Tensor, logvar: torch.Tensor
    ) -> torch.Tensor:
        """재파라미터화 트릭: z = mu + eps * std"""
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        return mu + eps * std

    def decode(self, z: torch.Tensor) -> torch.Tensor:
        """디코딩: 잠재 벡터 → 재구성 입력"""
        return self.decoder(z)

    def forward(
        self, x: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Args:
            x: (batch, input_dim) 입력 텐서

        Returns:
            (recon_x, mu, logvar)
        """
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        recon_x = self.decode(z)
        return recon_x, mu, logvar


class VAEAnomalyDetector:
    """
    VAE 기반 이상 탐지기

    정상 데이터로 VAE를 학습한 후,
    재구성 오차(MSE)를 이상치 점수로 사용합니다.

    사용 예시::

        detector = VAEAnomalyDetector(input_dim=5)
        detector.train(X_normal, epochs=100)
        anomalies, scores = detector.detect_anomalies(X_test)
    """

    def __init__(
        self,
        input_dim: int,
        latent_dim: int = 20,
        lr: float = 1e-3,
    ) -> None:
        self.model = VAE(input_dim, latent_dim)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        self.threshold: float | None = None

    # ------------------------------------------------------------------
    # 손실 함수
    # ------------------------------------------------------------------

    @staticmethod
    def _loss_function(
        recon_x: torch.Tensor,
        x: torch.Tensor,
        mu: torch.Tensor,
        logvar: torch.Tensor,
    ) -> torch.Tensor:
        """
        VAE Loss = Reconstruction Loss (MSE) + KL Divergence

        Args:
            recon_x: 재구성 입력
            x      : 원본 입력
            mu     : 잠재 공간 평균
            logvar : 잠재 공간 로그분산

        Returns:
            총 손실 스칼라
        """
        mse = nn.functional.mse_loss(recon_x, x, reduction="sum")
        kld = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp())
        return mse + kld

    # ------------------------------------------------------------------
    # 학습
    # ------------------------------------------------------------------

    def train(
        self,
        X_train: np.ndarray,
        epochs: int = 100,
        batch_size: int = 128,
    ) -> None:
        """
        정상 데이터로 VAE 학습

        Args:
            X_train   : 정상 샘플 배열 (n_samples, input_dim)
            epochs    : 학습 에포크 수
            batch_size: 미니배치 크기
        """
        self.model.train()
        n = len(X_train)

        for epoch in range(epochs):
            total_loss = 0.0
            # 미니배치 순회
            indices = np.random.permutation(n)
            for start in range(0, n, batch_size):
                batch_idx = indices[start : start + batch_size]
                batch = torch.FloatTensor(X_train[batch_idx])

                self.optimizer.zero_grad()
                recon_batch, mu, logvar = self.model(batch)
                loss = self._loss_function(recon_batch, batch, mu, logvar)
                loss.backward()
                self.optimizer.step()

                total_loss += loss.item()

            if (epoch + 1) % 10 == 0:
                print(
                    f"Epoch {epoch + 1}/{epochs}, "
                    f"Loss: {total_loss / n:.4f}"
                )

        # 학습 데이터 기준으로 임계값 설정
        self.set_threshold(X_train)

    # ------------------------------------------------------------------
    # 임계값 설정
    # ------------------------------------------------------------------

    def set_threshold(
        self, X_train: np.ndarray, percentile: int = 95
    ) -> float:
        """
        이상치 임계값 설정 (학습 데이터 재구성 오차 기반)

        Args:
            X_train   : 정상 학습 데이터
            percentile: 임계값으로 사용할 백분위수 (기본 95)

        Returns:
            설정된 임계값
        """
        self.model.eval()
        with torch.no_grad():
            X_tensor = torch.FloatTensor(X_train)
            recon_x, _, _ = self.model(X_tensor)
            errors = torch.mean((X_tensor - recon_x) ** 2, dim=1).numpy()

        self.threshold = float(np.percentile(errors, percentile))
        return self.threshold

    # ------------------------------------------------------------------
    # 탐지
    # ------------------------------------------------------------------

    def detect_anomalies(
        self, X_test: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        이상치 탐지

        Args:
            X_test: 테스트 샘플 배열 (n_samples, input_dim)

        Returns:
            (anomalies: bool 배열, errors: float 배열)
            anomalies[i] == True 이면 이상치
        """
        if self.threshold is None:
            raise RuntimeError(
                "임계값이 설정되지 않았습니다. "
                "train() 또는 set_threshold()를 먼저 호출하세요."
            )

        self.model.eval()
        with torch.no_grad():
            X_tensor = torch.FloatTensor(X_test)
            recon_x, _, _ = self.model(X_tensor)
            errors = torch.mean((X_tensor - recon_x) ** 2, dim=1).numpy()

        anomalies = errors > self.threshold
        return anomalies, errors
