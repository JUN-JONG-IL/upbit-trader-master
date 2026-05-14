# -*- coding: utf-8 -*-
"""timescale.core 패키지 — TimescaleConnector 분산 모듈"""

# 신규 모듈화된 믹스인 및 커넥터 클래스
from .schema_ddl import SchemaDDLMixin
from .candle_writer import CandleWriterMixin
from .query_helpers import QueryHelperMixin
from .connector_base import TimescaleConnector

# 기존 schema.py (DDL 상수) 유지 (하위호환)
try:
    from .schema import ensure_schema
except Exception:
    ensure_schema = None  # type: ignore

# kafka_client 선택적 임포트
try:
    from .kafka_client import KafkaClient
except Exception:
    KafkaClient = None  # type: ignore

__all__ = [
    "TimescaleConnector",
    "SchemaDDLMixin",
    "CandleWriterMixin",
    "QueryHelperMixin",
    "ensure_schema",
    "KafkaClient",
]
