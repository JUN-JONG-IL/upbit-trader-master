#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
HyperparameterOptimizer - Optuna-based Strategy / Model Optimisation

Provides walk-forward hyperparameter search for trading strategies and
ML models.  Uses Optuna when available; falls back to a random-search
baseline otherwise.
"""

import logging
import random
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    logger.debug("Optuna not installed; using random-search fallback.")


class HyperparameterOptimizer:
    """
    Optuna-based hyperparameter optimiser with walk-forward validation.

    Supports any objective function that accepts a parameter dict and
    returns a scalar metric (higher = better).

    Falls back to random search when Optuna is not installed.

    Example::

        def objective(params):
            # Train and evaluate strategy with params
            return sharpe_ratio

        optimizer = HyperparameterOptimizer(n_trials=50)
        result = optimizer.optimize(
            objective=objective,
            search_space={
                "fast_ma": ("int", 5, 30),
                "slow_ma": ("int", 20, 100),
                "stop_loss": ("float", 0.01, 0.05),
            },
        )
        print(result["best_params"])
    """

    def __init__(
        self,
        n_trials: int = 100,
        timeout_seconds: Optional[int] = None,
        direction: str = "maximize",
        study_name: Optional[str] = None,
    ):
        """
        Args:
            n_trials: Number of optimisation trials.
            timeout_seconds: Wall-clock budget in seconds (Optuna only).
            direction: ``"maximize"`` or ``"minimize"``.
            study_name: Optional Optuna study name (useful for persistence).
        """
        self.n_trials = n_trials
        self.timeout_seconds = timeout_seconds
        self.direction = direction
        self.study_name = study_name or f"study_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def optimize(
        self,
        objective: Callable[[Dict[str, Any]], float],
        search_space: Dict[str, Tuple],
    ) -> Dict[str, Any]:
        """
        Run hyperparameter optimisation.

        Args:
            objective: Function mapping params → scalar metric.
            search_space: Parameter specification dict where each value
                is a tuple of ``(type, *range_args)``:

                - ``("int", low, high)``
                - ``("float", low, high)``
                - ``("categorical", [choice1, choice2, ...])``

        Returns:
            ::

                {
                    "best_params": dict,
                    "best_value": float,
                    "n_trials": int,
                    "direction": str,
                    "all_trials": [...],   # brief summary
                    "timestamp": str,
                }
        """
        if OPTUNA_AVAILABLE:
            return self._optuna_search(objective, search_space)
        return self._random_search(objective, search_space)

    def walk_forward_optimize(
        self,
        objective_factory: Callable[[np.ndarray, np.ndarray], Callable],
        data: np.ndarray,
        search_space: Dict[str, Tuple],
        n_splits: int = 5,
    ) -> Dict[str, Any]:
        """
        Walk-forward hyperparameter optimisation.

        Splits *data* into *n_splits* folds and runs a separate
        optimisation on each in-sample fold, then validates on the
        next out-of-sample fold.

        Args:
            objective_factory: ``f(train_data, val_data) → objective``.
            data: Time series data array (N × features or 1-D).
            search_space: Parameter specification (see :meth:`optimize`).
            n_splits: Number of walk-forward splits.

        Returns:
            Dict with ``fold_results``, ``best_params`` (averaged),
            ``avg_val_score``.
        """
        fold_results: List[Dict[str, Any]] = []
        n = len(data)
        fold_size = n // (n_splits + 1)

        for i in range(n_splits):
            train_end = (i + 1) * fold_size
            val_end = train_end + fold_size
            train = data[:train_end]
            val = data[train_end:val_end]

            obj = objective_factory(train, val)
            result = self.optimize(obj, search_space)
            result["fold"] = i
            fold_results.append(result)
            logger.debug(
                "Walk-forward fold %d: best_value=%.4f", i, result["best_value"]
            )

        # Average best params across folds
        avg_params: Dict[str, Any] = {}
        for key in fold_results[0]["best_params"]:
            values = [f["best_params"][key] for f in fold_results]
            try:
                avg_params[key] = float(np.mean(values))
            except Exception:
                avg_params[key] = values[-1]

        avg_val_score = float(np.mean([f["best_value"] for f in fold_results]))

        return {
            "fold_results": fold_results,
            "best_params": avg_params,
            "avg_val_score": round(avg_val_score, 6),
            "n_splits": n_splits,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ------------------------------------------------------------------
    # Optuna search
    # ------------------------------------------------------------------

    def _optuna_search(
        self,
        objective: Callable[[Dict[str, Any]], float],
        search_space: Dict[str, Tuple],
    ) -> Dict[str, Any]:
        def optuna_objective(trial: "optuna.Trial") -> float:  # type: ignore[name-defined]
            params = self._sample_optuna(trial, search_space)
            try:
                return float(objective(params))
            except Exception as exc:
                logger.debug("Objective raised exception: %s", exc)
                return float("-inf") if self.direction == "maximize" else float("inf")

        study = optuna.create_study(
            direction=self.direction,
            study_name=self.study_name,
        )
        study.optimize(
            optuna_objective,
            n_trials=self.n_trials,
            timeout=self.timeout_seconds,
            show_progress_bar=False,
        )

        trial_summaries = [
            {"params": t.params, "value": t.value}
            for t in study.trials
            if t.value is not None
        ]

        return {
            "best_params": study.best_params,
            "best_value": round(study.best_value, 6),
            "n_trials": len(study.trials),
            "direction": self.direction,
            "all_trials": trial_summaries,
            "timestamp": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _sample_optuna(
        trial: Any, search_space: Dict[str, Tuple]
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        for name, spec in search_space.items():
            kind = spec[0]
            if kind == "int":
                params[name] = trial.suggest_int(name, spec[1], spec[2])
            elif kind == "float":
                params[name] = trial.suggest_float(name, spec[1], spec[2])
            elif kind == "categorical":
                params[name] = trial.suggest_categorical(name, spec[1])
            else:
                raise ValueError(f"Unknown param type '{kind}' for '{name}'")
        return params

    # ------------------------------------------------------------------
    # Random search fallback
    # ------------------------------------------------------------------

    def _random_search(
        self,
        objective: Callable[[Dict[str, Any]], float],
        search_space: Dict[str, Tuple],
    ) -> Dict[str, Any]:
        best_params: Dict[str, Any] = {}
        best_value = float("-inf") if self.direction == "maximize" else float("inf")
        all_trials: List[Dict[str, Any]] = []

        for _ in range(self.n_trials):
            params = self._sample_random(search_space)
            try:
                value = float(objective(params))
            except Exception:
                value = float("-inf")

            all_trials.append({"params": params, "value": value})

            is_better = (
                value > best_value
                if self.direction == "maximize"
                else value < best_value
            )
            if is_better:
                best_value = value
                best_params = dict(params)

        return {
            "best_params": best_params,
            "best_value": round(best_value, 6),
            "n_trials": self.n_trials,
            "direction": self.direction,
            "all_trials": all_trials,
            "timestamp": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _sample_random(search_space: Dict[str, Tuple]) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        for name, spec in search_space.items():
            kind = spec[0]
            if kind == "int":
                params[name] = random.randint(spec[1], spec[2])
            elif kind == "float":
                params[name] = random.uniform(spec[1], spec[2])
            elif kind == "categorical":
                params[name] = random.choice(spec[1])
            else:
                raise ValueError(f"Unknown param type '{kind}' for '{name}'")
        return params
