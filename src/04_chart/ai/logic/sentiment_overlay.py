# -*- coding: utf-8 -*-
"""
Sentiment Overlay - Display sentiment analysis on charts
Shows market sentiment from news and social media
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from PyQt5.QtCore import QThread, pyqtSignal


class SentimentData:
    """Sentiment data point"""
    
    def __init__(self, timestamp: datetime, score: float, source: str = "unknown"):
        self.timestamp = timestamp
        self.score = score  # Range: -1.0 (very negative) to 1.0 (very positive)
        self.source = source
        self.text = ""
        self.confidence = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "score": self.score,
            "source": self.source,
            "text": self.text,
            "confidence": self.confidence,
        }


class SentimentOverlay:
    """
    Sentiment analysis overlay for charts.
    
    Features:
    - Aggregates sentiment from multiple sources
    - Displays as bar chart below price chart
    - Color-coded: green (positive), red (negative), gray (neutral)
    """
    
    def __init__(self):
        self.sentiment_data: List[SentimentData] = []
        self.aggregation_period = "1H"  # Aggregate by hour
    
    def load_sentiment_data(self, symbol: str, timeframe: str, 
                           start_date: Optional[datetime] = None,
                           end_date: Optional[datetime] = None) -> List[SentimentData]:
        """
        Load sentiment data for a symbol and timeframe.
        
        Args:
            symbol: Trading symbol (e.g., "KRW-BTC")
            timeframe: Timeframe (e.g., "1H", "1D")
            start_date: Start date for data
            end_date: End date for data
        
        Returns:
            List of SentimentData objects
        """
        # In a real implementation, this would fetch from:
        # - News API
        # - Twitter API
        # - Reddit API
        # - Telegram channels
        # - etc.
        
        # For now, generate dummy data
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now()
        
        self.sentiment_data = self._generate_dummy_sentiment(start_date, end_date)
        return self.sentiment_data
    
    def _generate_dummy_sentiment(self, start_date: datetime, end_date: datetime) -> List[SentimentData]:
        """Generate dummy sentiment data for demonstration"""
        data = []
        current = start_date
        
        while current <= end_date:
            # Random sentiment with some autocorrelation
            if len(data) > 0:
                # Tend to be similar to previous sentiment
                prev_score = data[-1].score
                score = prev_score + np.random.normal(0, 0.2)
            else:
                score = np.random.normal(0, 0.3)
            
            # Clip to valid range
            score = max(-1.0, min(1.0, score))
            
            sentiment = SentimentData(current, score, "dummy")
            sentiment.confidence = np.random.uniform(0.7, 1.0)
            data.append(sentiment)
            
            current += timedelta(hours=1)
        
        return data
    
    def aggregate_by_timeframe(self, timeframe: str = "1H") -> pd.DataFrame:
        """
        Aggregate sentiment data by timeframe.
        
        Args:
            timeframe: Aggregation period (e.g., "1H", "4H", "1D")
        
        Returns:
            DataFrame with aggregated sentiment
        """
        if not self.sentiment_data:
            return pd.DataFrame(columns=["timestamp", "score", "count"])
        
        # Convert to DataFrame
        df = pd.DataFrame([{
            "timestamp": s.timestamp,
            "score": s.score,
            "confidence": s.confidence
        } for s in self.sentiment_data])
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp')
        
        # Aggregate
        aggregated = df.resample(timeframe).agg({
            'score': 'mean',
            'confidence': 'mean'
        })
        aggregated['count'] = df.resample(timeframe).size()
        
        return aggregated.reset_index()
    
    def get_sentiment_for_timestamp(self, timestamp: datetime, window: timedelta = timedelta(hours=1)) -> float:
        """
        Get aggregated sentiment for a specific timestamp.
        
        Args:
            timestamp: Target timestamp
            window: Time window to aggregate over
        
        Returns:
            Average sentiment score (-1.0 to 1.0)
        """
        start = timestamp - window / 2
        end = timestamp + window / 2
        
        relevant = [
            s.score for s in self.sentiment_data
            if start <= s.timestamp <= end
        ]
        
        if not relevant:
            return 0.0
        
        return np.mean(relevant)
    
    def get_sentiment_color(self, score: float) -> str:
        """
        Get color for sentiment score.
        
        Args:
            score: Sentiment score (-1.0 to 1.0)
        
        Returns:
            Color string (hex)
        """
        if score > 0.3:
            # Positive: Green gradient
            intensity = min(1.0, score)
            green = int(50 + intensity * 150)
            return f"#{0:02x}{green:02x}{0:02x}"
        elif score < -0.3:
            # Negative: Red gradient
            intensity = min(1.0, abs(score))
            red = int(50 + intensity * 150)
            return f"#{red:02x}{0:02x}{0:02x}"
        else:
            # Neutral: Gray
            return "#808080"
    
    def get_sentiment_label(self, score: float) -> str:
        """
        Get text label for sentiment score.
        
        Args:
            score: Sentiment score (-1.0 to 1.0)
        
        Returns:
            Label string
        """
        if score > 0.7:
            return "Very Positive"
        elif score > 0.3:
            return "Positive"
        elif score > -0.3:
            return "Neutral"
        elif score > -0.7:
            return "Negative"
        else:
            return "Very Negative"
    
    def render_overlay(self, chart, data: pd.DataFrame):
        """
        Render sentiment overlay on chart.
        
        This should be called by the chart engine to display sentiment bars
        below the price chart.
        
        Args:
            chart: Chart object
            data: Price data DataFrame with timestamps
        """
        # Get aggregated sentiment matching the price data timeframe
        aggregated = self.aggregate_by_timeframe(self.aggregation_period)
        
        if aggregated.empty:
            return
        
        # Align with price data timestamps
        # This is chart-engine specific and would need to be implemented
        # for each chart engine (matplotlib, plotly, etc.)
        pass


class SentimentWorker(QThread):
    """QThread worker for async sentiment data fetching"""
    
    finished = pyqtSignal(list)  # List of SentimentData
    error = pyqtSignal(str)
    progress = pyqtSignal(int)
    
    def __init__(self, symbol: str, timeframe: str,
                 start_date: Optional[datetime] = None,
                 end_date: Optional[datetime] = None):
        super().__init__()
        self.symbol = symbol
        self.timeframe = timeframe
        self.start_date = start_date
        self.end_date = end_date
        self.overlay = SentimentOverlay()
    
    def run(self):
        """Fetch sentiment data in background thread"""
        try:
            self.progress.emit(10)
            data = self.overlay.load_sentiment_data(
                self.symbol,
                self.timeframe,
                self.start_date,
                self.end_date
            )
            self.progress.emit(100)
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class SentimentAnalyzer:
    """
    Advanced sentiment analysis using NLP.
    
    In a real implementation, this would use:
    - BERT/Transformer models for text analysis
    - Named Entity Recognition (NER) for extracting mentions
    - Aspect-based sentiment analysis
    - Multi-language support
    """
    
    def __init__(self):
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """Load sentiment analysis model"""
        try:
            # In a real implementation:
            # from transformers import pipeline
            # self.model = pipeline("sentiment-analysis", model="finbert")
            pass
        except Exception:
            pass
    
    def analyze_text(self, text: str) -> float:
        """
        Analyze sentiment of text.
        
        Args:
            text: Input text to analyze
        
        Returns:
            Sentiment score (-1.0 to 1.0)
        """
        if self.model is None:
            # Fallback: simple keyword-based sentiment
            return self._simple_sentiment(text)
        
        # Use trained model
        result = self.model(text)[0]
        
        # Convert to -1.0 to 1.0 scale
        if result['label'] == 'POSITIVE':
            return result['score']
        else:
            return -result['score']
    
    def _simple_sentiment(self, text: str) -> float:
        """Simple keyword-based sentiment analysis"""
        text_lower = text.lower()
        
        positive_words = [
            'bullish', 'moon', 'pump', 'buy', 'long', 'rally', 'breakout',
            'green', 'profit', 'gain', 'up', 'high', 'surge', 'rise'
        ]
        negative_words = [
            'bearish', 'dump', 'sell', 'short', 'crash', 'breakdown',
            'red', 'loss', 'down', 'low', 'drop', 'fall', 'decline'
        ]
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        total = positive_count + negative_count
        if total == 0:
            return 0.0
        
        score = (positive_count - negative_count) / total
        return max(-1.0, min(1.0, score))
    
    def analyze_social_media(self, symbol: str, source: str = "twitter",
                            max_posts: int = 100) -> List[SentimentData]:
        """
        Analyze sentiment from social media posts.
        
        Args:
            symbol: Trading symbol
            source: Social media source ("twitter", "reddit", "telegram")
            max_posts: Maximum number of posts to analyze
        
        Returns:
            List of SentimentData objects
        """
        # In a real implementation, this would:
        # 1. Fetch recent posts mentioning the symbol
        # 2. Analyze sentiment of each post
        # 3. Aggregate and return results
        
        # For now, return empty list
        return []
