# -*- coding: utf-8 -*-
"""
DataFlowWidget — 실시간 데이터 플로우 / 데이터 모니터링 위젯 (Phase 5)

[책임]
    WebSocket → Kafka → (TimescaleDB / ClickHouse / MongoDB) 흐름을 노드 그래프
    스타일로 시각화하고, 각 엣지(connection) 위에 초당 메시지(msg/s) · 평균
    지연(ms) · 실패율(%) 을 라이브로 표시한다.

[비파괴]
    - 신규 위젯, 기존 화면에 자동 도킹되지 않는다.
    - PyQt5 미설치 환경에서도 import 가능하도록 더미 클래스 제공.

[데이터 갱신]
    호출 측이 주기적으로 ``update_metrics(metrics_by_edge)`` 를 호출.
    예: ``{"ws->kafka": {"mps": 1500, "latency_ms": 12, "fail_pct": 0.1}}``
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSlot
    from PyQt5.QtGui import (
        QBrush,
        QColor,
        QFont,
        QPainter,
        QPainterPath,
        QPen,
    )
    from PyQt5.QtWidgets import (
        QGroupBox,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )
    _HAS_QT = True
except ImportError:  # pragma: no cover
    _HAS_QT = False
    logger.debug("[DataFlowWidget] PyQt5 없음 — 더미 클래스 사용")


# 기본 노드/엣지 토폴로지
_DEFAULT_NODES: List[Tuple[str, str]] = [
    # (node_id, label)
    ("ws", "WebSocket Pool"),
    ("kafka", "Kafka"),
    ("timescale", "TimescaleDB"),
    ("clickhouse", "ClickHouse"),
    ("mongodb", "MongoDB"),
]

_DEFAULT_EDGES: List[Tuple[str, str]] = [
    ("ws", "kafka"),
    ("kafka", "timescale"),
    ("kafka", "clickhouse"),
    ("kafka", "mongodb"),
]


def _edge_key(src: str, dst: str) -> str:
    return f"{src}->{dst}"


if _HAS_QT:

    class _FlowCanvas(QWidget):
        """노드/엣지 + 라벨을 직접 페인팅하는 내부 캔버스."""

        _NODE_W = 130
        _NODE_H = 40
        _NODE_RADIUS = 10

        def __init__(
            self,
            nodes: List[Tuple[str, str]],
            edges: List[Tuple[str, str]],
            parent: Optional[QWidget] = None,
        ) -> None:
            super().__init__(parent)
            self._nodes = list(nodes)
            self._edges = list(edges)
            self._metrics: Dict[str, Dict[str, float]] = {}
            self.setMinimumSize(640, 220)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # --------------------------------------------------------------
        def set_metrics(self, metrics: Dict[str, Dict[str, float]]) -> None:
            self._metrics = dict(metrics or {})
            self.update()

        # --------------------------------------------------------------
        def _node_positions(self) -> Dict[str, QPointF]:
            """좌→우 단순 레이아웃: ws 1열, kafka 2열, 스토리지 3열 세로 균등."""
            w, h = self.width(), self.height()
            pos: Dict[str, QPointF] = {}
            cols: Dict[str, List[str]] = {"col0": [], "col1": [], "col2": []}
            for nid, _ in self._nodes:
                if nid == "ws":
                    cols["col0"].append(nid)
                elif nid == "kafka":
                    cols["col1"].append(nid)
                else:
                    cols["col2"].append(nid)
            xs = {"col0": 0.10, "col1": 0.45, "col2": 0.85}
            for ck, ids in cols.items():
                if not ids:
                    continue
                step = h / (len(ids) + 1)
                for i, nid in enumerate(ids, start=1):
                    pos[nid] = QPointF(w * xs[ck], step * i)
            return pos

        # --------------------------------------------------------------
        def paintEvent(self, _evt) -> None:
            if not self._nodes:
                return
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.fillRect(self.rect(), QColor("#1e1f22"))

            positions = self._node_positions()
            label_map = {nid: lbl for nid, lbl in self._nodes}

            # 엣지 그리기
            edge_pen = QPen(QColor("#5d6975"))
            edge_pen.setWidth(2)
            metric_font = QFont()
            metric_font.setPointSize(8)

            for src, dst in self._edges:
                if src not in positions or dst not in positions:
                    continue
                a = positions[src]
                b = positions[dst]
                p.setPen(edge_pen)
                # 베지어 곡선
                ctrl1 = QPointF((a.x() + b.x()) / 2, a.y())
                ctrl2 = QPointF((a.x() + b.x()) / 2, b.y())
                path = QPainterPath(a)
                path.cubicTo(ctrl1, ctrl2, b)
                p.drawPath(path)

                # 엣지 라벨 (중앙)
                m = self._metrics.get(_edge_key(src, dst), {})
                if m:
                    mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2 - 8)
                    txt = self._format_metric(m)
                    p.setPen(QPen(QColor("#d0d4d8")))
                    p.setFont(metric_font)
                    p.drawText(mid, txt)

            # 노드 그리기
            node_brush = QBrush(QColor("#2c3138"))
            node_pen = QPen(QColor("#8a93a0"))
            node_pen.setWidth(1)
            label_pen = QPen(QColor("#f5f6f7"))
            label_font = QFont()
            label_font.setBold(True)
            label_font.setPointSize(9)

            for nid, label in self._nodes:
                if nid not in positions:
                    continue
                c = positions[nid]
                rect = QRectF(c.x() - self._NODE_W / 2, c.y() - self._NODE_H / 2,
                              self._NODE_W, self._NODE_H)
                p.setBrush(node_brush)
                p.setPen(node_pen)
                p.drawRoundedRect(rect, self._NODE_RADIUS, self._NODE_RADIUS)
                p.setPen(label_pen)
                p.setFont(label_font)
                p.drawText(rect, Qt.AlignCenter, label)

            p.end()

        @staticmethod
        def _format_metric(m: Dict[str, float]) -> str:
            mps = m.get("mps", 0.0) or 0.0
            latency = m.get("latency_ms", 0.0) or 0.0
            fail = m.get("fail_pct", 0.0) or 0.0
            return f"{mps:.0f} msg/s · {latency:.0f} ms · {fail:.2f}%"


    class DataFlowWidget(QWidget):
        """WS → Kafka → (Timescale/ClickHouse/Mongo) 흐름 시각화 위젯.

        ``update_metrics({'ws->kafka': {'mps': ..., 'latency_ms': ..., 'fail_pct': ...}, ...})``
        형태로 갱신한다. 갱신 주기는 호출자 책임(권장: 1~3초).
        """

        def __init__(
            self,
            nodes: Optional[List[Tuple[str, str]]] = None,
            edges: Optional[List[Tuple[str, str]]] = None,
            title: Optional[str] = "실시간 데이터 플로우 / 데이터 모니터링",
            parent: Optional[QWidget] = None,
        ) -> None:
            super().__init__(parent)
            self._canvas = _FlowCanvas(
                nodes or _DEFAULT_NODES, edges or _DEFAULT_EDGES, self
            )
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            if title:
                box = QGroupBox(title, self)
                outer.addWidget(box)
                inner = QVBoxLayout(box)
                inner.addWidget(self._canvas)
            else:
                outer.addWidget(self._canvas)

        # --------------------------------------------------------------
        @pyqtSlot(dict)
        def update_metrics(self, metrics_by_edge: Dict[str, Dict[str, float]]) -> None:
            """엣지별 메트릭 갱신.

            Args:
                metrics_by_edge: ``{"src->dst": {"mps": float,
                                                  "latency_ms": float,
                                                  "fail_pct": float}}``
            """
            self._canvas.set_metrics(metrics_by_edge or {})

        def reset(self) -> None:
            self._canvas.set_metrics({})

else:  # pragma: no cover
    class DataFlowWidget:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            self._metrics: Dict[str, Dict[str, float]] = {}

        def update_metrics(self, metrics_by_edge: Dict[str, Dict[str, float]]) -> None:
            self._metrics = dict(metrics_by_edge or {})

        def reset(self) -> None:
            self._metrics = {}


__all__ = ["DataFlowWidget"]
