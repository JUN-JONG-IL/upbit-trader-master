"""
NLP Models Package - Sentiment, NER, Topic modeling, Summarization
"""

from .sentiment_model import SentimentAnalyzer
from .ner_model import NERModel
from .topic_model import TopicModel
from .summarizer import Summarizer

# Aliases for compatibility
NamedEntityRecognizer = NERModel
TopicModeler = TopicModel
TextSummarizer = Summarizer

__all__ = [
    'SentimentAnalyzer', 
    'NERModel', 
    'TopicModel', 
    'Summarizer',
    'NamedEntityRecognizer',
    'TopicModeler',
    'TextSummarizer'
]
