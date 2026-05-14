"""
Smart Tokenizer - 토크나이저
"""

import logging
import re
from typing import List

logger = logging.getLogger(__name__)


class SmartTokenizer:
    """스마트 토크나이저"""
    
    def __init__(self, language: str = "en"):
        """
        Initialize tokenizer
        
        Args:
            language: Language code ('en', 'ko', etc.)
        """
        self.language = language
        self._load_tokenizer()
    
    def _load_tokenizer(self):
        """Load appropriate tokenizer for language"""
        if self.language == "ko":
            try:
                # Try to use Korean tokenizer if available
                from konlpy.tag import Okt
                self.ko_tokenizer = Okt()
                logger.info("Korean tokenizer (Okt) loaded")
            except ImportError:
                logger.warning("konlpy not available, using basic tokenization")
                self.ko_tokenizer = None
        else:
            self.ko_tokenizer = None
    
    def tokenize(self, text: str, preserve_case: bool = False) -> List[str]:
        """
        텍스트 토큰화
        
        Args:
            text: Input text
            preserve_case: Preserve original case
            
        Returns:
            List of tokens
        """
        if not text:
            return []
        
        # Lowercase if needed
        if not preserve_case:
            text = text.lower()
        
        # Korean tokenization
        if self.language == "ko" and self.ko_tokenizer:
            try:
                return self.ko_tokenizer.morphs(text)
            except Exception as e:
                logger.warning(f"Korean tokenization failed: {e}, using basic tokenization")
        
        # Basic tokenization for English and fallback
        # Split on whitespace and punctuation but keep words together
        tokens = re.findall(r'\b\w+\b', text)
        
        return tokens
    
    def tokenize_sentences(self, text: str) -> List[str]:
        """
        문장 단위 토큰화
        
        Args:
            text: Input text
            
        Returns:
            List of sentences
        """
        if not text:
            return []
        
        # Simple sentence tokenization
        # Split on periods, exclamation marks, question marks
        sentences = re.split(r'[.!?]+', text)
        
        # Clean up and filter empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return sentences
    
    def get_ngrams(self, tokens: List[str], n: int = 2) -> List[str]:
        """
        Generate n-grams from tokens
        
        Args:
            tokens: List of tokens
            n: N-gram size
            
        Returns:
            List of n-grams
        """
        if len(tokens) < n:
            return []
        
        ngrams = []
        for i in range(len(tokens) - n + 1):
            ngram = ' '.join(tokens[i:i+n])
            ngrams.append(ngram)
        
        return ngrams
