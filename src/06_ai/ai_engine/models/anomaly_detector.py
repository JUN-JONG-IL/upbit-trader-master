#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Autoencoder 기반 이상 탐지기
비정상 거래 패턴 및 이상 징후 탐지
"""

import logging
import numpy as np
from typing import Tuple, Optional

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)


class AnomalyDetector(nn.Module if TORCH_AVAILABLE else object):
    """
    Autoencoder 기반 이상 탐지기
    
    정상 패턴을 학습하여 비정상 거래를 탐지
    """
    
    def __init__(self, input_size: int = 50, hidden_size: int = 20):
        """
        Args:
            input_size: 입력 특징 수
            hidden_size: 잠재 공간 크기
        """
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch 미설치. Mock 이상 탐지기 사용.")
            self.threshold = 2.0
            return
        
        super().__init__()
        
        # Encoder
        self.encoder = nn.Sequential(
            nn.Linear(input_size, 32),
            nn.ReLU(),
            nn.Linear(32, hidden_size),
            nn.ReLU()
        )
        
        # Decoder
        self.decoder = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Linear(32, input_size)
        )
        
        # 이상 탐지 임계값
        self.threshold = 2.0
        
        logger.info(f"Autoencoder 이상 탐지기 초기화: input={input_size}, hidden={hidden_size}")
    
    def forward(self, x: 'torch.Tensor') -> 'torch.Tensor':
        """순전파"""
        if not TORCH_AVAILABLE:
            return None
        
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return decoded
    
    def detect_anomaly(self, x: np.ndarray) -> Tuple[bool, float]:
        """
        이상 탐지
        
        Args:
            x: 입력 데이터
        
        Returns:
            (is_anomaly, score): 이상 여부, 이상 점수
        """
        if not TORCH_AVAILABLE:
            # Mock 구현
            import random
            score = random.uniform(0.5, 3.0)
            is_anomaly = score > self.threshold
            return is_anomaly, score
        
        try:
            self.eval()
            
            x_tensor = torch.FloatTensor(x).unsqueeze(0)
            
            with torch.no_grad():
                reconstructed = self.forward(x_tensor)
                
                # 재구성 오류 계산 (MSE)
                mse = torch.mean((x_tensor - reconstructed) ** 2).item()
                
                # 이상 점수 (표준편차 단위)
                score = mse / (self.threshold / 2)
                
                # 임계값 초과 여부
                is_anomaly = score > self.threshold
            
            logger.debug(f"이상 탐지: score={score:.3f}, anomaly={is_anomaly}")
            
            return is_anomaly, score
            
        except Exception as e:
            logger.error(f"이상 탐지 실패: {e}")
            return False, 0.0
    
    def set_threshold(self, threshold: float):
        """
        임계값 설정
        
        Args:
            threshold: 이상 탐지 임계값
        """
        self.threshold = threshold
        logger.info(f"임계값 설정: {threshold}")
    
    def train_on_normal(self, normal_data: np.ndarray, 
                       epochs: int = 100,
                       learning_rate: float = 0.001):
        """
        정상 데이터로 학습
        
        Args:
            normal_data: 정상 데이터 (n_samples, features)
            epochs: 학습 에포크 수
            learning_rate: 학습률
        """
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch 미설치. 학습 불가.")
            return
        
        try:
            self.train()
            
            optimizer = torch.optim.Adam(self.parameters(), lr=learning_rate)
            criterion = nn.MSELoss()
            
            X = torch.FloatTensor(normal_data)
            
            for epoch in range(epochs):
                optimizer.zero_grad()
                
                reconstructed = self.forward(X)
                loss = criterion(reconstructed, X)
                
                loss.backward()
                optimizer.step()
                
                if (epoch + 1) % 10 == 0:
                    logger.debug(f"Epoch [{epoch+1}/{epochs}], Loss: {loss.item():.4f}")
            
            self.eval()
            logger.info(f"학습 완료: {epochs} epochs")
            
        except Exception as e:
            logger.error(f"학습 실패: {e}")


# 싱글톤 인스턴스
_detector_instance = None


def get_anomaly_detector() -> AnomalyDetector:
    """글로벌 Anomaly Detector 인스턴스 반환"""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = AnomalyDetector()
    return _detector_instance
