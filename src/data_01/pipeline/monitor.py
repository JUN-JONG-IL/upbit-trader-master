"""
src/data_01/pipeline/monitor.py
Stage 10: Prometheus ë©”íŠ¸ë¦??˜ì§‘

?Œì´?„ë¼??ê°??¨ê³„??ì²˜ë¦¬ ê±´ìˆ˜, ?¤ë¥˜ ?? ì§€???œê°„???˜ì§‘?©ë‹ˆ??
Prometheus ?´ë¼?´ì–¸?¸ê? ?¤ì¹˜?˜ì–´ ?ˆì? ?Šìœ¼ë©??”ë?(no-op) ë©”íŠ¸ë¦?„ ?¬ìš©?©ë‹ˆ??
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ë©”íŠ¸ë¦??°ì´??(Prometheus ?†ì´???™ì‘)
# ---------------------------------------------------------------------------
@dataclass
class PipelineMetrics:
    """?Œì´?„ë¼???¨ê³„ë³?ì§‘ê³„ ë©”íŠ¸ë¦?"""

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
    """?Œì´?„ë¼??ì²˜ë¦¬ ?µê³„ë¥??˜ì§‘?©ë‹ˆ??"""

    def __init__(self, use_prometheus: bool = False) -> None:
        self._metrics = PipelineMetrics()
        self._prom    = None
        if use_prometheus:
            self._init_prometheus()

    # ------------------------------------------------------------------
    # Prometheus ì´ˆê¸°??(? íƒ)
    # ------------------------------------------------------------------
    def _init_prometheus(self) -> None:
        try:
            from prometheus_client import Counter, Gauge  # type: ignore

            self._prom = {
                "received":  Counter("pipeline_candles_received_total",  "?˜ì‹  ìº”ë“¤ ??),
                "staged":    Counter("pipeline_candles_staged_total",    "staging ?€????),
                "finalized": Counter("pipeline_candles_finalized_total", "ìµœì¢… ?€????),
                "errors":    Counter("pipeline_errors_total",            "?Œì´?„ë¼???¤ë¥˜ ??),
                "gaps":      Counter("pipeline_gaps_total",              "Gap ê°ì? ??),
                "latency":   Gauge(  "pipeline_latency_ms",              "ë§ˆì?ë§?ì²˜ë¦¬ ì§€??(ms)"),
            }
            logger.info("Prometheus ë©”íŠ¸ë¦?ì´ˆê¸°???„ë£Œ")
        except ImportError:
            logger.warning("prometheus_client ë¯¸ì„¤ì¹???ë©”íŠ¸ë¦?ë¹„í™œ?±í™”")

    # ------------------------------------------------------------------
    # ì¹´ìš´??ì¦ê? ?¬í¼
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
    # ì§€???œê°„ ì¸¡ì •
    # ------------------------------------------------------------------
    @contextmanager
    def measure(self) -> Iterator[None]:
        """ì»¨í…?¤íŠ¸ ë¸”ë¡???¤í–‰ ?œê°„??ì¸¡ì •?©ë‹ˆ??"""
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
    # ì¡°íšŒ
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        """?„ì¬ ë©”íŠ¸ë¦??¤ëƒ…?·ì„ dictë¡?ë°˜í™˜?©ë‹ˆ??"""
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

