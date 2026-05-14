#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FinBERT 기반 감성 분석기
금융 뉴스 및 소셜 미디어 감성 분석
"""

import logging
from typing import Dict, List

try:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logging.warning("Transformers not available.")

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """
    FinBERT 기반 감성 분석기
    
    금융 텍스트의 감성 (긍정/부정/중립) 분석
    """
    
    def __init__(self, model_name: str = "ProsusAI/finbert"):
        """
        Args:
            model_name: HuggingFace 모델 이름
        """
        self.model_name = model_name
        
        if TRANSFORMERS_AVAILABLE:
            try:
                logger.info(f"FinBERT 모델 로딩: {model_name}")
                self.tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
                self.model.eval()
                logger.info("FinBERT 모델 로드 완료")
            except Exception as e:
                logger.error(f"FinBERT 로드 실패: {e}. Mock 모드 사용.")
                self.tokenizer = None
                self.model = None
        else:
            logger.warning("Transformers 미설치. Mock 감성 분석기 사용.")
            self.tokenizer = None
            self.model = None
    
    def analyze(self, text: str) -> Dict[str, float]:
        """
        텍스트 감성 분석
        
        Args:
            text: 분석할 텍스트
        
        Returns:
            Dict[str, float]: {
                "positive": float,
                "negative": float,
                "neutral": float,
                "sentiment_score": float (-1 ~ +1)
            }
        """
        if not TRANSFORMERS_AVAILABLE or self.model is None:
            # Mock 구현
            import random
            pos = random.uniform(0.2, 0.5)
            neg = random.uniform(0.1, 0.3)
            neu = 1.0 - pos - neg
            
            return {
                "positive": pos,
                "negative": neg,
                "neutral": neu,
                "sentiment_score": pos - neg
            }
        
        try:
            # 토크나이징
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                max_length=512,
                truncation=True,
                padding=True
            )
            
            # 추론
            with torch.no_grad():
                outputs = self.model(**inputs)
                probs = torch.softmax(outputs.logits, dim=1)[0]
            
            # 결과 파싱 (FinBERT는 보통 [positive, negative, neutral] 순서)
            positive = float(probs[0].item())
            negative = float(probs[1].item())
            neutral = float(probs[2].item())
            
            # 감성 점수 계산 (-1 ~ +1)
            sentiment_score = positive - negative
            
            return {
                "positive": positive,
                "negative": negative,
                "neutral": neutral,
                "sentiment_score": sentiment_score
            }
            
        except Exception as e:
            logger.error(f"감성 분석 실패: {e}")
            return {
                "positive": 0.33,
                "negative": 0.33,
                "neutral": 0.34,
                "sentiment_score": 0.0
            }
    
    def analyze_batch(self, texts: List[str]) -> List[Dict[str, float]]:
        """
        배치 감성 분석
        
        Args:
            texts: 텍스트 리스트
        
        Returns:
            List[Dict]: 감성 분석 결과 리스트
        """
        results = []
        for text in texts:
            result = self.analyze(text)
            results.append(result)
        return results
    
    def get_aggregate_sentiment(self, texts: List[str]) -> Dict[str, float]:
        """
        여러 텍스트의 종합 감성
        
        Args:
            texts: 텍스트 리스트
        
        Returns:
            Dict[str, float]: 평균 감성
        """
        if not texts:
            return {
                "positive": 0.0,
                "negative": 0.0,
                "neutral": 0.0,
                "sentiment_score": 0.0
            }
        
        results = self.analyze_batch(texts)
        
        avg_positive = sum(r["positive"] for r in results) / len(results)
        avg_negative = sum(r["negative"] for r in results) / len(results)
        avg_neutral = sum(r["neutral"] for r in results) / len(results)
        avg_score = sum(r["sentiment_score"] for r in results) / len(results)
        
        return {
            "positive": avg_positive,
            "negative": avg_negative,
            "neutral": avg_neutral,
            "sentiment_score": avg_score
        }
