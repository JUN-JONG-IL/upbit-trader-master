"""
Sentiment Analyzer - Multi-language sentiment analysis
"""

import logging
from typing import Dict, Optional
import re

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """Multi-language sentiment analysis"""
    
    def __init__(self):
        self.models = {}
        self._initialize_models()
    
    def _initialize_models(self):
        """Initialize sentiment models for different languages"""
        # Try to load transformer models, fall back to rule-based
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            
            # English model
            try:
                self.models['en'] = {
                    'model': AutoModelForSequenceClassification.from_pretrained(
                        "cardiffnlp/twitter-roberta-base-sentiment"
                    ),
                    'tokenizer': AutoTokenizer.from_pretrained(
                        "cardiffnlp/twitter-roberta-base-sentiment"
                    )
                }
                logger.info("Loaded English sentiment model")
            except:
                logger.warning("Failed to load English model, using rule-based")
                self.models['en'] = None
            
            # Korean model
            try:
                self.models['ko'] = {
                    'model': AutoModelForSequenceClassification.from_pretrained(
                        "beomi/kcbert-base"
                    ),
                    'tokenizer': AutoTokenizer.from_pretrained(
                        "beomi/kcbert-base"
                    )
                }
                logger.info("Loaded Korean sentiment model")
            except:
                logger.warning("Failed to load Korean model, using rule-based")
                self.models['ko'] = None
                
        except ImportError:
            logger.warning("transformers not available, using rule-based sentiment")
    
    def analyze(self, text: str, lang: str = "en") -> Dict:
        """
        Analyze sentiment of text
        
        Args:
            text: Input text
            lang: Language code (en, ko, ja)
            
        Returns:
            Dictionary with sentiment analysis results
        """
        if not text:
            return {
                "score": 0.0,
                "label": "neutral",
                "confidence": 0.0
            }
        
        # Try transformer model if available
        if lang in self.models and self.models[lang] is not None:
            return self._analyze_with_transformer(text, lang)
        else:
            return self._analyze_rule_based(text, lang)
    
    def _analyze_with_transformer(self, text: str, lang: str) -> Dict:
        """
        Analyze sentiment using transformer model
        
        Args:
            text: Input text
            lang: Language code
            
        Returns:
            Sentiment dictionary
        """
        try:
            import torch
            
            model_dict = self.models[lang]
            model = model_dict['model']
            tokenizer = model_dict['tokenizer']
            
            # Tokenize
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
            
            # Predict
            with torch.no_grad():
                outputs = model(**inputs)
                probs = torch.softmax(outputs.logits, dim=1)[0]
            
            # Convert to score (-1 to +1)
            # Assuming 3-class model: [negative, neutral, positive]
            score = probs[2].item() - probs[0].item()
            
            return {
                "score": float(score),
                "label": self._get_label(score),
                "confidence": float(max(probs)),
                "probabilities": {
                    "negative": float(probs[0]),
                    "neutral": float(probs[1]),
                    "positive": float(probs[2])
                }
            }
        except Exception as e:
            logger.error(f"Transformer analysis failed: {e}")
            return self._analyze_rule_based(text, lang)
    
    def _analyze_rule_based(self, text: str, lang: str) -> Dict:
        """
        Analyze sentiment using rule-based approach
        
        Args:
            text: Input text
            lang: Language code
            
        Returns:
            Sentiment dictionary
        """
        # Simple keyword-based sentiment
        positive_keywords = {
            'en': ['good', 'great', 'excellent', 'bullish', 'moon', 'buy', 'profit', 'gain'],
            'ko': ['좋은', '훌륭', '상승', '매수', '이익'],
            'ja': ['良い', '素晴らしい', '上昇']
        }
        
        negative_keywords = {
            'en': ['bad', 'poor', 'terrible', 'bearish', 'sell', 'loss', 'dump', 'crash'],
            'ko': ['나쁜', '하락', '매도', '손실'],
            'ja': ['悪い', '下落']
        }
        
        text_lower = text.lower()
        
        pos_count = sum(1 for kw in positive_keywords.get(lang, []) if kw in text_lower)
        neg_count = sum(1 for kw in negative_keywords.get(lang, []) if kw in text_lower)
        
        # Calculate score
        if pos_count + neg_count == 0:
            score = 0.0
        else:
            score = (pos_count - neg_count) / (pos_count + neg_count)
        
        return {
            "score": float(score),
            "label": self._get_label(score),
            "confidence": min(0.7, abs(score)),  # Lower confidence for rule-based
            "method": "rule_based"
        }
    
    def _get_label(self, score: float) -> str:
        """
        Convert score to label
        
        Args:
            score: Sentiment score (-1 to +1)
            
        Returns:
            Label string
        """
        if score > 0.3:
            return "positive"
        elif score < -0.3:
            return "negative"
        else:
            return "neutral"
    
    def analyze_batch(self, texts: list, lang: str = "en") -> list:
        """
        Analyze sentiment for batch of texts
        
        Args:
            texts: List of texts
            lang: Language code
            
        Returns:
            List of sentiment dictionaries
        """
        return [self.analyze(text, lang) for text in texts]
