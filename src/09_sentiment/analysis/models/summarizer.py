"""
Summarizer - Text summarization
"""

import logging
from typing import Optional, List

logger = logging.getLogger(__name__)


class Summarizer:
    """Text summarization"""
    
    def __init__(self, max_length: int = 150):
        self.max_length = max_length
    
    def summarize(
        self,
        text: str,
        max_sentences: int = 3,
        method: str = "extractive"
    ) -> str:
        """
        Summarize text
        
        Args:
            text: Input text
            max_sentences: Maximum number of sentences in summary
            method: Summarization method ('extractive' or 'abstractive')
            
        Returns:
            Summary text
        """
        if not text:
            return ""
        
        if method == "extractive":
            return self._extractive_summary(text, max_sentences)
        else:
            return self._abstractive_summary(text)
    
    def _extractive_summary(self, text: str, max_sentences: int) -> str:
        """
        Extractive summarization (select important sentences)
        
        Args:
            text: Input text
            max_sentences: Max sentences
            
        Returns:
            Summary
        """
        # Split into sentences
        sentences = text.split('. ')
        
        if len(sentences) <= max_sentences:
            return text
        
        # Simple: take first N sentences
        # In production, would use sentence scoring (TF-IDF, TextRank, etc.)
        summary_sentences = sentences[:max_sentences]
        
        return '. '.join(summary_sentences) + '.'
    
    def _abstractive_summary(self, text: str) -> str:
        """
        Abstractive summarization (generate new text)
        
        Args:
            text: Input text
            
        Returns:
            Summary
        """
        # Mock implementation - in production would use T5 or BART
        # For now, just truncate
        if len(text) > self.max_length:
            return text[:self.max_length] + "..."
        return text
    
    def summarize_batch(self, texts: List[str], max_sentences: int = 3) -> List[str]:
        """
        Summarize multiple texts
        
        Args:
            texts: List of texts
            max_sentences: Max sentences per summary
            
        Returns:
            List of summaries
        """
        return [self.summarize(text, max_sentences) for text in texts]


# Alias for compatibility
TextSummarizer = Summarizer
