#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Multilingual Sentiment Analysis Module

다중 언어 감성 분석을 제공합니다.
- KoBERT (한국어)
- FinBERT (영어 금융)
- mBERT (다국어)
"""

import logging
from typing import Dict, List, Optional
import numpy as np

logger = logging.getLogger(__name__)


class MultilingualSentimentAnalyzer:
    """
    다중 언어 감성 분석기
    """
    
    def __init__(self):
        """Initialize Multilingual Sentiment Analyzer"""
        self.korean_model = None
        self.financial_model = None
        self.multilingual_model = None
        
        logger.info("Multilingual Sentiment Analyzer initialized")
    
    def _load_korean_model(self):
        """KoBERT 모델 로드"""
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            
            model_name = "beomi/kcbert-base"  # Alternative: monologg/kobert
            self.korean_tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.korean_model = AutoModelForSequenceClassification.from_pretrained(model_name)
            
            logger.info("Korean sentiment model (KoBERT) loaded")
            
        except ImportError:
            logger.error("transformers library not installed")
        except Exception as e:
            logger.error(f"Failed to load Korean model: {e}")
    
    def _load_financial_model(self):
        """FinBERT 모델 로드"""
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            
            model_name = "ProsusAI/finbert"
            self.financial_tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.financial_model = AutoModelForSequenceClassification.from_pretrained(model_name)
            
            logger.info("Financial sentiment model (FinBERT) loaded")
            
        except Exception as e:
            logger.error(f"Failed to load FinBERT model: {e}")
    
    def _load_multilingual_model(self):
        """다국어 BERT 모델 로드"""
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            
            model_name = "nlptown/bert-base-multilingual-uncased-sentiment"
            self.multilingual_tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.multilingual_model = AutoModelForSequenceClassification.from_pretrained(model_name)
            
            logger.info("Multilingual sentiment model loaded")
            
        except Exception as e:
            logger.error(f"Failed to load multilingual model: {e}")
    
    def analyze_korean(self, text: str) -> Dict:
        """
        한국어 감성 분석
        
        Args:
            text: 한국어 텍스트
        
        Returns:
            감성 분석 결과
        """
        try:
            if self.korean_model is None:
                self._load_korean_model()
            
            if self.korean_model is None:
                return self._fallback_sentiment(text)
            
            import torch
            
            # Tokenize
            inputs = self.korean_tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True
            )
            
            # Get prediction
            with torch.no_grad():
                outputs = self.korean_model(**inputs)
                logits = outputs.logits
                probabilities = torch.softmax(logits, dim=-1)
            
            # Convert to sentiment score (-1 to 1)
            # Assuming binary classification: 0=negative, 1=positive
            probs = probabilities[0].numpy()
            
            if len(probs) == 2:
                # Binary: negative, positive
                sentiment_score = float(probs[1] - probs[0])
                label = "긍정" if sentiment_score > 0 else "부정"
            else:
                # Multi-class: map to sentiment score
                sentiment_score = float(np.dot(probs, np.arange(len(probs)) - len(probs)//2))
                sentiment_score = sentiment_score / (len(probs) // 2)  # Normalize to [-1, 1]
                
                if sentiment_score > 0.3:
                    label = "긍정"
                elif sentiment_score < -0.3:
                    label = "부정"
                else:
                    label = "중립"
            
            result = {
                'score': sentiment_score,
                'label': label,
                'confidence': float(np.max(probs)),
                'probabilities': probs.tolist(),
                'language': 'korean'
            }
            
            logger.info(f"Korean sentiment: {label} (score: {sentiment_score:.3f})")
            
            return result
            
        except Exception as e:
            logger.error(f"Korean sentiment analysis failed: {e}")
            return self._fallback_sentiment(text)
    
    def analyze_financial_english(self, text: str) -> Dict:
        """
        영어 금융 텍스트 감성 분석
        
        Args:
            text: 영어 금융 텍스트
        
        Returns:
            감성 분석 결과
        """
        try:
            if self.financial_model is None:
                self._load_financial_model()
            
            if self.financial_model is None:
                return self._fallback_sentiment(text)
            
            import torch
            
            # Tokenize
            inputs = self.financial_tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True
            )
            
            # Get prediction
            with torch.no_grad():
                outputs = self.financial_model(**inputs)
                logits = outputs.logits
                probabilities = torch.softmax(logits, dim=-1)
            
            probs = probabilities[0].numpy()
            
            # FinBERT typically has 3 classes: negative, neutral, positive
            if len(probs) == 3:
                labels = ["Negative", "Neutral", "Positive"]
                label_idx = np.argmax(probs)
                label = labels[label_idx]
                # Map to [-1, 1]
                sentiment_score = float(probs[2] - probs[0])
            else:
                sentiment_score = 0.0
                label = "Neutral"
            
            result = {
                'score': sentiment_score,
                'label': label,
                'confidence': float(np.max(probs)),
                'probabilities': probs.tolist(),
                'language': 'english',
                'domain': 'financial'
            }
            
            logger.info(f"Financial sentiment: {label} (score: {sentiment_score:.3f})")
            
            return result
            
        except Exception as e:
            logger.error(f"Financial sentiment analysis failed: {e}")
            return self._fallback_sentiment(text)
    
    def analyze_multilingual(self, text: str) -> Dict:
        """
        다국어 감성 분석
        
        Args:
            text: 텍스트 (자동 언어 감지)
        
        Returns:
            감성 분석 결과
        """
        try:
            if self.multilingual_model is None:
                self._load_multilingual_model()
            
            if self.multilingual_model is None:
                return self._fallback_sentiment(text)
            
            import torch
            
            # Tokenize
            inputs = self.multilingual_tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True
            )
            
            # Get prediction
            with torch.no_grad():
                outputs = self.multilingual_model(**inputs)
                logits = outputs.logits
                probabilities = torch.softmax(logits, dim=-1)
            
            probs = probabilities[0].numpy()
            
            # Model typically outputs 5 star ratings (1-5)
            # Map to sentiment score
            stars = np.arange(1, len(probs) + 1)
            avg_rating = float(np.dot(probs, stars))
            # Normalize to [-1, 1]
            sentiment_score = (avg_rating - 3) / 2  # Center at 3, scale to [-1, 1]
            
            if sentiment_score > 0.3:
                label = "Positive"
            elif sentiment_score < -0.3:
                label = "Negative"
            else:
                label = "Neutral"
            
            result = {
                'score': sentiment_score,
                'label': label,
                'confidence': float(np.max(probs)),
                'probabilities': probs.tolist(),
                'rating': avg_rating,
                'language': 'multilingual'
            }
            
            logger.info(f"Multilingual sentiment: {label} (score: {sentiment_score:.3f})")
            
            return result
            
        except Exception as e:
            logger.error(f"Multilingual sentiment analysis failed: {e}")
            return self._fallback_sentiment(text)
    
    def analyze_auto(self, text: str) -> Dict:
        """
        자동 언어 감지 및 감성 분석
        
        Args:
            text: 텍스트
        
        Returns:
            감성 분석 결과
        """
        try:
            # Detect language
            language = self._detect_language(text)
            
            if language == "ko":
                return self.analyze_korean(text)
            elif language == "en":
                # Check if it's financial text
                if self._is_financial_text(text):
                    return self.analyze_financial_english(text)
                else:
                    return self.analyze_multilingual(text)
            else:
                return self.analyze_multilingual(text)
            
        except Exception as e:
            logger.error(f"Auto sentiment analysis failed: {e}")
            return self._fallback_sentiment(text)
    
    def _detect_language(self, text: str) -> str:
        """언어 감지"""
        try:
            import langdetect
            lang = langdetect.detect(text)
            return lang
        except:
            # Fallback: simple heuristic
            # Check for Korean characters
            if any('\uac00' <= char <= '\ud7a3' for char in text):
                return "ko"
            else:
                return "en"
    
    def _is_financial_text(self, text: str) -> bool:
        """금융 텍스트 여부 판단"""
        financial_keywords = [
            "stock", "market", "trading", "investment", "price",
            "bullish", "bearish", "profit", "loss", "revenue",
            "earnings", "dividend", "crypto", "bitcoin", "blockchain"
        ]
        
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in financial_keywords)
    
    def _fallback_sentiment(self, text: str) -> Dict:
        """Fallback: 간단한 감성 분석"""
        # Simple keyword-based sentiment
        positive_words = ["good", "great", "excellent", "bullish", "profit", "gain", "좋", "상승", "이익"]
        negative_words = ["bad", "poor", "terrible", "bearish", "loss", "decline", "나쁨", "하락", "손실"]
        
        text_lower = text.lower()
        
        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)
        
        total = pos_count + neg_count
        if total == 0:
            sentiment_score = 0.0
            label = "Neutral"
        else:
            sentiment_score = (pos_count - neg_count) / total
            if sentiment_score > 0.3:
                label = "Positive"
            elif sentiment_score < -0.3:
                label = "Negative"
            else:
                label = "Neutral"
        
        return {
            'score': sentiment_score,
            'label': label,
            'confidence': 0.5,
            'method': 'fallback'
        }


def analyze_sentiment(text: str, language: Optional[str] = None) -> Dict:
    """
    Convenience function for sentiment analysis
    
    Args:
        text: 텍스트
        language: 언어 ('ko', 'en', 'auto' 등)
    
    Returns:
        감성 분석 결과
    """
    analyzer = MultilingualSentimentAnalyzer()
    
    if language == "ko":
        return analyzer.analyze_korean(text)
    elif language == "en_financial":
        return analyzer.analyze_financial_english(text)
    elif language is None or language == "auto":
        return analyzer.analyze_auto(text)
    else:
        return analyzer.analyze_multilingual(text)


if __name__ == "__main__":
    """테스트 실행"""
    # Test Korean
    korean_text = "이 코인은 정말 좋은 투자입니다. 앞으로 가격이 많이 오를 것 같습니다."
    
    # Test English financial
    english_text = "The stock market is showing bullish signals with strong earnings reports."
    
    analyzer = MultilingualSentimentAnalyzer()
    
    print("Korean sentiment:")
    result_ko = analyzer.analyze_auto(korean_text)
    print(f"  Label: {result_ko['label']}, Score: {result_ko['score']:.3f}")
    
    print("\nEnglish financial sentiment:")
    result_en = analyzer.analyze_auto(english_text)
    print(f"  Label: {result_en['label']}, Score: {result_en['score']:.3f}")
