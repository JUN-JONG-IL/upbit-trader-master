"""
src/data_01/pipeline/monitor.py
Stage 10: Prometheus 硫뷀듃由??섏쭛

?뚯씠?꾨씪??媛??④퀎??泥섎━ 嫄댁닔, ?ㅻ쪟 ?? 吏???쒓컙???섏쭛?⑸땲??
Prometheus ?대씪?댁뼵?멸? ?ㅼ튂?섏뼱 ?덉? ?딆쑝硫??붾?(no-op) 硫뷀듃由?쓣 ?ъ슜?⑸땲??
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 硫뷀듃由??곗씠??(Prometheus ?놁씠???숈옉)
# ---------------------------------------------------------------------------
@dataclass
class PipelineMetrics:
    """?뚯씠?꾨씪???④퀎蹂?吏묎퀎 硫뷀듃由?"""

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
    """?뚯씠?꾨씪??泥섎━ ?듦퀎瑜??섏쭛?⑸땲??"""

    def __init__(self, use_prometheus: bool = False) -> None:
        self._metrics = PipelineMetrics()
        self._prom    = None
        if use_prometheus:
            self._init_prometheus()

    # ------------------------------------------------------------------
    # Prometheus 珥덇린??(?좏깮)
    # ------------------------------------------------------------------
    def _init_prometheus(self) -> None:
        try:
            from prometheus_client import Counter, Gauge  # type: ignore

            self._prom = {
                "received":  Counter("pipeline_candles_received_total",  "?섏떊 罹붾뱾 ??),
                "staged":    Counter("pipeline_candles_staged_total",    "staging ?????),
                "finalized": Counter("pipeline_candles_finalized_total", "理쒖쥌 ?????),
                "errors":    Counter("pipeline_errors_total",            "?뚯씠?꾨씪???ㅻ쪟 ??),
                "gaps":      Counter("pipeline_gaps_total",              "Gap 媛먯? ??),
                "latency":   Gauge(  "pipeline_latency_ms",              "留덉?留?泥섎━ 吏??(ms)"),
            }
            logger.info("Prometheus 硫뷀듃由?珥덇린???꾨즺")
        except ImportError:
            logger.warning("prometheus_client 誘몄꽕移???硫뷀듃由?鍮꾪솢?깊솕")

    # ------------------------------------------------------------------
    # 移댁슫??利앷? ?ы띁
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
    # 吏???쒓컙 痢≪젙
    # ------------------------------------------------------------------
    @contextmanager
    def measure(self) -> Iterator[None]:
        """而⑦뀓?ㅽ듃 釉붾줉???ㅽ뻾 ?쒓컙??痢≪젙?⑸땲??"""
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
    # 議고쉶
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        """?꾩옱 硫뷀듃由??ㅻ깄?룹쓣 dict濡?諛섑솚?⑸땲??"""
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

