"""
Topic Model - Topic modeling for document clustering
"""

import logging
from typing import List, Dict
from collections import Counter

logger = logging.getLogger(__name__)


class TopicModel:
    """Topic modeling for document clustering"""
    
    def __init__(self, n_topics: int = 5):
        self.n_topics = n_topics
        self.topics = []
    
    def fit(self, documents: List[str]):
        """
        Fit topic model on documents
        
        Args:
            documents: List of documents
        """
        # Simple keyword-based topics (mock implementation)
        # In production, would use LDA or BERTopic
        
        # Extract common words
        all_words = []
        for doc in documents:
            words = doc.lower().split()
            all_words.extend(words)
        
        # Get most common words as topics
        word_counts = Counter(all_words)
        common_words = word_counts.most_common(self.n_topics * 5)
        
        # Create topics
        self.topics = []
        for i in range(self.n_topics):
            topic_words = common_words[i*5:(i+1)*5]
            self.topics.append({
                "id": i,
                "words": [w[0] for w in topic_words],
                "weights": [w[1] for w in topic_words]
            })
        
        logger.info(f"Fitted topic model with {self.n_topics} topics")
    
    def predict(self, document: str) -> Dict:
        """
        Predict topic for document
        
        Args:
            document: Input document
            
        Returns:
            Topic dictionary
        """
        if not self.topics:
            return {"topic_id": 0, "confidence": 0.0}
        
        # Simple scoring based on word overlap
        doc_words = set(document.lower().split())
        
        scores = []
        for topic in self.topics:
            topic_words = set(topic["words"])
            overlap = len(doc_words & topic_words)
            scores.append(overlap)
        
        best_topic_idx = scores.index(max(scores)) if scores else 0
        
        return {
            "topic_id": best_topic_idx,
            "topic_words": self.topics[best_topic_idx]["words"],
            "confidence": max(scores) / max(len(doc_words), 1)
        }
    
    def get_topics(self) -> List[Dict]:
        """Get all topics"""
        return self.topics


# Alias for compatibility
TopicModeler = TopicModel
