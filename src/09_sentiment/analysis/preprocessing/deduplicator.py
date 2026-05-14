"""
Deduplicator - Remove duplicate documents
"""

import logging
import hashlib
from typing import List, Dict, Set

logger = logging.getLogger(__name__)


class Deduplicator:
    """Removes duplicate documents"""
    
    def __init__(self, similarity_threshold: float = 0.9):
        self.similarity_threshold = similarity_threshold
        self.seen_hashes: Set[str] = set()
    
    def deduplicate(
        self,
        documents: List[Dict],
        key: str = "content"
    ) -> List[Dict]:
        """
        Remove duplicate documents
        
        Args:
            documents: List of document dictionaries
            key: Key to use for deduplication
            
        Returns:
            Deduplicated list
        """
        unique_docs = []
        
        for doc in documents:
            content = doc.get(key, "")
            doc_hash = self._hash_content(content)
            
            if doc_hash not in self.seen_hashes:
                self.seen_hashes.add(doc_hash)
                unique_docs.append(doc)
        
        logger.info(f"Deduplicated: {len(documents)} -> {len(unique_docs)} documents")
        
        return unique_docs
    
    def _hash_content(self, content: str) -> str:
        """
        Hash content for comparison
        
        Args:
            content: Text content
            
        Returns:
            Hash string
        """
        # Normalize content
        normalized = content.lower().strip()
        
        # Create hash
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def is_duplicate(self, content: str) -> bool:
        """
        Check if content is duplicate
        
        Args:
            content: Text content
            
        Returns:
            True if duplicate
        """
        doc_hash = self._hash_content(content)
        return doc_hash in self.seen_hashes
    
    def add_to_seen(self, content: str):
        """
        Add content to seen set
        
        Args:
            content: Text content
        """
        doc_hash = self._hash_content(content)
        self.seen_hashes.add(doc_hash)
    
    def clear(self):
        """Clear seen hashes"""
        self.seen_hashes.clear()
        logger.info("Cleared seen hashes")
    
    def get_stats(self) -> Dict:
        """
        Get deduplication statistics
        
        Returns:
            Dictionary with stats
        """
        return {
            "unique_documents": len(self.seen_hashes),
            "similarity_threshold": self.similarity_threshold
        }
