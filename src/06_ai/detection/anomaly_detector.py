#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
이상 거래 탐지
- Autoencoder 기반
- 펌프앤덤프, 워시 트레이딩 감지

[Author] Copilot
[Created] 2026-02-06
"""

import logging
import numpy as np
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class Autoencoder:
    """
    Autoencoder 모델 (간단한 구현)
    
    정상 데이터 패턴 학습 및 이상 탐지
    """
    
    def __init__(self, input_dim: int, encoding_dim: int = 32):
        """
        초기화
        
        Args:
            input_dim: 입력 차원
            encoding_dim: 인코딩 차원
        """
        self.input_dim = input_dim
        self.encoding_dim = encoding_dim
        
        # 가중치 초기화 (간단한 선형 변환)
        self.encoder_weights = np.random.randn(input_dim, encoding_dim) * 0.1
        self.decoder_weights = np.random.randn(encoding_dim, input_dim) * 0.1
        
        logger.info(f"[Autoencoder] Initialized with input_dim={input_dim}, encoding_dim={encoding_dim}")
    
    def encode(self, x: np.ndarray) -> np.ndarray:
        """
        인코딩
        
        Args:
            x: 입력 데이터 (N x input_dim)
            
        Returns:
            인코딩된 데이터 (N x encoding_dim)
        """
        return np.tanh(x @ self.encoder_weights)
    
    def decode(self, encoded: np.ndarray) -> np.ndarray:
        """
        디코딩
        
        Args:
            encoded: 인코딩된 데이터
            
        Returns:
            재구성된 데이터
        """
        return encoded @ self.decoder_weights
    
    def forward(self, x: np.ndarray) -> np.ndarray:
        """
        순전파
        
        Args:
            x: 입력 데이터
            
        Returns:
            재구성된 데이터
        """
        encoded = self.encode(x)
        decoded = self.decode(encoded)
        return decoded
    
    def train(
        self,
        x_train: np.ndarray,
        epochs: int = 100,
        learning_rate: float = 0.01
    ) -> List[float]:
        """
        학습 (간단한 경사하강법)
        
        Args:
            x_train: 학습 데이터
            epochs: 에폭 수
            learning_rate: 학습률
            
        Returns:
            에폭별 손실 리스트
        """
        losses = []
        
        for epoch in range(epochs):
            # 순전파
            reconstructed = self.forward(x_train)
            
            # MSE 손실 계산
            loss = np.mean((x_train - reconstructed) ** 2)
            losses.append(float(loss))
            
            # 역전파 (간단한 그래디언트 계산)
            error = reconstructed - x_train
            
            # 가중치 업데이트
            encoded = self.encode(x_train)
            self.decoder_weights -= learning_rate * (encoded.T @ error) / len(x_train)
            
            decoder_grad = error @ self.decoder_weights.T
            decoder_grad *= (1 - encoded ** 2)  # tanh 미분
            self.encoder_weights -= learning_rate * (x_train.T @ decoder_grad) / len(x_train)
            
            if (epoch + 1) % 10 == 0:
                logger.debug(f"[Autoencoder] Epoch {epoch + 1}/{epochs}, Loss: {loss:.6f}")
        
        logger.info(f"[Autoencoder] Training complete. Final loss: {losses[-1]:.6f}")
        return losses
    
    def reconstruction_error(self, x: np.ndarray) -> np.ndarray:
        """
        재구성 오류 계산
        
        Args:
            x: 입력 데이터
            
        Returns:
            샘플별 MSE
        """
        reconstructed = self.forward(x)
        errors = np.mean((x - reconstructed) ** 2, axis=1)
        return errors


class AnomalyDetector:
    """
    이상 거래 탐지기
    
    Autoencoder를 사용한 비정상 거래 패턴 감지
    """
    
    def __init__(self, input_dim: int = 50):
        """
        초기화
        
        Args:
            input_dim: 입력 특징 차원
        """
        self.input_dim = input_dim
        self.model = Autoencoder(input_dim=input_dim, encoding_dim=min(32, input_dim // 2))
        self.threshold = None
        self.is_trained = False
        
        logger.info(f"[AnomalyDetector] Initialized with input_dim={input_dim}")
    
    def train(
        self,
        normal_data: np.ndarray,
        epochs: int = 100,
        contamination: float = 0.1
    ):
        """
        정상 데이터로 학습
        
        Args:
            normal_data: 정상 거래 데이터 (N x input_dim)
            epochs: 학습 에폭 수
            contamination: 이상치 비율 (임계값 설정용)
        """
        logger.info(f"[AnomalyDetector] Training on {len(normal_data)} normal samples")
        
        # Autoencoder 학습
        losses = self.model.train(normal_data, epochs=epochs)
        
        # 임계값 설정 (정상 데이터의 상위 contamination 백분위수)
        errors = self.model.reconstruction_error(normal_data)
        self.threshold = np.percentile(errors, 100 * (1 - contamination))
        
        self.is_trained = True
        logger.info(f"[AnomalyDetector] Training complete. Threshold: {self.threshold:.6f}")
    
    def detect(self, data: np.ndarray) -> Dict[str, Any]:
        """
        이상 거래 탐지
        
        Args:
            data: 거래 데이터 (1 x input_dim 또는 N x input_dim)
            
        Returns:
            탐지 결과
        """
        if not self.is_trained:
            logger.warning("[AnomalyDetector] Model not trained")
            return {
                "is_anomaly": False,
                "score": 0.0,
                "type": "unknown",
                "error": "Model not trained"
            }
        
        # 재구성 오류 계산
        if len(data.shape) == 1:
            data = data.reshape(1, -1)
        
        errors = self.model.reconstruction_error(data)
        is_anomaly = errors[0] > self.threshold
        
        # 이상 유형 분류
        anomaly_type = self._classify_anomaly(data[0], errors[0])
        
        return {
            "is_anomaly": bool(is_anomaly),
            "score": float(errors[0]),
            "threshold": float(self.threshold),
            "type": anomaly_type,
            "severity": self._calculate_severity(errors[0])
        }
    
    def _classify_anomaly(self, data: np.ndarray, error: float) -> str:
        """
        이상 유형 분류
        
        Args:
            data: 데이터 샘플
            error: 재구성 오류
            
        Returns:
            이상 유형
        """
        if error <= self.threshold:
            return "normal"
        
        # 간단한 휴리스틱으로 이상 유형 분류
        # 실제로는 더 정교한 규칙이나 분류 모델 사용
        
        # 특징 분석 (데이터 형식에 따라 조정 필요)
        # 예: [price_change, volume_change, volatility, ...]
        
        if len(data) >= 3:
            price_change = data[0] if len(data) > 0 else 0
            volume_change = data[1] if len(data) > 1 else 0
            volatility = data[2] if len(data) > 2 else 0
            
            # 펌프앤덤프 패턴: 급격한 가격 상승 + 높은 거래량 + 높은 변동성
            if price_change > 2.0 and volume_change > 3.0 and volatility > 1.5:
                return "pump_and_dump"
            
            # 워시 트레이딩: 비정상적으로 높은 거래량 + 낮은 가격 변동
            elif volume_change > 4.0 and abs(price_change) < 0.5:
                return "wash_trading"
            
            # 스푸핑: 급격한 가격 변동 + 비정상적 패턴
            elif abs(price_change) > 3.0:
                return "spoofing"
        
        return "unknown_anomaly"
    
    def _calculate_severity(self, error: float) -> str:
        """
        이상 심각도 계산
        
        Args:
            error: 재구성 오류
            
        Returns:
            심각도 ("low", "medium", "high", "critical")
        """
        if self.threshold is None:
            return "unknown"
        
        ratio = error / self.threshold
        
        if ratio < 1.0:
            return "normal"
        elif ratio < 2.0:
            return "low"
        elif ratio < 5.0:
            return "medium"
        elif ratio < 10.0:
            return "high"
        else:
            return "critical"
    
    def batch_detect(self, data: np.ndarray) -> List[Dict[str, Any]]:
        """
        배치 이상 탐지
        
        Args:
            data: 거래 데이터 배치 (N x input_dim)
            
        Returns:
            각 샘플의 탐지 결과 리스트
        """
        results = []
        
        for sample in data:
            result = self.detect(sample.reshape(1, -1))
            results.append(result)
        
        return results
    
    def save(self, path: str):
        """모델 저장"""
        np.savez(
            path,
            encoder_weights=self.model.encoder_weights,
            decoder_weights=self.model.decoder_weights,
            threshold=self.threshold,
            input_dim=self.input_dim
        )
        logger.info(f"[AnomalyDetector] Model saved to {path}")
    
    def load(self, path: str):
        """모델 로드"""
        try:
            data = np.load(path)
            self.input_dim = int(data["input_dim"])
            self.threshold = float(data["threshold"])
            
            self.model = Autoencoder(input_dim=self.input_dim)
            self.model.encoder_weights = data["encoder_weights"]
            self.model.decoder_weights = data["decoder_weights"]
            
            self.is_trained = True
            logger.info(f"[AnomalyDetector] Model loaded from {path}")
        except Exception as e:
            logger.error(f"[AnomalyDetector] Model loading error: {e}")


if __name__ == "__main__":
    # 테스트
    logging.basicConfig(level=logging.INFO)
    
    # 정상 데이터 생성 (50개 특징)
    n_normal = 1000
    n_features = 50
    normal_data = np.random.randn(n_normal, n_features)
    
    # 이상 데이터 생성 (극단값)
    n_anomaly = 50
    anomaly_data = np.random.randn(n_anomaly, n_features) * 5 + 3
    
    # 탐지기 생성 및 학습
    detector = AnomalyDetector(input_dim=n_features)
    detector.train(normal_data, epochs=50)
    
    # 정상 데이터 테스트
    normal_result = detector.detect(normal_data[0])
    print(f"Normal data result: {normal_result}")
    
    # 이상 데이터 테스트
    anomaly_result = detector.detect(anomaly_data[0])
    print(f"Anomaly data result: {anomaly_result}")
    
    # 배치 테스트
    batch_results = detector.batch_detect(anomaly_data[:10])
    anomalies = sum(1 for r in batch_results if r["is_anomaly"])
    print(f"Detected {anomalies}/10 anomalies in batch")
