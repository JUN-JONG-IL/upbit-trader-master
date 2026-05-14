#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Topic Modeling Module

BERTopic을 사용하여 동적 토픽 추출 및 분석을 수행합니다.
- BERTopic 기반 토픽 모델링
- Topics Over Time 분석
- 토픽 간 상관관계 분석
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)


class TopicModeler:
    """
    BERTopic 기반 토픽 모델링
    """
    
    def __init__(self, language: str = "multilingual", n_topics: int = 10):
        """
        Initialize Topic Modeler
        
        Args:
            language: 언어 ("korean", "english", "multilingual")
            n_topics: 토픽 개수
        """
        self.language = language
        self.n_topics = n_topics
        self.model = None
        self.topics = None
        self.topic_info = None
        
        logger.info(f"Topic Modeler initialized (language: {language}, n_topics: {n_topics})")
    
    def fit(self, documents: List[str], timestamps: Optional[List[datetime]] = None) -> Dict:
        """
        토픽 모델 학습
        
        Args:
            documents: 문서 리스트
            timestamps: 문서 타임스탬프 (Topics Over Time 분석용)
        
        Returns:
            토픽 모델링 결과
        """
        try:
            from bertopic import BERTopic
            
            # Create model
            self.model = BERTopic(
                language=self.language if self.language != "korean" else "multilingual",
                nr_topics=self.n_topics,
                calculate_probabilities=True,
                verbose=False
            )
            
            # Fit model
            self.topics, self.probs = self.model.fit_transform(documents)
            
            # Get topic info
            self.topic_info = self.model.get_topic_info()
            
            # Topics over time analysis if timestamps provided
            topics_over_time = None
            if timestamps is not None:
                topics_over_time = self.model.topics_over_time(
                    documents,
                    timestamps,
                    nr_bins=20
                )
            
            result = {
                'n_topics': len(set(self.topics)) - 1,  # Exclude outlier topic (-1)
                'topic_info': self.topic_info.to_dict('records') if hasattr(self.topic_info, 'to_dict') else [],
                'topics': self.topics,
                'topics_over_time': topics_over_time.to_dict('records') if topics_over_time is not None and hasattr(topics_over_time, 'to_dict') else None
            }
            
            logger.info(f"Topic modeling completed: {result['n_topics']} topics found")
            
            return result
            
        except ImportError:
            logger.error("BERTopic not installed. Install with: pip install bertopic")
            return self._fallback_topic_modeling(documents)
        except Exception as e:
            logger.error(f"Topic modeling failed: {e}")
            return self._fallback_topic_modeling(documents)
    
    def get_topic_keywords(self, topic_id: int, top_n: int = 10) -> List[Tuple[str, float]]:
        """
        토픽의 주요 키워드 반환
        
        Args:
            topic_id: 토픽 ID
            top_n: 상위 N개 키워드
        
        Returns:
            (키워드, 점수) 튜플 리스트
        """
        try:
            if self.model is None:
                logger.warning("Model not trained yet")
                return []
            
            topic = self.model.get_topic(topic_id)
            
            if topic:
                return topic[:top_n]
            else:
                return []
            
        except Exception as e:
            logger.error(f"Failed to get topic keywords: {e}")
            return []
    
    def get_document_topics(self, documents: List[str]) -> List[int]:
        """
        문서의 토픽 예측
        
        Args:
            documents: 문서 리스트
        
        Returns:
            토픽 ID 리스트
        """
        try:
            if self.model is None:
                logger.warning("Model not trained yet")
                return [-1] * len(documents)
            
            topics, _ = self.model.transform(documents)
            
            return topics
            
        except Exception as e:
            logger.error(f"Failed to predict topics: {e}")
            return [-1] * len(documents)
    
    def get_topic_similarity(self) -> np.ndarray:
        """
        토픽 간 유사도 계산
        
        Returns:
            토픽 유사도 행렬
        """
        try:
            if self.model is None:
                logger.warning("Model not trained yet")
                return np.array([])
            
            # Get topic embeddings
            topic_embeddings = np.array([
                self.model.topic_embeddings_[topic_id]
                for topic_id in range(len(self.model.topic_embeddings_))
                if topic_id != -1  # Exclude outlier topic
            ])
            
            # Calculate cosine similarity
            from sklearn.metrics.pairwise import cosine_similarity
            similarity_matrix = cosine_similarity(topic_embeddings)
            
            logger.info(f"Topic similarity calculated: {similarity_matrix.shape}")
            
            return similarity_matrix
            
        except Exception as e:
            logger.error(f"Failed to calculate topic similarity: {e}")
            return np.array([])
    
    def reduce_topics(self, n_topics: int) -> Dict:
        """
        토픽 개수 축소
        
        Args:
            n_topics: 목표 토픽 개수
        
        Returns:
            축소 결과
        """
        try:
            if self.model is None:
                logger.warning("Model not trained yet")
                return {}
            
            self.model.reduce_topics(docs=None, nr_topics=n_topics)
            
            # Update topic info
            self.topic_info = self.model.get_topic_info()
            
            result = {
                'n_topics': len(set(self.model.topics_)) - 1,
                'topic_info': self.topic_info.to_dict('records') if hasattr(self.topic_info, 'to_dict') else []
            }
            
            logger.info(f"Topics reduced to {result['n_topics']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to reduce topics: {e}")
            return {}
    
    def _fallback_topic_modeling(self, documents: List[str]) -> Dict:
        """Fallback: LDA 기반 토픽 모델링"""
        try:
            from sklearn.feature_extraction.text import CountVectorizer
            from sklearn.decomposition import LatentDirichletAllocation
            
            # Vectorize documents
            vectorizer = CountVectorizer(max_features=1000, stop_words='english')
            doc_term_matrix = vectorizer.fit_transform(documents)
            
            # LDA
            lda = LatentDirichletAllocation(
                n_components=self.n_topics,
                random_state=42
            )
            self.topics = lda.fit_transform(doc_term_matrix).argmax(axis=1)
            
            # Get top words for each topic
            feature_names = vectorizer.get_feature_names_out()
            topics_info = []
            
            for topic_idx, topic in enumerate(lda.components_):
                top_indices = topic.argsort()[-10:][::-1]
                top_words = [feature_names[i] for i in top_indices]
                
                topics_info.append({
                    'Topic': topic_idx,
                    'Count': int(np.sum(self.topics == topic_idx)),
                    'Keywords': ', '.join(top_words)
                })
            
            result = {
                'n_topics': self.n_topics,
                'topic_info': topics_info,
                'topics': self.topics.tolist(),
                'method': 'LDA (fallback)'
            }
            
            logger.info(f"Fallback topic modeling completed: {self.n_topics} topics")
            
            return result
            
        except Exception as e:
            logger.error(f"Fallback topic modeling failed: {e}")
            return {
                'n_topics': 0,
                'topic_info': [],
                'topics': []
            }


