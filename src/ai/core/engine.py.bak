#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AIEngineManager - Main Orchestrator

Coordinates all AI models including prediction, sentiment analysis, and
pattern recognition. Manages model lifecycle and provides integration
with Redis (caching), MongoDB (metadata), and Prometheus (metrics).
"""

import asyncio
import logging
import os
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Optional dependency guards
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

try:
    import motor.motor_asyncio as motor
    MOTOR_AVAILABLE = True
except ImportError:
    MOTOR_AVAILABLE = False

try:
    from prometheus_client import Counter, Histogram, Gauge, Info
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


def _get_default_redis_url() -> str:
    """config.yaml 기반 Redis URL 반환 (fallback: 포트 58530, password=dummy)"""
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        return redis_url
    try:
        import importlib.util as _ilu
        import pathlib as _pl
        _factory_path = _pl.Path(__file__).resolve().parents[2] / "01_core" / "database" / "redis_factory.py"
        _spec = _ilu.spec_from_file_location("_redis_factory_ai", str(_factory_path))
        _factory_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_factory_mod)  # type: ignore[union-attr]
        return _factory_mod.get_redis_url()
    except Exception:
        return "redis://:dummy@127.0.0.1:58530/0"


class AIEngineManager:
    """
    Main AI engine orchestrator.

    Coordinates prediction, sentiment, and pattern-recognition models.
    All external I/O (Redis, MongoDB) is optional and degrades gracefully
    when the corresponding service is unavailable.

    Prometheus metrics are registered once per process; subsequent
    instantiations reuse the already-registered objects.

    Example::

        engine = AIEngineManager(
            redis_uri="redis://:dummy@127.0.0.1:58530",
            mongo_uri="mongodb://localhost:27017",
        )
        await engine.start()
        predictions = await engine.get_predictions(["BTC/KRW"])
        await engine.stop()
    """

    # Class-level Prometheus metric objects (shared across instances)
    _metrics: Dict[str, Any] = {}
    _metrics_lock: threading.Lock = threading.Lock()

    def __init__(
        self,
        redis_uri: Optional[str] = None,
        mongo_uri: str = "mongodb://localhost:27017",
        cache_ttl: int = 60,
        prediction_threshold: float = 0.55,
    ):
        """
        Args:
            redis_uri: Redis connection URI for caching predictions.
                       Defaults to config.yaml REDIS settings.
            mongo_uri: MongoDB connection URI for metadata storage.
            cache_ttl: Prediction cache time-to-live in seconds.
            prediction_threshold: Minimum confidence to emit a signal.
        """
        self.redis_uri = redis_uri if redis_uri is not None else _get_default_redis_url()
        self.mongo_uri = mongo_uri
        self.cache_ttl = cache_ttl
        self.prediction_threshold = prediction_threshold

        self._redis: Optional[Any] = None
        self._mongo_client: Optional[Any] = None
        self._db: Optional[Any] = None

        self._running = False
        self._models: Dict[str, Any] = {}

        self._init_prometheus_metrics()
        logger.info("AIEngineManager initialised")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the engine and connect to backing services."""
        self._running = True
        await self._connect_redis()
        await self._connect_mongo()
        logger.info("AIEngineManager started")

    async def stop(self) -> None:
        """Gracefully shut down the engine."""
        self._running = False
        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass
        if self._mongo_client:
            try:
                self._mongo_client.close()
            except Exception:
                pass
        logger.info("AIEngineManager stopped")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_predictions(
        self, symbols: List[str], timeframe: str = "1h"
    ) -> Dict[str, Dict[str, Any]]:
        """
        Return latest price predictions for a list of symbols.

        Results are served from the Redis cache when available.
        Falls back to the registered prediction model on a cache miss.

        Args:
            symbols: List of trading pairs, e.g. ``["BTC/KRW", "ETH/KRW"]``.
            timeframe: Candle timeframe.

        Returns:
            Mapping of symbol → prediction dict.
        """
        results: Dict[str, Dict[str, Any]] = {}
        for symbol in symbols:
            cached = await self._get_cached_prediction(symbol, timeframe)
            if cached:
                results[symbol] = cached
                continue

            prediction = await self._run_prediction(symbol, timeframe)
            results[symbol] = prediction
            await self._cache_prediction(symbol, timeframe, prediction)

        return results

    async def get_sentiment(self, symbol: str) -> Dict[str, Any]:
        """
        Return the latest sentiment score for a symbol.

        Args:
            symbol: Trading pair.

        Returns:
            Sentiment dict with ``sentiment_score`` (-1 … +1) and
            ``confidence`` (0 … 1).
        """
        cache_key = f"ai:sentiment:{symbol}"
        cached = await self._redis_get(cache_key)
        if cached:
            import json
            try:
                return json.loads(cached)
            except Exception:
                pass

        sentiment = await self._run_sentiment(symbol)
        await self._redis_set(cache_key, sentiment, ttl=self.cache_ttl * 5)
        return sentiment

    async def get_patterns(self, symbol: str) -> Dict[str, Any]:
        """
        Return detected chart patterns for a symbol.

        Args:
            symbol: Trading pair.

        Returns:
            Dict containing detected patterns and confidence scores.
        """
        cache_key = f"ai:pattern:{symbol}"
        cached = await self._redis_get(cache_key)
        if cached:
            import json
            try:
                return json.loads(cached)
            except Exception:
                pass

        patterns = await self._run_pattern_detection(symbol)
        await self._redis_set(cache_key, patterns, ttl=self.cache_ttl * 2)
        return patterns

    async def load_model(self, model_type: str, model: Any) -> None:
        """
        Register a model with the engine.

        Args:
            model_type: Identifier such as ``"lstm"`` or ``"sentiment"``.
            model: Callable model object supporting ``predict()``.
        """
        self._models[model_type] = model
        logger.info("Model loaded: %s", model_type)

    async def store_prediction_result(
        self,
        symbol: str,
        model_type: str,
        prediction_value: float,
        confidence: float,
        actual_value: Optional[float] = None,
    ) -> None:
        """
        Persist a prediction record to MongoDB for later evaluation.

        Args:
            symbol: Trading pair.
            model_type: Model identifier.
            prediction_value: Predicted price/direction value.
            confidence: Prediction confidence (0 … 1).
            actual_value: Observed value (filled in later if unknown).
        """
        if self._db is None:
            return
        doc = {
            "timestamp": datetime.utcnow(),
            "symbol": symbol,
            "model_type": model_type,
            "prediction_value": prediction_value,
            "confidence": confidence,
            "actual_value": actual_value,
            "error": (
                abs(prediction_value - actual_value)
                if actual_value is not None
                else None
            ),
        }
        try:
            await self._db["ai_predictions"].insert_one(doc)
        except Exception as exc:
            logger.warning("Failed to store prediction: %s", exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _connect_redis(self) -> None:
        if not REDIS_AVAILABLE:
            logger.warning("aioredis not available; Redis caching disabled")
            return
        try:
            self._redis = aioredis.from_url(
                self.redis_uri, encoding="utf-8", decode_responses=True
            )
            await self._redis.ping()
            logger.info("Redis connected: %s", self.redis_uri)
        except Exception as exc:
            logger.warning("Redis connection failed (%s); caching disabled", exc)
            self._redis = None

    async def _connect_mongo(self) -> None:
        if not MOTOR_AVAILABLE:
            logger.warning("motor not available; MongoDB storage disabled")
            return
        try:
            self._mongo_client = motor.AsyncIOMotorClient(self.mongo_uri)
            self._db = self._mongo_client["upbit_trader"]
            await self._mongo_client.admin.command("ping")
            logger.info("MongoDB connected: %s", self.mongo_uri)
        except Exception as exc:
            logger.warning("MongoDB connection failed (%s); storage disabled", exc)
            self._mongo_client = None
            self._db = None

    async def _redis_get(self, key: str) -> Optional[str]:
        if not self._redis:
            return None
        try:
            return await self._redis.get(key)
        except Exception:
            return None

    async def _redis_set(self, key: str, value: Any, ttl: int = 60) -> None:
        if not self._redis:
            return
        import json
        try:
            await self._redis.set(key, json.dumps(value), ex=ttl)
        except Exception:
            pass

    async def _get_cached_prediction(
        self, symbol: str, timeframe: str
    ) -> Optional[Dict[str, Any]]:
        key = f"ai:prediction:{symbol}:{timeframe}"
        raw = await self._redis_get(key)
        if raw is None:
            return None
        import json
        try:
            return json.loads(raw)
        except Exception:
            return None

    async def _cache_prediction(
        self, symbol: str, timeframe: str, prediction: Dict[str, Any]
    ) -> None:
        key = f"ai:prediction:{symbol}:{timeframe}"
        await self._redis_set(key, prediction, ttl=self.cache_ttl)

    async def _run_prediction(
        self, symbol: str, timeframe: str
    ) -> Dict[str, Any]:
        """Run the registered prediction model or return a stub."""
        model = self._models.get("prediction") or self._models.get("lstm")
        if model and hasattr(model, "predict"):
            try:
                return await model.predict(symbol=symbol, timeframe=timeframe)
            except Exception as exc:
                logger.warning("Prediction model failed (%s); returning stub", exc)

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "predictions": [],
            "confidence_lower": [],
            "confidence_upper": [],
            "model_version": "stub",
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _run_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Run the registered sentiment model or return a stub."""
        model = self._models.get("sentiment")
        if model and hasattr(model, "analyze"):
            try:
                return await model.analyze(symbol)
            except Exception as exc:
                logger.warning("Sentiment model failed (%s); returning stub", exc)

        return {
            "symbol": symbol,
            "sentiment_score": 0.0,
            "confidence": 0.0,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _run_pattern_detection(self, symbol: str) -> Dict[str, Any]:
        """Run the registered pattern detector or return a stub."""
        model = self._models.get("pattern")
        if model and hasattr(model, "detect"):
            try:
                return await model.detect(symbol)
            except Exception as exc:
                logger.warning("Pattern detector failed (%s); returning stub", exc)

        return {
            "symbol": symbol,
            "patterns": [],
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _init_prometheus_metrics(self) -> None:
        """Register Prometheus metrics (idempotent and thread-safe)."""
        if not PROMETHEUS_AVAILABLE:
            return
        with AIEngineManager._metrics_lock:
            if AIEngineManager._metrics:
                return
            try:
                AIEngineManager._metrics = {
                    "prediction_latency": Histogram(
                        "ai_prediction_latency_seconds",
                        "Prediction latency",
                        ["model_type"],
                    ),
                    "prediction_accuracy": Gauge(
                        "ai_prediction_accuracy",
                        "Rolling accuracy",
                        ["symbol", "timeframe"],
                    ),
                    "sentiment_latency": Histogram(
                        "ai_sentiment_latency_seconds",
                        "Sentiment analysis latency",
                    ),
                    "sentiment_score": Gauge(
                        "ai_sentiment_score",
                        "Current sentiment score",
                        ["symbol"],
                    ),
                    "training_duration": Histogram(
                        "ai_training_duration_seconds",
                        "Training time",
                        ["model_type"],
                    ),
                }
            except Exception as exc:
                logger.debug("Prometheus metrics already registered: %s", exc)
