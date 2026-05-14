"""
src/data_01/pipeline/monitor.py
Stage 10: Prometheus 메트릭 수집

파이프라인 각 단계의 처리 건수, 오류 수, 지연 시간을 수집합니다.
Prometheus 클라이언트가 설치되어 있지 않으면 더미(no-op) 메트릭을 사용합니다.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 메트릭 데이터 (Prometheus 없이도 동작)
# ---------------------------------------------------------------------------
@dataclass
class PipelineMetrics:
    """파이프라인 단계별 집계 메트릭."""

    received:      int   = 0
    staged:        int   = 0
    validated:     int   = 0
    isolated:      int   = 0
    finalized:     int   = 0
    notified:      int   = 0
    errors:        int   = 0
    gap_detected:  int   = 0
    last_latency_ms: float = 0.0


class PipelineMonitor:
    """파이프라인 처리 통계를 수집합니다."""

    def __init__(self, use_prometheus: bool = False) -> None:
        self._metrics = PipelineMetrics()
        self._prom    = None
        if use_prometheus:
            self._init_prometheus()

    # ------------------------------------------------------------------
    # Prometheus 초기화 (선택)
    # ------------------------------------------------------------------
    def _init_prometheus(self) -> None:
        try:
            from prometheus_client import Counter, Gauge  # type: ignore

            self._prom = {
                "received":  Counter("pipeline_candles_received_total",  "수신 캔들 수"),
                "staged":    Counter("pipeline_candles_staged_total",    "staging 저장 수"),
                "finalized": Counter("pipeline_candles_finalized_total", "최종 저장 수"),
                "errors":    Counter("pipeline_errors_total",            "파이프라인 오류 수"),
                "gaps":      Counter("pipeline_gaps_total",              "Gap 감지 수"),
                "latency":   Gauge(  "pipeline_latency_ms",              "마지막 처리 지연 (ms)"),
            }
            logger.info("Prometheus 메트릭 초기화 완료")
        except ImportError:
            logger.warning("prometheus_client 미설치 – 메트릭 비활성화")

    # ------------------------------------------------------------------
    # 카운터 증가 헬퍼
    # ------------------------------------------------------------------
    def inc_received(self)  -> None: self._inc("received")
    def inc_staged(self)    -> None: self._inc("staged")
    def inc_validated(self) -> None: self._inc("validated")
    def inc_isolated(self)  -> None: self._inc("isolated")
    def inc_finalized(self) -> None: self._inc("finalized")
    def inc_notified(self)  -> None: self._inc("notified")
    def inc_errors(self)    -> None: self._inc("errors")
    def inc_gap(self)       -> None: self._inc("gap_detected")

    def _inc(self, name: str) -> None:
        setattr(self._metrics, name, getattr(self._metrics, name, 0) + 1)
        if self._prom and name in self._prom:
            try:
                self._prom[name].inc()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 지연 시간 측정
    # ------------------------------------------------------------------
    @contextmanager
    def measure(self) -> Iterator[None]:
        """컨텍스트 블록의 실행 시간을 측정합니다."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._metrics.last_latency_ms = elapsed_ms
            if self._prom and "latency" in self._prom:
                try:
                    self._prom["latency"].set(elapsed_ms)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        """현재 메트릭 스냅샷을 dict로 반환합니다."""
        m = self._metrics
        return {
            "received":        m.received,
            "staged":          m.staged,
            "validated":       m.validated,
            "isolated":        m.isolated,
            "finalized":       m.finalized,
            "notified":        m.notified,
            "errors":          m.errors,
            "gap_detected":    m.gap_detected,
            "last_latency_ms": m.last_latency_ms,
        }