def extract_topics(
    documents: List[str],
    timestamps: Optional[List[datetime]] = None,
    language: str = "multilingual",
    n_topics: int = 10
) -> Dict:
    """
    Convenience function for topic extraction
    
    Args:
        documents: 문서 리스트
        timestamps: 타임스탬프 리스트
        language: 언어
        n_topics: 토픽 개수
    
    Returns:
        토픽 모델링 결과
    """
    modeler = TopicModeler(language, n_topics)
    return modeler.fit(documents, timestamps)


if __name__ == "__main__":
    """테스트 실행"""
    # Generate synthetic documents
    documents = [
        "Bitcoin price is rising rapidly today",
        "Ethereum network upgrade successful",
        "Stock market shows bullish trends",
        "Cryptocurrency regulations announced",
        "Bitcoin mining difficulty increases",
        "Ethereum gas fees remain high",
        "Stock market volatility concerns",
        "New crypto exchange launched",
        "Bitcoin halving event approaching",
        "Ethereum staking rewards announced"
    ]
    
    timestamps = [datetime.now() for _ in documents]
    
    # Extract topics
    result = extract_topics(documents, timestamps, language="english", n_topics=3)
    
    print("Topic Modeling Results:")
    print(f"  Number of topics: {result['n_topics']}")
    
    if result['topic_info']:
        print("\nTop Topics:")
        for topic in result['topic_info'][:3]:
            print(f"  Topic {topic.get('Topic', 'N/A')}: {topic.get('Keywords', 'N/A')[:50]}...")
