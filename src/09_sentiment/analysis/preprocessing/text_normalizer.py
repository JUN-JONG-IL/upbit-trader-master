"""
Text Normalizer - Normalize and clean text data
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TextNormalizer:
    """Normalizes text data for NLP processing"""
    
    def __init__(self):
        # Patterns for cleaning
        self.url_pattern = re.compile(r'https?://\S+|www\.\S+')
        self.mention_pattern = re.compile(r'@\w+')
        self.hashtag_pattern = re.compile(r'#\w+')
        self.email_pattern = re.compile(r'\S+@\S+')
        self.special_chars_pattern = re.compile(r'[^\w\s가-힣ぁ-んァ-ヶ一-龯]')
    
    def normalize(
        self,
        text: str,
        remove_urls: bool = True,
        remove_mentions: bool = False,
        remove_hashtags: bool = False,
        remove_emails: bool = True,
        lowercase: bool = True,
        remove_special_chars: bool = False
    ) -> str:
        """
        Normalize text
        
        Args:
            text: Input text
            remove_urls: Remove URLs
            remove_mentions: Remove @mentions
            remove_hashtags: Remove #hashtags
            remove_emails: Remove email addresses
            lowercase: Convert to lowercase
            remove_special_chars: Remove special characters
            
        Returns:
            Normalized text
        """
        if not text:
            return ""
        
        # Remove URLs
        if remove_urls:
            text = self.url_pattern.sub('', text)
        
        # Remove mentions
        if remove_mentions:
            text = self.mention_pattern.sub('', text)
        
        # Remove hashtags
        if remove_hashtags:
            text = self.hashtag_pattern.sub('', text)
        
        # Remove emails
        if remove_emails:
            text = self.email_pattern.sub('', text)
        
        # Remove special characters
        if remove_special_chars:
            text = self.special_chars_pattern.sub(' ', text)
        
        # Convert to lowercase (preserve non-Latin scripts)
        if lowercase:
            text = text.lower()
        
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        return text
    
    def remove_emoji(self, text: str) -> str:
        """
        Remove emoji from text
        
        Args:
            text: Input text
            
        Returns:
            Text without emoji
        """
        # Simple emoji removal (basic implementation)
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE
        )
        return emoji_pattern.sub(r'', text)
    
    def extract_hashtags(self, text: str) -> list:
        """
        Extract hashtags from text
        
        Args:
            text: Input text
            
        Returns:
            List of hashtags
        """
        return self.hashtag_pattern.findall(text)
    
    def extract_mentions(self, text: str) -> list:
        """
        Extract mentions from text
        
        Args:
            text: Input text
            
        Returns:
            List of mentions
        """
        return self.mention_pattern.findall(text)
