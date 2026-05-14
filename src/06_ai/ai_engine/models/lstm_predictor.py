#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LSTM 가격 예측기 (Attention + Monte Carlo Dropout)
시계열 가격 예측을 위한 LSTM 모델
"""

import logging
import numpy as np
from typing import Tuple, Optional, List

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logging.warning("PyTorch not available. LSTM predictor will use mock implementation.")

logger = logging.getLogger(__name__)


class LSTMPredictor(nn.Module if TORCH_AVAILABLE else object):
    """
    LSTM 예측기 (Attention 메커니즘 포함)
    
    Monte Carlo Dropout을 통한 불확실성 추정 기능 제공
    """
    
    def __init__(self, 
                 input_size: int = 50,
                 hidden_size: int = 128,
                 num_layers: int = 3,
                 dropout: float = 0.2,
                 use_attention: bool = True):
        """
        Args:
            input_size: 입력 특징 수
            hidden_size: LSTM 히든 크기
            num_layers: LSTM 레이어 수
            dropout: Dropout 비율
            use_attention: Attention 사용 여부
        """
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch 미설치. Mock LSTM 사용.")
            return
        
        super().__init__()
        
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.use_attention = use_attention
        
        # LSTM 레이어
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0
        )
        
        # Attention 레이어
        if use_attention:
            self.attention = nn.Linear(hidden_size, 1)
        
        # Fully Connected 레이어
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 1)
        )
        
        logger.info(
            f"LSTM 모델 초기화: input={input_size}, hidden={hidden_size}, "
            f"layers={num_layers}, attention={use_attention}"
        )
    
    def forward(self, x: 'torch.Tensor') -> 'torch.Tensor':
        """
        순전파
        
        Args:
            x: 입력 텐서 (batch, sequence, features)
        
        Returns:
            예측 텐서 (batch, 1)
        """
        if not TORCH_AVAILABLE:
            return None
        
        # LSTM 통과
        lstm_out, (hidden, cell) = self.lstm(x)
        
        # Attention 적용
        if self.use_attention:
            # Attention weights 계산
            attn_weights = torch.softmax(self.attention(lstm_out), dim=1)
            # Context vector 계산
            context = torch.sum(attn_weights * lstm_out, dim=1)
        else:
            # 마지막 히든 상태 사용
            context = lstm_out[:, -1, :]
        
        # FC 레이어 통과
        output = self.fc(context)
        
        return output
    
    def predict_with_uncertainty(self, 
                                 x: np.ndarray,
                                 n_samples: int = 100) -> Tuple[float, float, float]:
        """
        Monte Carlo Dropout을 이용한 불확실성 추정
        
        Args:
            x: 입력 데이터 (sequence, features)
            n_samples: Monte Carlo 샘플 수
        
        Returns:
            (mean, std, confidence): 예측 평균, 표준편차, 신뢰도
        """
        if not TORCH_AVAILABLE:
            # Mock 구현
            return 50000.0, 500.0, 0.85
        
        try:
            # Dropout 활성화 (학습 모드)
            self.train()
            
            predictions = []
            
            # 입력을 텐서로 변환
            x_tensor = torch.FloatTensor(x).unsqueeze(0)  # (1, sequence, features)
            
            # Monte Carlo 샘플링
            for _ in range(n_samples):
                with torch.no_grad():
                    pred = self.forward(x_tensor)
                    predictions.append(pred.item())
            
            # 추론 모드로 복귀
            self.eval()
            
            # 통계 계산
            mean = float(np.mean(predictions))
            std = float(np.std(predictions))
            
            # 신뢰도 계산 (변동계수의 역수)
            if abs(mean) > 1e-6:
                cv = std / abs(mean)  # Coefficient of Variation
                confidence = max(0.0, min(1.0, 1.0 - cv))
            else:
                confidence = 0.5
            
            logger.debug(
                f"예측: mean={mean:.2f}, std={std:.2f}, confidence={confidence:.3f}"
            )
            
            return mean, std, confidence
            
        except Exception as e:
            logger.error(f"불확실성 예측 실패: {e}")
            return 0.0, 0.0, 0.0
    
    def predict(self, x: np.ndarray) -> float:
        """
        단순 예측 (불확실성 없이)
        
        Args:
            x: 입력 데이터 (sequence, features)
        
        Returns:
            float: 예측값
        """
        if not TORCH_AVAILABLE:
            return 50000.0
        
        try:
            self.eval()
            
            x_tensor = torch.FloatTensor(x).unsqueeze(0)
            
            with torch.no_grad():
                output = self.forward(x_tensor)
            
            return output.item()
            
        except Exception as e:
            logger.error(f"예측 실패: {e}")
            return 0.0
    
    def save_model(self, path: str):
        """모델 저장"""
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch 미설치. 모델 저장 불가.")
            return
        
        try:
            torch.save({
                'model_state_dict': self.state_dict(),
                'input_size': self.input_size,
                'hidden_size': self.hidden_size,
                'num_layers': self.num_layers,
                'use_attention': self.use_attention
            }, path)
            logger.info(f"모델 저장: {path}")
        except Exception as e:
            logger.error(f"모델 저장 실패: {e}")
    
    @classmethod
    def load_model(cls, path: str) -> 'LSTMPredictor':
        """모델 로드"""
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch 미설치. Mock 모델 반환.")
            return cls()
        
        try:
            checkpoint = torch.load(path)
            
            model = cls(
                input_size=checkpoint['input_size'],
                hidden_size=checkpoint['hidden_size'],
                num_layers=checkpoint['num_layers'],
                use_attention=checkpoint['use_attention']
            )
            
            model.load_state_dict(checkpoint['model_state_dict'])
            model.eval()
            
            logger.info(f"모델 로드: {path}")
            return model
            
        except Exception as e:
            logger.error(f"모델 로드 실패: {e}")
            return cls()
