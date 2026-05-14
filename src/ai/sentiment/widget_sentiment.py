#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sentiment Widget

Qt Widget for sentiment analysis functionality including:
- Multi-source scraping (News, Twitter, Reddit)
- Real-time sentiment visualization
- Word cloud generation
- Sentiment history tracking
"""

import logging
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import QWidget, QMessageBox, QTableWidgetItem, QVBoxLayout
from PyQt5.QtCore import pyqtSignal, QTimer, Qt, QThread, pyqtSlot
from PyQt5.QtGui import QColor
from PyQt5 import uic

from .sentiment_logic import SentimentLogic

logger = logging.getLogger(__name__)


class SentimentCollectionThread(QThread):
    """Background thread for sentiment data collection"""
    
    progress = pyqtSignal(int, str)  # progress percentage, status message
    data_collected = pyqtSignal(dict)  # collected sentiment data
    finished = pyqtSignal(dict)  # final sentiment summary
    error = pyqtSignal(str)  # error message
    
    def __init__(self, source_type: str, keywords: list, parent=None):
        """
        Args:
            source_type: Type of source ('news', 'twitter', 'reddit')
            keywords: List of keywords to search for
            parent: Parent QObject
        """
        super().__init__(parent)
        self.source_type = source_type
        self.keywords = keywords
        self._running = True
    
    def run(self):
        """Run sentiment collection in background"""
        try:
            self.progress.emit(0, f"Starting {self.source_type} collection...")
            
            # Import source-specific modules
            if self.source_type == 'news':
                self._collect_news()
            elif self.source_type == 'twitter':
                self._collect_twitter()
            elif self.source_type == 'reddit':
                self._collect_reddit()
            
            self.progress.emit(100, f"{self.source_type} collection completed")
            
        except Exception as e:
            logger.error(f"Sentiment collection error ({self.source_type}): {e}")
            self.error.emit(str(e))
    
    def _collect_news(self):
        """Collect news data"""
        try:
            from bs4 import BeautifulSoup
            import requests
            
            self.progress.emit(10, "Fetching news articles...")
            
            # Mock implementation - replace with real API
            # This should use actual news APIs
            sample_articles = [
                {
                    'title': 'Bitcoin reaches new high',
                    'sentiment': 0.8,
                    'source': 'News',
                    'timestamp': datetime.now()
                }
            ]
            
            for i, article in enumerate(sample_articles):
                if not self._running:
                    break
                    
                progress = 10 + int((i / len(sample_articles)) * 80)
                self.progress.emit(progress, f"Processing article {i+1}/{len(sample_articles)}")
                self.data_collected.emit(article)
                
            self.finished.emit({'count': len(sample_articles), 'source': 'news'})
            
        except Exception as e:
            raise Exception(f"News collection failed: {e}")
    
    def _collect_twitter(self):
        """Collect Twitter data"""
        try:
            self.progress.emit(10, "Connecting to Twitter API...")
            
            # Mock implementation - replace with actual Twitter API
            sample_tweets = [
                {
                    'text': 'Bitcoin is going up!',
                    'sentiment': 0.7,
                    'source': 'Twitter',
                    'timestamp': datetime.now()
                }
            ]
            
            for i, tweet in enumerate(sample_tweets):
                if not self._running:
                    break
                    
                progress = 10 + int((i / len(sample_tweets)) * 80)
                self.progress.emit(progress, f"Processing tweet {i+1}/{len(sample_tweets)}")
                self.data_collected.emit(tweet)
                
            self.finished.emit({'count': len(sample_tweets), 'source': 'twitter'})
            
        except Exception as e:
            raise Exception(f"Twitter collection failed: {e}")
    
    def _collect_reddit(self):
        """Collect Reddit data"""
        try:
            self.progress.emit(10, "Connecting to Reddit API...")
            
            # Mock implementation - replace with actual Reddit API  
            sample_posts = [
                {
                    'title': 'Discussion on crypto trends',
                    'sentiment': 0.5,
                    'source': 'Reddit',
                    'timestamp': datetime.now()
                }
            ]
            
            for i, post in enumerate(sample_posts):
                if not self._running:
                    break
                    
                progress = 10 + int((i / len(sample_posts)) * 80)
                self.progress.emit(progress, f"Processing post {i+1}/{len(sample_posts)}")
                self.data_collected.emit(post)
                
            self.finished.emit({'count': len(sample_posts), 'source': 'reddit'})
            
        except Exception as e:
            raise Exception(f"Reddit collection failed: {e}")
    
    def stop(self):
        """Stop the collection thread"""
        self._running = False


class SentimentWidget(QWidget):
    """
    Sentiment Analysis UI Widget
    
    Provides user interface for multi-source sentiment analysis
    """
    
    # Signal definitions
    signal_log = pyqtSignal(str)
    signal_sentiment_update = pyqtSignal(dict)
    signal_new_data = pyqtSignal(dict)
    
    def __init__(self, parent=None):
        """Initialize Sentiment Widget"""
        super().__init__(parent)
        
        # Load UI
        ui_path = Path(__file__).parent / "sentiment.ui"
        try:
            uic.loadUi(str(ui_path), self)
            logger.info("Sentiment UI loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load UI: {e}")
            raise
        
        # Initialize logic
        self.logic = SentimentLogic()
        
        # Collection threads
        self.news_thread = None
        self.twitter_thread = None
        self.reddit_thread = None
        
        # Chart layouts (for matplotlib integration)
        self.history_chart_layout = None
        self.pie_chart_layout = None
        
        # Connect signals
        self.connect_signals()
        
        # Initialize UI state
        self.initialize_ui()
        
        # Start update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(1000)  # Update every second
    
    def connect_signals(self):
        """Connect all Signal/Slot connections"""
        # Button signals
        self.btn_start_news.clicked.connect(self.on_start_news)
        self.btn_start_twitter.clicked.connect(self.on_start_twitter)
        self.btn_start_reddit.clicked.connect(self.on_start_reddit)
        self.btn_stop_all.clicked.connect(self.on_stop_all)
        
        # Help button
        if hasattr(self, 'btn_help'):
            self.btn_help.clicked.connect(self.on_show_help)
        
        # Filter signals
        self.check_filter_news.stateChanged.connect(self.on_filter_changed)
        self.check_filter_twitter.stateChanged.connect(self.on_filter_changed)
        self.check_filter_reddit.stateChanged.connect(self.on_filter_changed)
        
        # Settings signals
        self.slider_update_interval.valueChanged.connect(self.on_interval_changed)
        
        # Custom signals
        self.signal_log.connect(self.append_log)
        self.signal_sentiment_update.connect(self.update_sentiment_display)
        self.signal_new_data.connect(self.add_data_to_table)
        
        # Logic signals
        self.logic.signal_news_data.connect(self.on_new_news_data)
        self.logic.signal_twitter_data.connect(self.on_new_twitter_data)
        self.logic.signal_reddit_data.connect(self.on_new_reddit_data)
        self.logic.signal_sentiment_updated.connect(self.on_sentiment_updated)
        self.logic.signal_error.connect(self.on_logic_error)
        
        logger.info("Signals connected")
    
    def initialize_ui(self):
        """Initialize UI state"""
        # Initialize table
        self.table_sentiment.setColumnWidth(0, 150)  # Time
        self.table_sentiment.setColumnWidth(1, 100)  # Source
        self.table_sentiment.setColumnWidth(2, 80)   # Score
        self.table_sentiment.setColumnWidth(3, 200)  # Keywords
        self.table_sentiment.setColumnWidth(4, 400)  # Headline/Text
        
        # Initialize buttons
        self.btn_stop_all.setEnabled(False)
        
        # Initialize charts
        self.initialize_charts()
        
        self.signal_log.emit("✅ Sentiment Analysis module initialized")
    
    def initialize_charts(self):
        """Initialize matplotlib charts with proper size and antialiasing"""
        try:
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
            from matplotlib.figure import Figure
            from PyQt5.QtGui import QPainter
            
            # History chart - 1000x600px minimum as per rules
            # Using figsize in inches (1000px / 100dpi = 10in, 600px / 100dpi = 6in)
            self.history_figure = Figure(figsize=(10, 6), dpi=100)
            self.history_canvas = FigureCanvas(self.history_figure)
            
            # Enable antialiasing as per rules
            self.history_canvas.setRenderHint(QPainter.Antialiasing)
            
            self.history_chart_layout = QVBoxLayout(self.widget_history_chart)
            self.history_chart_layout.addWidget(self.history_canvas)
            self.history_chart_layout.setContentsMargins(0, 0, 0, 0)
            
            self.history_ax = self.history_figure.add_subplot(111)
            self.history_ax.set_title("Sentiment Timeline (시간별 감성 점수)", fontsize=12, fontweight='bold')
            self.history_ax.set_xlabel("Time", fontsize=10)
            self.history_ax.set_ylabel("Sentiment Score", fontsize=10)
            self.history_ax.grid(True, alpha=0.3)
            self.history_ax.axhline(y=0, color='gray', linestyle='--', linewidth=1)
            
            # Pie chart - minimum 800x600 as per rules
            self.pie_figure = Figure(figsize=(8, 6), dpi=100)
            self.pie_canvas = FigureCanvas(self.pie_figure)
            
            # Enable antialiasing as per rules
            self.pie_canvas.setRenderHint(QPainter.Antialiasing)
            
            self.pie_chart_layout = QVBoxLayout(self.widget_pie_chart)
            self.pie_chart_layout.addWidget(self.pie_canvas)
            self.pie_chart_layout.setContentsMargins(0, 0, 0, 0)
            
            self.pie_ax = self.pie_figure.add_subplot(111)
            self.pie_ax.set_title("Sentiment Distribution (긍정/중립/부정)", fontsize=12, fontweight='bold')
            
            logger.info("Charts initialized with antialiasing (800x600px minimum)")
            
        except ImportError:
            logger.warning("matplotlib not available, charts disabled")
            self.signal_log.emit("⚠️ Charts require matplotlib package")
    
    def on_start_news(self):
        """Start news scraping with QThread"""
        try:
            if self.news_thread and self.news_thread.isRunning():
                self.signal_log.emit("⚠️ News scraping already running")
                return
            
            self.signal_log.emit("📰 Starting news scraping...")
            
            # Create and start news collection thread
            keywords = ['bitcoin', 'crypto', 'cryptocurrency']  # Default keywords
            self.news_thread = SentimentCollectionThread('news', keywords, self)
            self.news_thread.progress.connect(self.on_collection_progress)
            self.news_thread.data_collected.connect(self.on_data_collected)
            self.news_thread.finished.connect(lambda result: self.on_collection_finished('news', result))
            self.news_thread.error.connect(lambda err: self.on_collection_error('news', err))
            self.news_thread.start()
            
            self.btn_start_news.setEnabled(False)
            self.btn_stop_all.setEnabled(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start news scraping: {e}")
            self.signal_log.emit(f"❌ News scraping error: {e}")
            logger.error(f"Failed to start news scraping: {e}")
    
    def on_start_twitter(self):
        """Start Twitter scraping with QThread"""
        try:
            if self.twitter_thread and self.twitter_thread.isRunning():
                self.signal_log.emit("⚠️ Twitter scraping already running")
                return
            
            self.signal_log.emit("🐦 Starting Twitter scraping...")
            
            # Create and start Twitter collection thread
            keywords = ['bitcoin', 'crypto', 'btc']  # Default keywords
            self.twitter_thread = SentimentCollectionThread('twitter', keywords, self)
            self.twitter_thread.progress.connect(self.on_collection_progress)
            self.twitter_thread.data_collected.connect(self.on_data_collected)
            self.twitter_thread.finished.connect(lambda result: self.on_collection_finished('twitter', result))
            self.twitter_thread.error.connect(lambda err: self.on_collection_error('twitter', err))
            self.twitter_thread.start()
            
            self.btn_start_twitter.setEnabled(False)
            self.btn_stop_all.setEnabled(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start Twitter scraping: {e}")
            self.signal_log.emit(f"❌ Twitter scraping error: {e}")
            logger.error(f"Failed to start Twitter scraping: {e}")
    
    def on_start_reddit(self):
        """Start Reddit scraping with QThread"""
        try:
            if self.reddit_thread and self.reddit_thread.isRunning():
                self.signal_log.emit("⚠️ Reddit scraping already running")
                return
            
            self.signal_log.emit("🤖 Starting Reddit scraping...")
            
            # Create and start Reddit collection thread
            keywords = ['bitcoin', 'cryptocurrency', 'crypto']  # Default keywords
            self.reddit_thread = SentimentCollectionThread('reddit', keywords, self)
            self.reddit_thread.progress.connect(self.on_collection_progress)
            self.reddit_thread.data_collected.connect(self.on_data_collected)
            self.reddit_thread.finished.connect(lambda result: self.on_collection_finished('reddit', result))
            self.reddit_thread.error.connect(lambda err: self.on_collection_error('reddit', err))
            self.reddit_thread.start()
            
            self.btn_start_reddit.setEnabled(False)
            self.btn_stop_all.setEnabled(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start Reddit scraping: {e}")
            self.signal_log.emit(f"❌ Reddit scraping error: {e}")
            logger.error(f"Failed to start Reddit scraping: {e}")
    
    def on_stop_all(self):
        """Stop all scraping"""
        try:
            # Stop all collection threads
            if self.news_thread and self.news_thread.isRunning():
                self.news_thread.stop()
                self.news_thread.wait(3000)
            
            if self.twitter_thread and self.twitter_thread.isRunning():
                self.twitter_thread.stop()
                self.twitter_thread.wait(3000)
            
            if self.reddit_thread and self.reddit_thread.isRunning():
                self.reddit_thread.stop()
                self.reddit_thread.wait(3000)
            
            self.logic.stop_all_scraping()
            self.signal_log.emit("⏹ All scraping stopped")
            
            # Re-enable start buttons
            self.btn_start_news.setEnabled(True)
            self.btn_start_twitter.setEnabled(True)
            self.btn_start_reddit.setEnabled(True)
            self.btn_stop_all.setEnabled(False)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to stop scraping: {e}")
            self.signal_log.emit(f"❌ Stop error: {e}")
            logger.error(f"Failed to stop scraping: {e}")
    
    @pyqtSlot(int, str)
    def on_collection_progress(self, percentage: int, message: str):
        """Handle collection progress updates"""
        self.signal_log.emit(f"📊 {percentage}% - {message}")
    
    @pyqtSlot(dict)
    def on_data_collected(self, data: dict):
        """Handle collected data from thread"""
        # Add to table via signal
        self.signal_new_data.emit(data)
        
        # Update sentiment calculations
        if hasattr(self.logic, 'add_sentiment_data'):
            self.logic.add_sentiment_data(data)
    
    def on_collection_finished(self, source: str, result: dict):
        """Handle collection completion"""
        count = result.get('count', 0)
        self.signal_log.emit(f"✅ {source.capitalize()} collection completed: {count} items")
        
        # Re-enable start button
        if source == 'news':
            self.btn_start_news.setEnabled(True)
        elif source == 'twitter':
            self.btn_start_twitter.setEnabled(True)
        elif source == 'reddit':
            self.btn_start_reddit.setEnabled(True)
        
        # Update charts
        self.update_history_chart()
        self.update_pie_chart()
    
    def on_collection_error(self, source: str, error_message: str):
        """Handle collection error"""
        self.signal_log.emit(f"❌ {source.capitalize()} collection error: {error_message}")
        QMessageBox.warning(self, "Collection Error", f"{source.capitalize()} collection failed:\n{error_message}")
        
        # Re-enable start button
        if source == 'news':
            self.btn_start_news.setEnabled(True)
        elif source == 'twitter':
            self.btn_start_twitter.setEnabled(True)
        elif source == 'reddit':
            self.btn_start_reddit.setEnabled(True)
    
    def on_filter_changed(self):
        """Handle filter checkbox changes"""
        filters = {
            'news': self.check_filter_news.isChecked(),
            'twitter': self.check_filter_twitter.isChecked(),
            'reddit': self.check_filter_reddit.isChecked()
        }
        
        self.logic.set_filters(filters)
        self.update_table_filter()
        self.signal_log.emit(f"🔍 Filters updated: {filters}")
    
    def on_interval_changed(self, value):
        """Handle update interval slider change"""
        self.label_interval_value.setText(f"{value}s")
        self.logic.set_update_interval(value)
        self.signal_log.emit(f"⏱ Update interval set to {value} seconds")
    
    def on_new_news_data(self, data):
        """Handle new news data from logic"""
        data['source'] = 'News'
        self.signal_new_data.emit(data)
    
    def on_new_twitter_data(self, data):
        """Handle new Twitter data from logic"""
        data['source'] = 'Twitter'
        self.signal_new_data.emit(data)
    
    def on_new_reddit_data(self, data):
        """Handle new Reddit data from logic"""
        data['source'] = 'Reddit'
        self.signal_new_data.emit(data)
    
    def on_sentiment_updated(self, sentiment_data):
        """Handle sentiment update from logic"""
        self.signal_sentiment_update.emit(sentiment_data)
    
    def on_logic_error(self, error_msg):
        """Handle error from logic"""
        self.signal_log.emit(f"❌ Error: {error_msg}")
        logger.error(f"Logic error: {error_msg}")
    
    def append_log(self, message):
        """Append message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.text_log.append(f"[{timestamp}] {message}")
    
    def update_sentiment_display(self, sentiment_data: dict):
        """Update sentiment score display"""
        score = sentiment_data.get('overall_score', 0)
        
        # Update progress bar
        self.progress_sentiment.setValue(int(score))
        
        # Update color based on sentiment
        if score > 20:
            color = "#27ae60"  # Green - positive
            text = f"Positive ({score:.1f})"
        elif score < -20:
            color = "#e74c3c"  # Red - negative
            text = f"Negative ({score:.1f})"
        else:
            color = "#3498db"  # Blue - neutral
            text = f"Neutral ({score:.1f})"
        
        self.progress_sentiment.setStyleSheet(f"""
            QProgressBar {{
                border: 2px solid grey;
                border-radius: 5px;
                text-align: center;
                font-weight: bold;
                min-height: 30px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
            }}
        """)
        
        self.label_sentiment_text.setText(text)
        self.label_sentiment_text.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")
    
    def add_data_to_table(self, data: dict):
        """Add sentiment data to table"""
        # Check if filtered
        source = data.get('source', '').lower()
        if source == 'news' and not self.check_filter_news.isChecked():
            return
        if source == 'twitter' and not self.check_filter_twitter.isChecked():
            return
        if source == 'reddit' and not self.check_filter_reddit.isChecked():
            return
        
        row_count = self.table_sentiment.rowCount()
        self.table_sentiment.insertRow(0)  # Insert at top
        
        # Add data
        timestamp = data.get('time', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        score = data.get('score', 0)
        keywords = data.get('keywords', [])
        text = data.get('text', '')
        
        self.table_sentiment.setItem(0, 0, QTableWidgetItem(timestamp))
        self.table_sentiment.setItem(0, 1, QTableWidgetItem(data.get('source', '')))
        
        # Color-code score
        score_item = QTableWidgetItem(f"{score:.2f}")
        if score > 0.2:
            score_item.setBackground(QColor("#d5f4e6"))  # Light green
        elif score < -0.2:
            score_item.setBackground(QColor("#fadbd8"))  # Light red
        self.table_sentiment.setItem(0, 2, score_item)
        
        self.table_sentiment.setItem(0, 3, QTableWidgetItem(", ".join(keywords[:5])))
        self.table_sentiment.setItem(0, 4, QTableWidgetItem(text[:100] + "..." if len(text) > 100 else text))
        
        # Limit table size
        if row_count > 100:
            self.table_sentiment.removeRow(self.table_sentiment.rowCount() - 1)
    
    def update_table_filter(self):
        """Update table based on active filters"""
        for row in range(self.table_sentiment.rowCount()):
            source_item = self.table_sentiment.item(row, 1)
            if source_item:
                source = source_item.text().lower()
                show_row = False
                
                if source == 'news' and self.check_filter_news.isChecked():
                    show_row = True
                elif source == 'twitter' and self.check_filter_twitter.isChecked():
                    show_row = True
                elif source == 'reddit' and self.check_filter_reddit.isChecked():
                    show_row = True
                
                self.table_sentiment.setRowHidden(row, not show_row)
    
    def update_display(self):
        """Update display periodically"""
        # Update charts
        self.update_history_chart()
        self.update_pie_chart()
        
        # Update word cloud
        self.update_wordcloud()
    
    def update_history_chart(self):
        """Update sentiment history timeline chart"""
        try:
            if not hasattr(self, 'history_ax'):
                return
            
            history = self.logic.get_sentiment_history()
            if not history:
                return
            
            times = [h['time'] for h in history]
            scores = [h['score'] for h in history]
            
            self.history_ax.clear()
            
            # Plot line with color based on sentiment (positive=green, negative=red)
            self.history_ax.plot(times, scores, marker='o', linestyle='-', linewidth=2, 
                               color='#2ecc71', label='Sentiment Score')
            
            self.history_ax.set_title("Sentiment Timeline (시간별 감성 점수)", fontsize=12, fontweight='bold')
            self.history_ax.set_xlabel("Time", fontsize=10)
            self.history_ax.set_ylabel("Sentiment Score", fontsize=10)
            self.history_ax.grid(True, alpha=0.3)
            self.history_ax.axhline(y=0, color='gray', linestyle='--', linewidth=1, label='Neutral')
            
            # Color fill: green for positive, red for negative as per rules
            self.history_ax.fill_between(times, scores, 0, 
                                        where=[s >= 0 for s in scores],
                                        alpha=0.3, color='#27ae60', label='Positive')
            self.history_ax.fill_between(times, scores, 0,
                                        where=[s < 0 for s in scores],
                                        alpha=0.3, color='#e74c3c', label='Negative')
            
            self.history_ax.legend(loc='upper left')
            
            # Rotate x labels
            self.history_figure.autofmt_xdate()
            
            self.history_canvas.draw()
            
        except Exception as e:
            logger.error(f"Failed to update history chart: {e}")
    
    def update_pie_chart(self):
        """Update sentiment distribution pie chart (긍정/중립/부정)"""
        try:
            if not hasattr(self, 'pie_ax'):
                return
            
            distribution = self.logic.get_sentiment_distribution()
            if not distribution:
                return
            
            # Order: Positive, Neutral, Negative
            labels = ['긍정 (Positive)', '중립 (Neutral)', '부정 (Negative)']
            sizes = [
                distribution.get('positive', 0),
                distribution.get('neutral', 0),
                distribution.get('negative', 0)
            ]
            
            # Colors as per rules: positive=green, neutral=blue, negative=red
            colors = ['#27ae60', '#3498db', '#e74c3c']
            explode = (0.05, 0, 0.05)  # Explode positive and negative slightly
            
            self.pie_ax.clear()
            wedges, texts, autotexts = self.pie_ax.pie(
                sizes, 
                labels=labels, 
                colors=colors, 
                autopct='%1.1f%%',
                startangle=90,
                explode=explode,
                shadow=True
            )
            
            # Make percentage text more readable
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontsize(10)
                autotext.set_fontweight('bold')
            
            self.pie_ax.set_title("Sentiment Distribution (긍정/중립/부정)", 
                                 fontsize=12, fontweight='bold')
            self.pie_ax.axis('equal')
            
            self.pie_canvas.draw()
            
        except Exception as e:
            logger.error(f"Failed to update pie chart: {e}")
    
    def update_wordcloud(self):
        """Update word cloud display"""
        try:
            wordcloud_image = self.logic.get_wordcloud_image()
            if wordcloud_image:
                from PyQt5.QtGui import QPixmap
                pixmap = QPixmap()
                if pixmap.loadFromData(wordcloud_image):
                    self.label_wordcloud.setPixmap(pixmap.scaled(
                        self.label_wordcloud.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    ))
                    self.label_wordcloud.setText("")
        except Exception as e:
            logger.error(f"Failed to update word cloud: {e}")
    
    def closeEvent(self, event):
        """Handle widget close event"""
        self.update_timer.stop()
        
        # Stop all collection threads
        if self.news_thread and self.news_thread.isRunning():
            self.news_thread.stop()
            self.news_thread.wait(3000)
        
        if self.twitter_thread and self.twitter_thread.isRunning():
            self.twitter_thread.stop()
            self.twitter_thread.wait(3000)
        
        if self.reddit_thread and self.reddit_thread.isRunning():
            self.reddit_thread.stop()
            self.reddit_thread.wait(3000)
        
        self.logic.stop_all_scraping()
        event.accept()
    
    def on_show_help(self):
        """Show help dialog"""
        try:
            from src._server.ui.widgets.help_dialog import HelpDialog  # type: ignore
            
            help_content = """
            <h2>감성 분석</h2>
            <p>다중 소스 감성 분석으로 시장 심리를 파악합니다.</p>
            
            <h3>사용법:</h3>
            <ol>
                <li><b>소스 선택:</b> News, Twitter, Reddit 중 원하는 소스 시작</li>
                <li><b>데이터 수집:</b> 자동으로 실시간 데이터 수집 시작</li>
                <li><b>감성 확인:</b> 테이블과 차트에서 감성 확인</li>
                <li><b>필터링:</b> 체크박스로 특정 소스만 필터링</li>
                <li><b>업데이트 간격:</b> 슬라이더로 조정 (초 단위)</li>
            </ol>
            
            <h3>감성 점수 해석:</h3>
            <ul>
                <li><b>+1.0 ~ +0.3:</b> 긍정 (상승 전망)</li>
                <li><b>+0.3 ~ -0.3:</b> 중립 (관망)</li>
                <li><b>-0.3 ~ -1.0:</b> 부정 (하락 전망)</li>
            </ul>
            
            <h3>신규 기능:</h3>
            <ul>
                <li><b>다중 언어:</b> 한국어(KoBERT), 영어(FinBERT) 지원</li>
                <li><b>토픽 모델링:</b> BERTopic으로 주요 토픽 자동 추출</li>
                <li><b>상관 분석:</b> Granger Causality로 인과관계 검정</li>
                <li><b>영향력 점수:</b> 팔로워/리트윗 기반 가중치</li>
            </ul>
            
            <h3>토픽 모델링:</h3>
            <ul>
                <li>자동으로 5-10개 주요 토픽 추출</li>
                <li>각 토픽의 키워드 표시</li>
                <li>시간별 토픽 진화 추적</li>
            </ul>
            
            <h3>상관 분석:</h3>
            <ul>
                <li><b>Granger Test:</b> 감성이 가격 변동에 선행하는지 검정</li>
                <li><b>Lead-Lag:</b> 최적 시차 탐지 (몇 시간 선행?)</li>
                <li><b>동적 상관:</b> 시간에 따른 상관관계 변화</li>
            </ul>
            
            <h3>영향력 점수:</h3>
            <ul>
                <li>팔로워 수 기반 가중치 (0-1)</li>
                <li>리트윗 전파 계수 (Virality)</li>
                <li>검증 계정 부스트 (×1.5)</li>
                <li>가중 감성 = 일반 감성과 다를 수 있음</li>
            </ul>
            
            <h3>주의사항:</h3>
            <ul>
                <li>API 키 필요 (Twitter API, Reddit API)</li>
                <li>Rate limit 주의 (과도한 요청 금지)</li>
                <li>가짜 뉴스 필터링 확인</li>
                <li>다른 지표와 종합 판단 권장</li>
            </ul>
            """
            
            dialog = HelpDialog("감성 분석", help_content, self)
            dialog.exec_()
            
        except Exception as e:
            logger.error(f"Failed to show help: {e}")
            QMessageBox.information(
                self,
                "도움말",
                "감성 분석 기능에 대한 도움말입니다.\n\n"
                "1. 소스 선택 (News, Twitter, Reddit)\n"
                "2. 데이터 수집 시작\n"
                "3. 감성 점수 확인\n"
                "4. 토픽 및 상관관계 분석\n\n"
                "자세한 내용은 README.md를 참조하세요."
            )
