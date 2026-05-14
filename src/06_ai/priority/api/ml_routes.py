#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML 모델 API 엔드포인트

FastAPI 라우터로 ML 모델 설정 및 예측 API를 제공합니다.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ml", tags=["ml"])


# ── 요청/응답 스키마 ─────────────────────────────────────────────────────────

class MLSettingsRequest(BaseModel):
    """ML 모델 설정 저장 요청"""

    gap_model_type: str = Field(default="lightgbm")
    gap_model_enabled: bool = True

    adaptive_tf_enabled: bool = False
    adaptive_tf_method: str = Field(default="symbol_based")

    anomaly_model_type: str = Field(default="isolation_forest")
    anomaly_threshold: float = Field(default=0.95, ge=0.01, le=1.0)
    anomaly_enabled: bool = True

    drift_monitor_type: str = Field(default="evidently")
    drift_check_interval: int = Field(default=3600, ge=1)
    drift_enabled: bool = True

    @field_validator("gap_model_type")
    @classmethod
    def validate_gap_model(cls, v: str) -> str:
        allowed = {"xgboost", "lightgbm", "catboost", "prophet"}
        if v not in allowed:
            raise ValueError(f"gap_model_type은 {allowed} 중 하나여야 합니다.")
        return v

    @field_validator("adaptive_tf_method")
    @classmethod
    def validate_adaptive_method(cls, v: str) -> str:
        allowed = {"symbol_based", "volatility_based", "hybrid"}
        if v not in allowed:
            raise ValueError(f"adaptive_tf_method는 {allowed} 중 하나여야 합니다.")
        return v

    @field_validator("anomaly_model_type")
    @classmethod
    def validate_anomaly_model(cls, v: str) -> str:
        allowed = {"autoencoder", "isolation_forest", "one_class_svm"}
        if v not in allowed:
            raise ValueError(f"anomaly_model_type은 {allowed} 중 하나여야 합니다.")
        return v

    @field_validator("drift_monitor_type")
    @classmethod
    def validate_drift_monitor(cls, v: str) -> str:
        allowed = {"alibi_detect", "evidently"}
        if v not in allowed:
            raise ValueError(f"drift_monitor_type은 {allowed} 중 하나여야 합니다.")
        return v


class GapPredictionResponse(BaseModel):
    """Gap 예측 응답"""
    symbol: str
    exchange: str
    prediction: Optional[float] = None
    model_type: str
    predicted_at: str
    error: Optional[str] = None


class AnomalyDetectionResponse(BaseModel):
    """이상치 감지 응답"""
    symbol: str
    exchange: str
    is_anomaly: Optional[bool] = None
    detected_at: str
    error: Optional[str] = None


# ── 엔드포인트 ───────────────────────────────────────────────────────────────

@router.get("/settings", summary="ML 모델 설정 조회")
async def get_ml_settings():
    """현재 저장된 ML 모델 설정을 반환합니다."""
    try:
        from ..config.ml_config import MLConfigManager
        mgr = MLConfigManager()
        config = mgr.load()
        return config.to_dict()
    except Exception as exc:
        logger.error("ML 설정 조회 실패: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/settings", summary="ML 모델 설정 저장")
async def save_ml_settings(body: MLSettingsRequest):
    """ML 모델 설정을 저장합니다."""
    try:
        from ..config.ml_config import MLConfig, MLConfigManager
        config = MLConfig.from_dict(body.model_dump())
        mgr = MLConfigManager()
        mgr.save(config)
        return {"message": "ML 설정이 저장되었습니다.", "gap_model_type": config.gap_model_type}
    except Exception as exc:
        logger.error("ML 설정 저장 실패: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/predict/gap/{symbol}",
    response_model=GapPredictionResponse,
    summary="Gap 예측 실행",
)
async def predict_gap(
    symbol: str,
    exchange: str = Query(default="upbit"),
):
    """특정 심볼에 대한 Gap 예측을 실행합니다."""
    try:
        from ..config.ml_config import MLConfigManager
        from ..services.ml_service import MLService

        mgr = MLConfigManager()
        config = mgr.load()
        service = MLService(settings=config)
        await service.setup_gap_predictor()
        result = await service.predict_gap(symbol, exchange)
        return GapPredictionResponse(
            symbol=result.get("symbol", symbol),
            exchange=exchange,
            prediction=result.get("prediction"),
            model_type=result.get("model_type", config.gap_model_type),
            predicted_at=result.get("predicted_at", ""),
            error=result.get("error"),
        )
    except Exception as exc:
        logger.error("Gap 예측 실패 (%s): %s", symbol, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/detect/anomaly/{symbol}",
    response_model=AnomalyDetectionResponse,
    summary="이상치 감지 실행",
)
async def detect_anomaly(
    symbol: str,
    exchange: str = Query(default="upbit"),
):
    """특정 심볼에 대한 이상치 감지를 실행합니다."""
    try:
        from ..config.ml_config import MLConfigManager
        from ..services.ml_service import MLService
        from datetime import datetime

        mgr = MLConfigManager()
        config = mgr.load()
        service = MLService(settings=config)
        await service.setup_anomaly_detector()
        result = await service.detect_anomaly(symbol, exchange)
        return AnomalyDetectionResponse(
            symbol=result.get("symbol", symbol),
            exchange=exchange,
            is_anomaly=result.get("is_anomaly"),
            detected_at=result.get("detected_at", datetime.now().isoformat()),
            error=result.get("error"),
        )
    except Exception as exc:
        logger.error("이상치 감지 실패 (%s): %s", symbol, exc)
        raise HTTPException(status_code=500, detail=str(exc))
