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

try:
    from PyQt5.QtWidgets import QWidget, QApplication
    from PyQt5.QtCore import pyqtSignal, pyqtSlot
    from PyQt5 import uic
    _HAS_QT = True
except Exception:
    _HAS_QT = False
    QWidget = object

from ..logic.sentiment_engine import SentimentLogic

logger = logging.getLogger(__name__)

_UI_FILE = Path(__file__).parent / "sentiment.ui"


class SentimentWidget(QWidget if _HAS_QT else object):
    """
    Widget for sentiment analysis with QThread collection.

    Provides a UI for:
    - Starting/stopping multi-source scraping (News, Twitter, Reddit)
    - Viewing real-time sentiment scores
    - Filtering by source
    - Monitoring collection progress
    """

    if _HAS_QT:
        signal_log = pyqtSignal(str)
        signal_sentiment_update = pyqtSignal(dict)
        signal_new_data = pyqtSignal(dict)

    def __init__(self, parent=None):
        if _HAS_QT:
            super().__init__(parent)
        else:
            super().__init__()

        self._logic = SentimentLogic(parent=self if _HAS_QT else None)
        self._workers = {}

        if _HAS_QT and _UI_FILE.exists():
            try:
                uic.loadUi(str(_UI_FILE), self)
                self._connect_signals()
                logger.info("SentimentWidget UI loaded from %s", _UI_FILE)
            except Exception as e:
                logger.warning("Failed to load UI file: %s", e)
        else:
            logger.info("SentimentWidget created (no Qt or UI file)")

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """Connect UI buttons to slots."""
        try:
            self.btn_start_news.clicked.connect(self.on_start_news)
        except AttributeError:
            pass
        try:
            self.btn_start_twitter.clicked.connect(self.on_start_twitter)
        except AttributeError:
            pass
        try:
            self.btn_start_reddit.clicked.connect(self.on_start_reddit)
        except AttributeError:
            pass
        try:
            self.btn_stop_all.clicked.connect(self.on_stop_all)
        except AttributeError:
            pass

    def initialize_charts(self) -> None:
        """Initialize charts with proper size and antialiasing."""
        logger.debug("Charts initialized")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def on_start_news(self) -> None:
        """Start news collection in QThread."""
        self._start_worker("news")

    def on_start_twitter(self) -> None:
        """Start Twitter collection in QThread."""
        self._start_worker("twitter")

    def on_start_reddit(self) -> None:
        """Start Reddit collection in QThread."""
        self._start_worker("reddit")

    def on_stop_all(self) -> None:
        """Stop all active workers."""
        for source, worker in list(self._workers.items()):
            try:
                worker.stop()
                worker.wait()
            except Exception as e:
                logger.warning("Error stopping %s worker: %s", source, e)
        self._workers.clear()
        self._logic.stop_all_scraping()
        if _HAS_QT:
            self.signal_log.emit("All scraping stopped.")

    @pyqtSlot(int, str) if _HAS_QT else (lambda f: f)
    def on_collection_progress(self, percentage: int, message: str) -> None:
        """Handle collection progress updates."""
        if _HAS_QT:
            self.signal_log.emit(f"[{percentage}%] {message}")
        try:
            self.progressBar.setValue(percentage)
        except AttributeError:
            pass

    @pyqtSlot(dict) if _HAS_QT else (lambda f: f)
    def on_data_collected(self, data: dict) -> None:
        """Handle individual collected data point."""
        item = data.get("data", {})
        source = data.get("source", "unknown")
        self._logic.add_sentiment_data(
            {
                "source": source,
                "score": item.get("sentiment") or 0.0,
                "text": item.get("text", item.get("title", "")),
                "timestamp": datetime.now(),
            }
        )
        if _HAS_QT:
            self.signal_new_data.emit(data)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _start_worker(self, source: str) -> None:
        """Launch a ScrapingWorker for the given source."""
        if not _HAS_QT:
            logger.info("Cannot start worker without Qt: source=%s", source)
            return
        if source in self._workers:
            try:
                if self._workers[source].isRunning():
                    logger.info("%s worker already running", source)
                    return
            except Exception:
                pass

        try:
            from ..workers.scraping_worker import ScrapingWorker

            keywords = ["bitcoin", "BTC", "crypto"]
            worker = ScrapingWorker(source=source, keywords=keywords)
            worker.data_received.connect(self.on_data_collected)
            worker.progress.connect(self.on_collection_progress)
            worker.error_occurred.connect(
                lambda msg: self.signal_log.emit(f"Error: {msg}")
            )
            self._workers[source] = worker
            worker.start()
            self.signal_log.emit(f"Started {source} scraping...")
        except Exception as e:
            logger.error("Failed to start %s worker: %s", source, e)
            if _HAS_QT:
                self.signal_log.emit(f"Failed to start {source}: {e}")
