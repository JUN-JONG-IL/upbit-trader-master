#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DataPreprocessor - Data Preprocessing Pipeline

Provides standardised data cleaning, normalisation, train/val/test
splitting, and sequence padding utilities shared across all AI/ML models.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

try:
    from sklearn.preprocessing import MinMaxScaler, StandardScaler, RobustScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


class DataPreprocessor:
    """
    Standardised preprocessing pipeline for trading data.

    Handles:
    - Missing-value imputation (forward-fill, zero-fill)
    - Outlier clipping (IQR-based)
    - Feature scaling (standard, minmax, robust)
    - Train / validation / test splitting (time-aware)
    - Sequence padding / truncation

    The scaler is fitted on the training split only and reused for
    validation and test transforms to prevent data leakage.

    Example::

        prep = DataPreprocessor(scaler_type="standard")
        X_train, X_val, X_test, y_train, y_val, y_test = \\
            prep.split_and_scale(features, targets)
    """

    SCALER_TYPES = ("standard", "minmax", "robust", "none")

    def __init__(
        self,
        scaler_type: str = "standard",
        train_ratio: float = 0.7,
        val_ratio: float = 0.15,
        clip_outliers: bool = True,
        outlier_iqr_factor: float = 3.0,
    ):
        """
        Args:
            scaler_type: Scaling method (``"standard"`` | ``"minmax"`` |
                ``"robust"`` | ``"none"``).
            train_ratio: Fraction of data used for training.
            val_ratio: Fraction used for validation (remainder is test).
            clip_outliers: If True, clip outliers before scaling.
            outlier_iqr_factor: IQR multiplier for outlier clipping.
        """
        if scaler_type not in self.SCALER_TYPES:
            raise ValueError(
                f"Unknown scaler '{scaler_type}'. Choose from {self.SCALER_TYPES}."
            )

        self.scaler_type = scaler_type
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.clip_outliers = clip_outliers
        self.outlier_iqr_factor = outlier_iqr_factor

        self._scaler: Optional[Any] = None
        self._is_fitted = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def split_and_scale(
        self,
        features: np.ndarray,
        targets: Optional[np.ndarray] = None,
    ) -> Tuple:
        """
        Split data chronologically and fit/apply the scaler.

        Args:
            features: (N, n_features) or (N, seq_len, n_features) array.
            targets: (N,) target array (optional).

        Returns:
            If targets is provided:
                (X_train, X_val, X_test, y_train, y_val, y_test)
            Otherwise:
                (X_train, X_val, X_test)
        """
        n = len(features)
        train_end = int(n * self.train_ratio)
        val_end = train_end + int(n * self.val_ratio)

        X_train = features[:train_end]
        X_val = features[train_end:val_end]
        X_test = features[val_end:]

        X_train = self.fit_transform(X_train)
        X_val = self.transform(X_val)
        X_test = self.transform(X_test)

        if targets is not None:
            y_train = np.asarray(targets[:train_end])
            y_val = np.asarray(targets[train_end:val_end])
            y_test = np.asarray(targets[val_end:])
            return X_train, X_val, X_test, y_train, y_val, y_test

        return X_train, X_val, X_test

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        """Fit scaler on X and return scaled version."""
        X = self._clean(X)
        if self.clip_outliers:
            X = self._clip_outliers(X)
        if self.scaler_type != "none":
            X = self._fit_scaler(X)
        return X

    def transform(self, X: np.ndarray) -> np.ndarray:
        """Apply previously fitted scaler to X."""
        X = self._clean(X)
        if self.clip_outliers:
            X = self._clip_outliers(X)
        if self.scaler_type != "none" and self._is_fitted and self._scaler is not None:
            original_shape = X.shape
            X_flat = X.reshape(-1, original_shape[-1])
            X_flat = self._scaler.transform(X_flat)
            X = X_flat.reshape(original_shape)
        return X

    def inverse_transform(self, X: np.ndarray) -> np.ndarray:
        """Reverse scaling transformation."""
        if self._scaler is None:
            return X
        original_shape = X.shape
        X_flat = X.reshape(-1, original_shape[-1])
        X_flat = self._scaler.inverse_transform(X_flat)
        return X_flat.reshape(original_shape)

    # ------------------------------------------------------------------
    # Cleaning utilities
    # ------------------------------------------------------------------

    @staticmethod
    def fill_missing(
        data: np.ndarray,
        method: str = "forward",
        fill_value: float = 0.0,
    ) -> np.ndarray:
        """
        Fill missing values (NaN) in a 2-D array.

        Args:
            data: Input array (N, features).
            method: ``"forward"`` | ``"backward"`` | ``"zero"`` | ``"mean"``.
            fill_value: Static fill value (used when method == ``"zero"``).

        Returns:
            Array with NaN values replaced.
        """
        data = data.copy().astype(np.float32)
        if method == "forward":
            for col in range(data.shape[1] if data.ndim > 1 else 1):
                col_data = data[:, col] if data.ndim > 1 else data
                mask = np.isnan(col_data)
                idx = np.where(~mask, np.arange(len(col_data)), 0)
                np.maximum.accumulate(idx, out=idx)
                if data.ndim > 1:
                    data[:, col] = col_data[idx]
                else:
                    data = col_data[idx]
        elif method == "backward":
            data = DataPreprocessor.fill_missing(data[::-1], method="forward")[::-1]
        elif method == "mean":
            col_means = np.nanmean(data, axis=0)
            for col in range(data.shape[1] if data.ndim > 1 else 1):
                if data.ndim > 1:
                    mask = np.isnan(data[:, col])
                    data[mask, col] = col_means[col]
                else:
                    data[np.isnan(data)] = col_means
        else:  # zero / static
            data = np.nan_to_num(data, nan=fill_value)
        return data

    @staticmethod
    def remove_duplicates(
        data: np.ndarray, timestamps: Optional[np.ndarray] = None
    ) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """Remove duplicate rows (identified by identical timestamps)."""
        if timestamps is None:
            _, idx = np.unique(data, axis=0, return_index=True)
            idx = np.sort(idx)
            return data[idx], None
        _, idx = np.unique(timestamps, return_index=True)
        idx = np.sort(idx)
        return data[idx], timestamps[idx]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean(X: np.ndarray) -> np.ndarray:
        """Replace NaN/Inf with 0."""
        return np.nan_to_num(
            np.asarray(X, dtype=np.float32),
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        )

    def _clip_outliers(self, X: np.ndarray) -> np.ndarray:
        """IQR-based outlier clipping (applied per feature)."""
        original_shape = X.shape
        X_2d = X.reshape(-1, original_shape[-1])
        q1 = np.percentile(X_2d, 25, axis=0)
        q3 = np.percentile(X_2d, 75, axis=0)
        iqr = q3 - q1
        lower = q1 - self.outlier_iqr_factor * iqr
        upper = q3 + self.outlier_iqr_factor * iqr
        X_2d = np.clip(X_2d, lower, upper)
        return X_2d.reshape(original_shape)

    def _fit_scaler(self, X: np.ndarray) -> np.ndarray:
        """Fit a new scaler and transform X."""
        original_shape = X.shape
        X_flat = X.reshape(-1, original_shape[-1])

        if SKLEARN_AVAILABLE:
            if self.scaler_type == "standard":
                self._scaler = StandardScaler()
            elif self.scaler_type == "minmax":
                self._scaler = MinMaxScaler()
            elif self.scaler_type == "robust":
                self._scaler = RobustScaler()
            X_flat = self._scaler.fit_transform(X_flat)
        else:
            # Fallback: manual z-score
            self._mean = X_flat.mean(axis=0)
            self._std = X_flat.std(axis=0) + 1e-8
            X_flat = (X_flat - self._mean) / self._std
            self._scaler = _NumpyStandardScaler(self._mean, self._std)

        self._is_fitted = True
        return X_flat.reshape(original_shape)


class _NumpyStandardScaler:
    """Minimal sklearn-compatible scaler using only numpy."""

    def __init__(self, mean: np.ndarray, std: np.ndarray):
        self.mean_ = mean
        self.scale_ = std

    def transform(self, X: np.ndarray) -> np.ndarray:
        return (X - self.mean_) / self.scale_

    def inverse_transform(self, X: np.ndarray) -> np.ndarray:
        return X * self.scale_ + self.mean_
