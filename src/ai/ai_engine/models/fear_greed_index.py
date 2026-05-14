#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fear & Greed Index 계산기
시장 심리 지수 계산
"""

import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class FearGreedIndex:
    """
    Fear & Greed Index 계산기
    
    시장 변동성, 거래량, 소셜 멘션, 감성 등을 종합하여
    0~100 점수로 시장 심리를 측정
    """
    
    def __init__(self):
        """초기화"""
        # 각 지표의 가중치
        self.weights = {
            "volatility": 0.25,     # 변동성
            "volume": 0.25,         # 거래량
            "social": 0.25,         # 소셜 멘션
            "sentiment": 0.25       # 감성 점수
        }
        
        logger.info("Fear & Greed Index 계산기 초기화")
    
    def calculate(self,
                 volatility: float,
                 volume_change: float,
                 social_mentions: int,
                 sentiment_score: float) -> Dict[str, Any]:
        """
        Fear & Greed Index 계산
        
        Args:
            volatility: 변동성 (0~100)
            volume_change: 거래량 변화율 (-100 ~ +100)
            social_mentions: 소셜 멘션 수
            sentiment_score: 감성 점수 (-1 ~ +1)
        
        Returns:
            Dict: {
                "index": float,      # 0~100
                "label": str,        # "극단적 공포" ~ "극단적 탐욕"
                "breakdown": Dict    # 각 지표별 점수
            }
        """
        try:
            # 1. 변동성 정규화 (높을수록 공포)
            volatility_norm = 100 - min(100, max(0, volatility))
            
            # 2. 거래량 정규화 (증가 = 탐욕, 감소 = 공포)
            volume_norm = 50 + (volume_change / 2)
            volume_norm = min(100, max(0, volume_norm))
            
            # 3. 소셜 멘션 정규화 (많을수록 관심 = 탐욕)
            social_norm = min(100, social_mentions / 10)
            
            # 4. 감성 정규화 (-1~+1 -> 0~100)
            sentiment_norm = (sentiment_score + 1) * 50
            sentiment_norm = min(100, max(0, sentiment_norm))
            
            # 가중 평균으로 최종 인덱스 계산
            index = (
                self.weights["volatility"] * volatility_norm +
                self.weights["volume"] * volume_norm +
                self.weights["social"] * social_norm +
                self.weights["sentiment"] * sentiment_norm
            )
            
            # 라벨 결정
            if index < 20:
                label = "극단적 공포"
                color = "#8B0000"  # Dark Red
            elif index < 40:
                label = "공포"
                color = "#FF4500"  # Orange Red
            elif index < 60:
                label = "중립"
                color = "#FFD700"  # Gold
            elif index < 80:
                label = "탐욕"
                color = "#32CD32"  # Lime Green
            else:
                label = "극단적 탐욕"
                color = "#006400"  # Dark Green
            
            # 세부 내역
            breakdown = {
                "volatility": round(volatility_norm, 2),
                "volume": round(volume_norm, 2),
                "social": round(social_norm, 2),
                "sentiment": round(sentiment_norm, 2)
            }
            
            result = {
                "index": round(index, 2),
                "label": label,
                "color": color,
                "breakdown": breakdown
            }
            
            logger.debug(f"Fear & Greed Index: {index:.2f} ({label})")
            
            return result
            
        except Exception as e:
            logger.error(f"Fear & Greed Index 계산 실패: {e}")
            return {
                "index": 50.0,
                "label": "중립",
                "color": "#FFD700",
                "breakdown": {}
            }
    
    def set_weights(self, weights: Dict[str, float]):
        """
        가중치 설정
        
        Args:
            weights: {"volatility": 0.25, "volume": 0.25, ...}
        """
        total = sum(weights.values())
        if abs(total - 1.0) > 0.01:
            logger.warning(f"가중치 합계가 1이 아닙니다: {total}")
            # 정규화
            weights = {k: v/total for k, v in weights.items()}
        
        self.weights.update(weights)
        logger.info(f"가중치 업데이트: {self.weights}")
    
    def get_recommendation(self, index: float) -> str:
        """
        인덱스에 따른 투자 권장사항
        
        Args:
            index: Fear & Greed Index (0~100)
        
        Returns:
            str: 권장사항
        """
        if index < 20:
            return "극단적 공포 - 매수 기회일 수 있습니다 (역발상)"
        elif index < 40:
            return "공포 - 점진적 매수 고려"
        elif index < 60:
            return "중립 - 관망 또는 분할 매수"
        elif index < 80:
            return "탐욕 - 이익 실현 고려"
        else:
            return "극단적 탐욕 - 매도 타이밍 근접 (위험 증가)"


# 싱글톤 인스턴스
_index_instance = None


def get_fear_greed_index() -> FearGreedIndex:
    """글로벌 Fear & Greed Index 인스턴스 반환"""
    global _index_instance
    if _index_instance is None:
        _index_instance = FearGreedIndex()
    return _index_instance
