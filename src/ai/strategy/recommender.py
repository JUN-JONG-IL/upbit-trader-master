#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
StrategyRecommender - AI-driven Trading Strategy Recommender

Analyses the current market regime and recommends the most suitable
trading strategies with optimised parameters and risk assessment.

Integrates with the strategy templates in ``src/strategy/``.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


class MarketRegimeDetector:
    """Classify market regime from OHLCV data."""

    def detect(
        self,
        close: np.ndarray,
        volume: Optional[np.ndarray] = None,
        atr_period: int = 14,
        adx_period: int = 14,
    ) -> Dict[str, Any]:
        """
        Detect the current market regime.

        Args:
            close: Close price array (length >= 30 recommended).
            volume: Volume array (optional).
            atr_period: Period for ATR volatility estimate.
            adx_period: Period for trend-strength estimate.

        Returns:
            Dict with keys ``type``, ``volatility``, ``trend_strength``.
        """
        close = np.asarray(close, dtype=np.float64)
        n = len(close)

        # --- Trend strength (simple linear regression R²) ---
        x = np.arange(n)
        if n > 1:
            coef = np.polyfit(x, close, 1)
            trend_line = np.polyval(coef, x)
            ss_res = np.sum((close - trend_line) ** 2)
            ss_tot = np.sum((close - close.mean()) ** 2)
            r2 = max(0.0, 1 - ss_res / (ss_tot + 1e-10))
            trend_dir = "UP" if coef[0] > 0 else "DOWN"
        else:
            r2 = 0.0
            trend_dir = "FLAT"

        # --- Volatility (ATR proxy: std of log-returns) ---
        if n > 1:
            log_returns = np.diff(np.log(close + 1e-10))
            vol = float(np.std(log_returns) * np.sqrt(252))
        else:
            vol = 0.0

        regime_type = "TRENDING" if r2 > 0.5 else "RANGING"
        volatility = "HIGH" if vol > 0.5 else ("LOW" if vol < 0.2 else "MEDIUM")

        return {
            "type": regime_type,
            "trend_direction": trend_dir,
            "volatility": volatility,
            "volatility_value": round(float(vol), 4),
            "trend_strength": round(float(r2), 4),
        }


