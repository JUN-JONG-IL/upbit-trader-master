"""
Language Detector - Detect language of text
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class LanguageDetector:
    """Detects language of text"""
    
    def __init__(self):
        self.supported_languages = ['en', 'ko', 'ja', 'zh']
        
        # Character ranges for detection
        self.korean_pattern = r'[가-힣]'
        self.japanese_pattern = r'[ぁ-んァ-ヶー]'
        self.chinese_pattern = r'[一-龯]'
    
    def detect(self, text: str) -> str:
        """
        Detect language of text
        
        Args:
            text: Input text
            
        Returns:
            Language code (en, ko, ja, zh, unknown)
        """
        if not text:
            return "unknown"
        
        # Try using langdetect library if available
        try:
            import langdetect
            lang = langdetect.detect(text)
            return lang
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"langdetect failed: {e}")
        
        # Fallback to simple character-based detection
        return self._detect_by_characters(text)
    
    def _detect_by_characters(self, text: str) -> str:
        """
        Detect language by character patterns
        
        Args:
            text: Input text
            
        Returns:
            Language code
        """
        import re
        
        # Count characters for each language
        korean_count = len(re.findall(self.korean_pattern, text))
        japanese_count = len(re.findall(self.japanese_pattern, text))
        chinese_count = len(re.findall(self.chinese_pattern, text))
        
        # Determine language
        total_chars = len(text)
        if total_chars == 0:
            return "unknown"
        
        if korean_count / total_chars > 0.1:
            return "ko"
        elif japanese_count / total_chars > 0.1:
            return "ja"
        elif chinese_count / total_chars > 0.1:
            return "zh"
        else:
            return "en"  # Default to English
    
    def detect_with_confidence(self, text: str) -> Dict[str, float]:
        """
        Detect language with confidence scores
        
        Args:
            text: Input text
            
        Returns:
            Dictionary of language -> confidence
        """
        try:
            import langdetect
            from langdetect import detect_langs
            
            langs = detect_langs(text)
            return {lang.lang: lang.prob for lang in langs}
        except:
            # Fallback
            detected_lang = self.detect(text)
            return {detected_lang: 1.0}
    
    def is_supported(self, language: str) -> bool:
        """
        Check if language is supported
        
        Args:
            language: Language code
            
        Returns:
            True if supported
        """
        return language in self.supported_languages
