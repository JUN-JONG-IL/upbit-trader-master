# L1 캐시 통계 및 만료 예정 키 조회 (SCAN 사용, 안전성 보강)
from __future__ import annotations
from typing import Dict, List, Tuple, Optional, Any
from . import common
import logging

logger = logging.getLogger(__name__)

def fetch_l1_cache(host: str, port: int, password: Optional[str], timeout: float, client: Optional[Any]=None) -> Tuple[Dict[str,str], List[Tuple[str,str]]]:
    stats: Dict[str,str] = {"total_keys":"-","mem_usage":"-","hit_rate":"-"}
    expiring: List[Tuple[str,str]] = []
    keys_list = []
    try:
        # 안전: SCAN 기반 키 카운트 (운영에서는 KEYS 사용 금지)
        cnt = common.scan_count(host, port, password, timeout, "candles:*", client=client, max_scan=200000)
        stats["total_keys"] = f"{cnt:,}개"
    except Exception as exc:
        logger.debug("[l1_cache] scan_count failed: %s", exc, exc_info=True)
        stats["total_keys"] = "-"
    try:
        info = common.info_section(host, port, password, timeout, "memory", client=client)
        used_bytes = int(info.get("used_memory", 0) or 0)
        stats["mem_usage"] = f"{used_bytes / (1024*1024):.2f} MB"
    except Exception:
        stats["mem_usage"] = "-"
    try:
        s = common.info_section(host, port, password, timeout, "stats", client=client)
        hits = int(s.get("keyspace_hits", 0) or 0)
        misses = int(s.get("keyspace_misses", 0) or 0)
        total = hits + misses
        stats["hit_rate"] = f"{hits / total * 100:.1f}%" if total > 0 else "데이터 없음"
    except Exception:
        stats["hit_rate"] = "-"
    # TTL 상위 몇개 검사 (부하 주의)
    try:
        # keys()는 운영에서 위험. 여기선 작은 샘플로 scan 사용
        if client:
            try:
                keys_list = [k.decode() if isinstance(k, (bytes,bytearray)) else str(k) for k in client.scan_iter(match="candles:*", count=1000)]
            except Exception:
                keys_list = common.keys(host, port, password, timeout, "candles:*", client=client)
        else:
            keys_list = common.keys(host, port, password, timeout, "candles:*", client=None)
        ttl_pairs = []
        for key in (keys_list or [])[:200]:
            try:
                t = common.ttl(host, port, password, timeout, key, client=client)
                if t is not None and t >= 0:
                    ttl_pairs.append((int(t), key))
            except Exception:
                pass
        ttl_pairs.sort()
        expiring = [(k, str(t)) for t,k in ttl_pairs[:20]]
    except Exception as exc:
        logger.debug("[l1_cache] TTL scan failed: %s", exc, exc_info=True)
        expiring = []
    return stats, expiring

# ---------------------------------------------------------------------------
# QWidget 탭 클래스 (fetch_l1_cache를 이용해 UI 갱신)
# ---------------------------------------------------------------------------
import os

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_UI_PATH = os.path.join(os.path.dirname(__file__), "l1_cache_tab.ui")

if _HAS_QT:
    class L1CacheTab(QWidget):
        """L1 캐시 현황 탭 - 만료 예정 키와 메모리 통계 표시."""

        def __init__(self, conn_params: dict = None, parent=None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[L1CacheTab] UI 로드 실패: %s", exc)
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
                stats, expiring = fetch_l1_cache(host, port, password, timeout)
            except Exception as exc:
                logger.debug("[L1CacheTab] 조회 실패: %s", exc)
                stats, expiring = {"total_keys": "-", "mem_usage": "-", "hit_rate": "-"}, []

            self._refresh_table(expiring, stats)

        def _refresh_table(self, expiring: List[Tuple[str, str]], stats: Dict[str, str]) -> None:
            table = getattr(self, "table_cache", None)
            if table is None:
                return

            table.setRowCount(len(expiring))
            for r, (key, ttl_str) in enumerate(expiring):
                # 키에서 심볼 추출 (예: candles:KRW-BTC -> KRW-BTC)
                parts = key.split(":", 1)
                symbol = parts[1] if len(parts) > 1 else key
                table.setItem(r, 0, QTableWidgetItem(symbol))
                table.setItem(r, 1, QTableWidgetItem(stats.get("mem_usage", "-")))
                table.setItem(r, 2, QTableWidgetItem("-"))
                table.setItem(r, 3, QTableWidgetItem(f"{ttl_str}초"))

else:
    class L1CacheTab:  # type: ignore[no-redef]
        def __init__(self, conn_params: dict = None, parent=None): pass
        def start_updates(self, interval_ms: int = 3000) -> None: pass
        def stop_updates(self) -> None: pass
