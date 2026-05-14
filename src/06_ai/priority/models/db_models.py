#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM 모델 정의

우선순위 설정, ML 모델 설정, 심볼 점수, ML 예측 데이터를 위한 테이블 모델입니다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class User(Base):
    """사용자 테이블"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"


class PrioritySettings(Base):
    """우선순위 설정 테이블"""

    __tablename__ = "priority_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    setting_name = Column(String(100), nullable=False)

    # 우선순위 항목 활성화 여부
    volume_enabled = Column(Boolean, default=False, nullable=False)
    market_cap_enabled = Column(Boolean, default=False, nullable=False)
    popularity_enabled = Column(Boolean, default=False, nullable=False)
    new_listings_enabled = Column(Boolean, default=False, nullable=False)
    volatility_enabled = Column(Boolean, default=False, nullable=False)
    price_change_enabled = Column(Boolean, default=False, nullable=False)
    pattern_detection_enabled = Column(Boolean, default=False, nullable=False)
    social_mentions_enabled = Column(Boolean, default=False, nullable=False)

    # 우선순위 순서 및 로직
    priority_order = Column(JSON, default=list)
    logic_type = Column(String(10), default="OR", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        return (
            f"<PrioritySettings id={self.id} "
            f"user_id={self.user_id} name={self.setting_name!r}>"
        )


class MLModelSettings(Base):
    """ML 모델 설정 테이블"""

    __tablename__ = "ml_model_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)

    # Gap 예측 모델
    gap_model_type = Column(String(50), default="lightgbm", nullable=False)
    gap_model_params = Column(JSON, default=dict)
    gap_model_enabled = Column(Boolean, default=True, nullable=False)

    # Adaptive TimeFrame
    adaptive_tf_enabled = Column(Boolean, default=False, nullable=False)
    adaptive_tf_method = Column(String(50), default="symbol_based", nullable=False)
    adaptive_tf_params = Column(JSON, default=dict)

    # 이상치 감지
    anomaly_model_type = Column(String(50), default="isolation_forest", nullable=False)
    anomaly_threshold = Column(Numeric(5, 2), default=0.95)
    anomaly_enabled = Column(Boolean, default=True, nullable=False)

    # Drift 모니터링
    drift_monitor_type = Column(String(50), default="evidently", nullable=False)
    drift_check_interval = Column(Integer, default=3600)
    drift_enabled = Column(Boolean, default=True, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        return (
            f"<MLModelSettings id={self.id} "
            f"user_id={self.user_id} gap_model={self.gap_model_type!r}>"
        )


class SymbolPriorityScores(Base):
    """심볼별 우선순위 점수 테이블"""

    __tablename__ = "symbol_priority_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange = Column(String(50), nullable=False)
    symbol = Column(String(50), nullable=False)

    # 항목별 점수 (0 ~ 100)
    volume_score = Column(Numeric(10, 4), default=0)
    market_cap_score = Column(Numeric(10, 4), default=0)
    popularity_score = Column(Numeric(10, 4), default=0)
    new_listing_score = Column(Numeric(10, 4), default=0)
    volatility_score = Column(Numeric(10, 4), default=0)
    price_change_score = Column(Numeric(10, 4), default=0)
    pattern_score = Column(Numeric(10, 4), default=0)
    social_score = Column(Numeric(10, 4), default=0)

    total_score = Column(Numeric(10, 4), default=0)
    weighted_score = Column(Numeric(10, 4), default=0)
    rank = Column(Integer, nullable=True)

    calculated_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<SymbolPriorityScores id={self.id} "
            f"exchange={self.exchange!r} symbol={self.symbol!r} "
            f"total={self.total_score}>"
        )


class MLPredictions(Base):
    """ML 예측 결과 테이블"""

    __tablename__ = "ml_predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange = Column(String(50), nullable=False)
    symbol = Column(String(50), nullable=False)

    model_type = Column(String(50), nullable=False)
    model_version = Column(String(50), nullable=True)

    prediction_type = Column(String(50), nullable=False)
    prediction_value = Column(JSON, nullable=False)
    confidence_score = Column(Numeric(5, 4), nullable=True)

    predicted_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<MLPredictions id={self.id} "
            f"symbol={self.symbol!r} model={self.model_type!r}>"
        )
