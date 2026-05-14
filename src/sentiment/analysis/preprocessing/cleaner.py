"""
Text Cleaner - 텍스트 정제
"""

import re
import logging

logger = logging.getLogger(__name__)


class TextCleaner:
    """텍스트 정제 클래스"""
    
    def __init__(self):
        """Initialize text cleaner"""
        self.html_pattern = re.compile(r'<[^>]+>')
        self.url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
        self.mention_pattern = re.compile(r'@\w+')
        self.hashtag_pattern = re.compile(r'#\w+')
    
    def clean(self, text: str, remove_urls: bool = True, remove_mentions: bool = False, 
              remove_hashtags: bool = False) -> str:
        """
        텍스트 정제
        
        Args:
            text: Input text
            remove_urls: Whether to remove URLs
            remove_mentions: Whether to remove @mentions
            remove_hashtags: Whether to remove #hashtags
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        # HTML 태그 제거
        text = self.html_pattern.sub('', text)
        
        # URL 제거
        if remove_urls:
            text = self.url_pattern.sub('', text)
        
        # Mention 제거
        if remove_mentions:
            text = self.mention_pattern.sub('', text)
        
        # Hashtag 제거 (but keep the word)
        if remove_hashtags:
            text = self.hashtag_pattern.sub(lambda m: m.group(0)[1:], text)
        
        # 연속된 공백 제거
        text = ' '.join(text.split())
        
        # 앞뒤 공백 제거
        return text.strip()
    
    def remove_special_chars(self, text: str, keep_alphanumeric: bool = True) -> str:
        """
        특수 문자 제거
        
        Args:
            text: Input text
            keep_alphanumeric: Keep alphanumeric characters
            
        Returns:
            Cleaned text
        """
        if keep_alphanumeric:
            # Keep alphanumeric, spaces, and common punctuation
            text = re.sub(r'[^a-zA-Z0-9가-힣\s.,!?]', '', text)
        else:
            # Remove all special characters except spaces
            text = re.sub(r'[^a-zA-Z0-9가-힣\s]', '', text)
        
        return ' '.join(text.split())
