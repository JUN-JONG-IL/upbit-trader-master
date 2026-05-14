# Sentinel 상태 조회 파서 (안정화)
from __future__ import annotations
from typing import List, Tuple, Dict, Optional, Any
from . import common
import logging

logger = logging.getLogger(__name__)

def fetch_sentinel(host: str, port: int, password: Optional[str], timeout: float, client: Optional[Any]=None) -> Tuple[Dict[str,str], List[Tuple[str,str,str]], List[Tuple[str,str]]]:
    info: Dict[str,str] = {"master":"-","quorum":"-"}
    sentinel_rows: List[Tuple[str,str,str]] = []
    failover_rows: List[Tuple[str,str]] = []
    try:
        masters = common.sentinel_masters(host, port, password, timeout, client=client) or []
        if not masters:
            return info, sentinel_rows, failover_rows
        # sentinel_masters may return flat list [name, prop, name2, prop2...] or list of dict-like strings
        # attempt simple pairing
        master_dict = {}
        try:
            for i in range(0, len(masters)-1, 2):
                master_dict[masters[i]] = masters[i+1]
        except Exception:
            # fallback: join raw
            logger.debug("[sentinel] unexpected masters format: %s", masters)
        master_name = master_dict.get("name", masters[0] if masters else "-")
        info["master"] = master_name
        info["quorum"] = master_dict.get("quorum", "-")
        if master_name and master_name != "-":
            sent = common.sentinel_sentinels(host, port, password, timeout, master_name, client=client) or []
            # sent may be flat list: key, value, key, value...
            entry = {}
            idx = 0
            for item in sent:
                if idx % 2 == 0:
                    entry = {}
                    current_key = item
                else:
                    entry[current_key] = item
                    if current_key == "port":
                        name = entry.get("name","-")
                        ip = entry.get("ip","-")
                        port = entry.get("port","-")
                        flags = entry.get("flags","ok")
                        state = "ok" if "disconnected" not in flags and "s_down" not in flags else "DOWN"
                        sentinel_rows.append((name, f"{ip}:{port}", state))
                idx += 1
    except Exception as exc:
        logger.exception("[sentinel] fetch failed")
        failover_rows = [("N/A", "Sentinel 모드 아님 또는 조회 실패")]
    return info, sentinel_rows, failover_rows

# ---------------------------------------------------------------------------
# QWidget 탭 클래스 (fetch_sentinel를 이용해 UI 갱신)
# ---------------------------------------------------------------------------
import os

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_UI_PATH = os.path.join(os.path.dirname(__file__), "sentinel_tab.ui")

if _HAS_QT:
    class SentinelTab(QWidget):
        """Sentinel 현황 탭 - Redis HA 구성 모니터링."""

        def __init__(self, conn_params: dict = None, parent=None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[SentinelTab] UI 로드 실패: %s", exc)
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._update)
            self._timer.start(5000)

        def start_updates(self, interval_ms: int = 5000) -> None:
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
                info, sentinel_rows, failover_rows = fetch_sentinel(host, port, password, timeout)
            except Exception as exc:
                logger.debug("[SentinelTab] 조회 실패: %s", exc)
                info, sentinel_rows, failover_rows = {"master": "-", "quorum": "-"}, [], []

            self._refresh_table(info, sentinel_rows, failover_rows)

        def _refresh_table(self, info: Dict[str, str], sentinel_rows: List[Tuple[str, str, str]], failover_rows) -> None:
            table = getattr(self, "table_sentinel", None)
            if table is None:
                return

            master_name = info.get("master", "-")

            if sentinel_rows:
                table.setRowCount(len(sentinel_rows))
                for r, (name, addr, state) in enumerate(sentinel_rows):
                    # addr 형식: "ip:port"
                    ip_str, port_str = addr, "-"
                    if ":" in addr:
                        ip_str, _, port_str = addr.rpartition(":")
                    table.setItem(r, 0, QTableWidgetItem(name))
                    table.setItem(r, 1, QTableWidgetItem(master_name))
                    table.setItem(r, 2, QTableWidgetItem(port_str))
                    table.setItem(r, 3, QTableWidgetItem(state))
            elif failover_rows:
                table.setRowCount(len(failover_rows))
                for r, row in enumerate(failover_rows):
                    msg = str(row[1]) if len(row) > 1 else str(row[0])
                    table.setItem(r, 0, QTableWidgetItem(msg))
                    for c in range(1, 4):
                        table.setItem(r, c, QTableWidgetItem("-"))
            else:
                table.setRowCount(1)
                table.setItem(0, 0, QTableWidgetItem("Sentinel 없음 또는 일반 모드"))
                for c in range(1, 4):
                    table.setItem(0, c, QTableWidgetItem("-"))

else:
    class SentinelTab:  # type: ignore[no-redef]
        def __init__(self, conn_params: dict = None, parent=None): pass
        def start_updates(self, interval_ms: int = 5000) -> None: pass
        def stop_updates(self) -> None: pass
