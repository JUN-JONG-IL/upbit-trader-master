#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Transformer 예측기
Attention 기반 시계열 예측 모델
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
    logging.warning("PyTorch not available.")

logger = logging.getLogger(__name__)


class TransformerPredictor(nn.Module if TORCH_AVAILABLE else object):
    """
    Transformer 기반 가격 예측기
    
    Self-attention 메커니즘을 활용한 시계열 예측
    """
    
    def __init__(self,
                 input_size: int = 50,
                 d_model: int = 128,
                 nhead: int = 8,
                 num_layers: int = 3,
                 dim_feedforward: int = 512,
                 dropout: float = 0.1):
        """
        Args:
            input_size: 입력 특징 수
            d_model: 모델 차원
            nhead: Attention 헤드 수
            num_layers: Transformer 레이어 수
            dim_feedforward: Feedforward 차원
            dropout: Dropout 비율
        """
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch 미설치. Mock Transformer 사용.")
            return
        
        super().__init__()
        
        self.d_model = d_model
        
        # 입력 임베딩
        self.input_embedding = nn.Linear(input_size, d_model)
        
        # Positional Encoding
        self.pos_encoder = self._generate_positional_encoding(100, d_model)
        
        # Transformer Encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True
        )
        
        self.transformer_encoder = nn.TransformerEncoder(
            encoder_layer,
            num_layers=num_layers
        )
        
        # 출력 레이어
        self.fc_out = nn.Sequential(
            nn.Linear(d_model, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 1)
        )
        
        logger.info(f"Transformer 모델 초기화: d_model={d_model}, heads={nhead}, layers={num_layers}")
    
    def _generate_positional_encoding(self, max_len: int, d_model: int) -> 'torch.Tensor':
        """Positional Encoding 생성"""
        if not TORCH_AVAILABLE:
            return None
        
        position = torch.arange(max_len).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2) * (-np.log(10000.0) / d_model))
        
        pe = torch.zeros(max_len, d_model)
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        
        return pe.unsqueeze(0)  # (1, max_len, d_model)
    
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
        
        # 입력 임베딩
        x = self.input_embedding(x)  # (batch, seq, d_model)
        
        # Positional Encoding 추가
        seq_len = x.size(1)
        x = x + self.pos_encoder[:, :seq_len, :].to(x.device)
        
        # Transformer Encoder
        transformer_out = self.transformer_encoder(x)
        
        # 마지막 시퀀스 출력 사용
        last_out = transformer_out[:, -1, :]
        
        # 최종 예측
        output = self.fc_out(last_out)
        
        return output
    
    def predict(self, x: np.ndarray) -> float:
        """예측"""
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
