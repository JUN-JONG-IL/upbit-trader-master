# Gap Fill 큐 조회/파싱 (로깅·에러 노출 강화)
from __future__ import annotations
from typing import List, Tuple, Optional, Any
from . import common
import json
import logging

logger = logging.getLogger(__name__)

def fetch_gap_queue(host: str, port: int, password: Optional[str], timeout: float, client: Optional[Any]=None) -> Tuple[int, List[Tuple[str,str,str]]]:
    """
    반환: (queue_len, rows) where rows: [(symbol, priority, gap_range), ...]
    오류 시 rows 첫 항목에 ("!ERROR!", "", "메시지")를 넣음
    """
    rows: List[Tuple[str,str,str]] = []
    queue_len = 0
    try:
        parsed_len = common.zcard(host, port, password, timeout, "gap_fill_queue", client=client)
        if parsed_len is None:
            raise RuntimeError("ZCARD 파싱 실패")
        queue_len = int(parsed_len)
        if queue_len == 0:
            return 0, rows  # 빈 큐 정상
        items = common.zrevrange_withscores(host, port, password, timeout, "gap_fill_queue", 0, 49, client=client)
        for member, score_str in items:
            try:
                score = float(score_str)
                if score >= 10:
                    priority = "HIGH"
                elif score >= 5:
                    priority = "MEDIUM"
                else:
                    priority = "LOW"
            except Exception:
                priority = str(score_str)
            symbol = member
            gap_range = "-"
            # 시도: JSON 파싱 우선
            try:
                parsed = json.loads(member)
                if isinstance(parsed, dict):
                    symbol = parsed.get("symbol", str(parsed))
                    s = parsed.get("start") or parsed.get("gap_start") or parsed.get("approx_time")
                    e = parsed.get("end") or parsed.get("gap_end")
                    if s or e:
                        gap_range = f"{s or '-'} → {e or '-'}"
                else:
                    symbol = str(parsed)
            except Exception:
                # fallback: ':' 구분으로 간단 파싱
                try:
                    parts = member.split(":")
                    symbol = parts[0] if parts else member
                    gap_range = ":".join(parts[1:]) if len(parts) > 1 else "-"
                except Exception:
                    gap_range = "-"
            rows.append((symbol, priority, gap_range))
    except Exception as exc:
        logger.exception("[gap_queue] fetch failed")
        rows = [("!ERROR!", "", "Gap 큐 조회 실패: 연결/파싱 문제")]
        queue_len = 0
    return queue_len, rows

# ---------------------------------------------------------------------------
# QWidget 탭 클래스 (fetch_gap_queue를 이용해 UI 갱신)
# ---------------------------------------------------------------------------
import os

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_UI_PATH = os.path.join(os.path.dirname(__file__), "gap_queue_tab.ui")

if _HAS_QT:
    class GapQueueTab(QWidget):
        """Gap Fill 큐 현황 탭."""

        def __init__(self, conn_params: dict = None, parent=None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[GapQueueTab] UI 로드 실패: %s", exc)
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._update)
            self._timer.start(3000)

        def start_updates(self, interval_ms: int = 3000) -> None:
            self._timer.setInterval(max(1000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

        def _get_redis_params(self):
            p = self._conn_params
            return (
                p.get("host", "localhost"),
                int(p.get("port", 58530)),
                p.get("password", None),
                3.0,
            )

        def _update(self) -> None:
            host, port, password, timeout = self._get_redis_params()
            try:
                queue_len, rows = fetch_gap_queue(host, port, password, timeout)
            except Exception as exc:
                logger.debug("[GapQueueTab] 조회 실패: %s", exc)
                queue_len, rows = 0, []

            # 큐 크기 레이블 갱신
            lbl_size = getattr(self, "label_queue_size", None)
            if lbl_size:
                lbl_size.setText(f"큐 크기: {queue_len}")

            lbl_proc = getattr(self, "label_processing", None)
            if lbl_proc:
                lbl_proc.setText("처리 중: -")

            self._refresh_table(rows)

        def _refresh_table(self, rows: List[Tuple[str, str, str]]) -> None:
            table = getattr(self, "table_queue", None)
            if table is None:
                return
            table.setRowCount(len(rows))
            for r, (symbol, priority, gap_range) in enumerate(rows):
                if symbol == "!ERROR!":
                    table.setItem(r, 0, QTableWidgetItem(gap_range))
                    table.setItem(r, 1, QTableWidgetItem("-"))
                    table.setItem(r, 2, QTableWidgetItem("-"))
                    table.setItem(r, 3, QTableWidgetItem("-"))
                else:
                    # gap_range: "start → end" 파싱 시도
                    start_str, end_str = "-", "-"
                    if " → " in gap_range:
                        parts = gap_range.split(" → ", 1)
                        start_str = parts[0].strip() or "-"
                        end_str = parts[1].strip() or "-"
                    table.setItem(r, 0, QTableWidgetItem(symbol))
                    table.setItem(r, 1, QTableWidgetItem(start_str))
                    table.setItem(r, 2, QTableWidgetItem(end_str))
                    table.setItem(r, 3, QTableWidgetItem(priority))

else:
    class GapQueueTab:  # type: ignore[no-redef]
        def __init__(self, conn_params: dict = None, parent=None): pass
        def start_updates(self, interval_ms: int = 3000) -> None: pass
        def stop_updates(self) -> None: pass
