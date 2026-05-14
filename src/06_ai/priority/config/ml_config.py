#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML 모델 설정 관리 모듈

Gap 예측, Adaptive TimeFrame, 이상치 감지, Drift 모니터링 설정을 관리합니다.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "ml_config.json"
)

# ── 허용값 상수 ─────────────────────────────────────────────────────────────
GAP_MODEL_TYPES = ("xgboost", "lightgbm", "catboost", "prophet")
ADAPTIVE_TF_METHODS = ("symbol_based", "volatility_based", "hybrid")
ANOMALY_MODEL_TYPES = ("autoencoder", "isolation_forest", "one_class_svm")
DRIFT_MONITOR_TYPES = ("alibi_detect", "evidently")


@dataclass
class MLConfig:
    """ML 모델 설정 데이터 클래스"""

    # Gap 예측 모델
    gap_model_type: str = "lightgbm"
    gap_model_enabled: bool = True
    gap_model_params: Dict = field(default_factory=dict)

    # Adaptive TimeFrame
    adaptive_tf_enabled: bool = False
    adaptive_tf_method: str = "symbol_based"
    adaptive_tf_params: Dict = field(default_factory=dict)

    # 이상치 감지
    anomaly_model_type: str = "isolation_forest"
    anomaly_threshold: float = 0.95
    anomaly_enabled: bool = True

    # Drift 모니터링
    drift_monitor_type: str = "evidently"
    drift_check_interval: int = 3600
    drift_enabled: bool = True

    def __post_init__(self) -> None:
        if self.gap_model_params is None:
            self.gap_model_params = {}
        if self.adaptive_tf_params is None:
            self.adaptive_tf_params = {}
        self._validate()

    def _validate(self) -> None:
        if self.gap_model_type not in GAP_MODEL_TYPES:
            raise ValueError(f"gap_model_type must be one of {GAP_MODEL_TYPES}")
        if self.adaptive_tf_method not in ADAPTIVE_TF_METHODS:
            raise ValueError(f"adaptive_tf_method must be one of {ADAPTIVE_TF_METHODS}")
        if self.anomaly_model_type not in ANOMALY_MODEL_TYPES:
            raise ValueError(f"anomaly_model_type must be one of {ANOMALY_MODEL_TYPES}")
        if self.drift_monitor_type not in DRIFT_MONITOR_TYPES:
            raise ValueError(f"drift_monitor_type must be one of {DRIFT_MONITOR_TYPES}")
        if not (0 < self.anomaly_threshold <= 1):
            raise ValueError("anomaly_threshold must be in (0, 1]")
        if self.drift_check_interval <= 0:
            raise ValueError("drift_check_interval must be > 0")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MLConfig":
        known_fields = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


class MLConfigManager:
    """ML 설정 파일 기반 관리자"""

    def __init__(self, config_path: Optional[str] = None) -> None:
        self._path = config_path or _DEFAULT_CONFIG_PATH
        self._config: MLConfig = MLConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> MLConfig:
        """JSON 파일에서 설정을 로드합니다."""
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._config = MLConfig.from_dict(data)
                logger.info("ML 설정 로드 완료: %s", self._path)
            else:
                logger.info("ML 설정 파일 없음, 기본값 사용: %s", self._path)
        except Exception as exc:
            logger.error("ML 설정 로드 실패: %s", exc)
        return self._config

    def save(self, config: MLConfig) -> None:
        """설정을 JSON 파일에 저장합니다."""
        try:
            self._config = config
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(config.to_dict(), fh, ensure_ascii=False, indent=2)
            logger.info("ML 설정 저장 완료: %s", self._path)
        except Exception as exc:
            logger.error("ML 설정 저장 실패: %s", exc)
            raise

    @property
    def config(self) -> MLConfig:
        return self._config