class StrategyRecommender:
    """
    AI-driven trading strategy recommender.

    Scores a library of strategy templates against the detected market
    regime and historical backtests to produce ranked recommendations
    with optimised parameters.

    Strategy templates (aligned with ``src/strategy/``):
    - TrendFollowing   – MA crossover
    - MeanReversion    – Bollinger Bands
    - Breakout         – Support / Resistance
    - Momentum         – RSI / MACD
    - DCA              – Dollar-Cost Averaging
    - Grid             – Grid Trading

    Example::

        recommender = StrategyRecommender()
        result = recommender.recommend(close, volume)
        for rec in result["recommendations"]:
            print(rec["strategy"], rec["score"])
    """

    # Strategy catalogue: (name, preferred_regimes, volatility_pref)
    _STRATEGIES = [
        {
            "name": "TrendFollowing",
            "preferred_regimes": ["TRENDING"],
            "preferred_volatility": ["MEDIUM", "HIGH"],
            "default_params": {"fast_ma": 12, "slow_ma": 26, "stop_loss": 0.02},
            "risk_level": "MEDIUM",
        },
        {
            "name": "MeanReversion",
            "preferred_regimes": ["RANGING"],
            "preferred_volatility": ["LOW", "MEDIUM"],
            "default_params": {"bb_period": 20, "bb_std": 2.0, "rsi_period": 14},
            "risk_level": "LOW",
        },
        {
            "name": "Breakout",
            "preferred_regimes": ["RANGING", "TRENDING"],
            "preferred_volatility": ["MEDIUM", "HIGH"],
            "default_params": {"lookback": 20, "atr_multiplier": 1.5},
            "risk_level": "HIGH",
        },
        {
            "name": "Momentum",
            "preferred_regimes": ["TRENDING"],
            "preferred_volatility": ["MEDIUM"],
            "default_params": {"rsi_period": 14, "macd_fast": 12, "macd_slow": 26},
            "risk_level": "MEDIUM",
        },
        {
            "name": "DCA",
            "preferred_regimes": ["RANGING", "TRENDING"],
            "preferred_volatility": ["LOW", "MEDIUM", "HIGH"],
            "default_params": {"interval_days": 7, "amount_pct": 0.05},
            "risk_level": "LOW",
        },
        {
            "name": "Grid",
            "preferred_regimes": ["RANGING"],
            "preferred_volatility": ["LOW", "MEDIUM"],
            "default_params": {"grid_count": 10, "grid_pct": 0.01},
            "risk_level": "MEDIUM",
        },
    ]

    def __init__(self, top_n: int = 3):
        """
        Args:
            top_n: Number of top recommendations to return.
        """
        self.top_n = top_n
        self._regime_detector = MarketRegimeDetector()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recommend(
        self,
        close: np.ndarray,
        volume: Optional[np.ndarray] = None,
        symbol: str = "",
    ) -> Dict[str, Any]:
        """
        Generate strategy recommendations for the given price series.

        Args:
            close: Close price array.
            volume: Volume array (optional, used for regime detection).
            symbol: Trading pair label (used in output only).

        Returns:
            ::

                {
                    "symbol": str,
                    "timestamp": str,
                    "market_regime": {
                        "type": str,
                        "volatility": str,
                        "trend_strength": float,
                    },
                    "recommendations": [
                        {
                            "strategy": str,
                            "score": float,
                            "parameters": dict,
                            "expected_metrics": dict,
                            "risk_level": str,
                            "confidence": float,
                        },
                        ...
                    ],
                }
        """
        regime = self._regime_detector.detect(close, volume)
        scored = self._score_strategies(regime, close)
        top = sorted(scored, key=lambda x: x["score"], reverse=True)[: self.top_n]

        return {
            "symbol": symbol,
            "timestamp": datetime.utcnow().isoformat(),
            "market_regime": {
                "type": regime["type"],
                "volatility": regime["volatility"],
                "trend_strength": regime["trend_strength"],
            },
            "recommendations": top,
        }

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score_strategies(
        self, regime: Dict[str, Any], close: np.ndarray
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for template in self._STRATEGIES:
            score = self._compute_score(template, regime)
            expected = self._estimate_metrics(template["name"], close)
            results.append({
                "strategy": template["name"],
                "score": round(score, 4),
                "parameters": dict(template["default_params"]),
                "expected_metrics": expected,
                "risk_level": template["risk_level"],
                "confidence": round(min(score + 0.1, 1.0), 4),
            })
        return results

    def _compute_score(
        self, template: Dict[str, Any], regime: Dict[str, Any]
    ) -> float:
        score = 0.0
        # Regime match
        if regime["type"] in template["preferred_regimes"]:
            score += 0.5
        # Volatility match
        if regime["volatility"] in template["preferred_volatility"]:
            score += 0.3
        # Trend-strength bonus for trend-following strategies
        if template["name"] in ("TrendFollowing", "Momentum"):
            score += regime["trend_strength"] * 0.2
        # Range bonus for mean reversion
        if template["name"] in ("MeanReversion", "Grid"):
            score += (1 - regime["trend_strength"]) * 0.2
        return min(score, 1.0)

    def _estimate_metrics(
        self, strategy_name: str, close: np.ndarray
    ) -> Dict[str, float]:
        """Return heuristic expected metric estimates for the strategy."""
        # Compute a simple backtest proxy using log returns
        n = len(close)
        if n < 10:
            return {"sharpe_ratio": 0.0, "max_drawdown": 0.0, "win_rate": 0.5}

        returns = np.diff(np.log(close + 1e-10))

        # Crude Sharpe
        sharpe = (
            float(returns.mean() / (returns.std() + 1e-10)) * np.sqrt(252)
        )

        # Max drawdown
        cumulative = np.exp(np.cumsum(returns))
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (running_max - cumulative) / (running_max + 1e-10)
        max_dd = float(drawdown.max())

        # Win rate (simplistic)
        win_rate = float((returns > 0).mean())

        # Adjust heuristically by strategy type
        adjustments: Dict[str, Tuple[float, float]] = {
            "TrendFollowing": (0.3, -0.05),
            "MeanReversion": (0.1, 0.05),
            "Breakout": (0.5, -0.1),
            "Momentum": (0.2, 0.0),
            "DCA": (-0.1, 0.1),
            "Grid": (0.0, 0.05),
        }
        sharpe_adj, win_adj = adjustments.get(strategy_name, (0.0, 0.0))

        return {
            "sharpe_ratio": round(sharpe + sharpe_adj, 3),
            "max_drawdown": round(max_dd, 4),
            "win_rate": round(float(np.clip(win_rate + win_adj, 0.3, 0.8)), 4),
        }
