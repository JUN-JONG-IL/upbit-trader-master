"""
feast_repo/features.py

Feast 피처 정의 — 거래 심볼 기반 온라인/오프라인 피처 뷰

사용 방법:
  1. feast apply   # 피처 저장소 초기화
  2. feast materialize-incremental $(date -u +"%Y-%m-%dT%H:%M:%S")
"""
from __future__ import annotations

from datetime import timedelta

from feast import Entity, FeatureView, Field  # type: ignore
from feast.data_source import FileSource  # type: ignore
from feast.types import Float64, Int64  # type: ignore

# ---------------------------------------------------------------------------
# Entity 정의
# ---------------------------------------------------------------------------

symbol = Entity(
    name="symbol",
    description="거래 심볼 (예: KRW-BTC)",
    join_keys=["symbol"],
)

# ---------------------------------------------------------------------------
# Data Sources
# ---------------------------------------------------------------------------

market_stats_source = FileSource(
    path="data/market_stats.parquet",
    timestamp_field="timestamp",
)

technical_indicators_source = FileSource(
    path="data/technical_indicators.parquet",
    timestamp_field="timestamp",
)

# ---------------------------------------------------------------------------
# Feature Views
# ---------------------------------------------------------------------------

market_stats_fv = FeatureView(
    name="market_stats",
    entities=[symbol],
    ttl=timedelta(days=1),
    schema=[
        Field(name="price_mean_24h", dtype=Float64),
        Field(name="volume_sum_24h", dtype=Float64),
        Field(name="price_high_24h", dtype=Float64),
        Field(name="price_low_24h", dtype=Float64),
        Field(name="trade_count_24h", dtype=Int64),
    ],
    online=True,
    source=market_stats_source,
    tags={"team": "trading", "version": "v9.0"},
)

technical_indicators_fv = FeatureView(
    name="technical_indicators",
    entities=[symbol],
    ttl=timedelta(hours=1),
    schema=[
        Field(name="rsi_14", dtype=Float64),
        Field(name="macd", dtype=Float64),
        Field(name="macd_signal", dtype=Float64),
        Field(name="bb_upper", dtype=Float64),
        Field(name="bb_lower", dtype=Float64),
        Field(name="ema_20", dtype=Float64),
    ],
    online=True,
    source=technical_indicators_source,
    tags={"team": "trading", "version": "v9.0"},
)
