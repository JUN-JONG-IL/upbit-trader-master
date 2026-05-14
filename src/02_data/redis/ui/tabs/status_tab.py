# 상태 탭 데이터 수집 함수 (SCAN 사용, INFO server에서 버전 수집 포함)
from __future__ import annotations
from typing import Dict, Any, Optional
try:
    from . import common
except ImportError:
    import common  # type: ignore[no-redef]

def fetch_stats(host: str, port: int, password: Optional[str], timeout: float, client=None) -> Dict[str, str]:
    """
    반환 dict:
    {
      "status": "green"|"red"|"gray",
      "key_count": "1,234개",
      "memory": "12.34 MB",
      "avg_ttl": "7일",
      "hit_rate": "12.3%" or "데이터 없음" or "조회 불가",
      "redis_version": "7.4.7"
    }
    """
    result: Dict[str, str] = {
        "status": "gray",
        "key_count": "-",
        "memory": "-",
        "avg_ttl": "7일",
        "hit_rate": "-",
        "redis_version": "-",
    }

    # 1) 키 카운트 (SCAN 기반)
    try:
        cnt = common.scan_count(host, port, password, timeout, "candles:*", client=client, max_scan=200000)
        result["key_count"] = f"{cnt:,}개"
        # 상태에 대해서는 간단히 연결 가능 여부로 green 처리
        result["status"] = "green"
    except Exception:
        result["key_count"] = "-"
        result["status"] = "red"

    # 2) 메모리 정보 (INFO memory)
    try:
        info = common.info_section(host, port, password, timeout, "memory", client=client)
        used_bytes = int(info.get("used_memory", 0) or 0)
        result["memory"] = f"{used_bytes / (1024*1024):.2f} MB"
    except Exception:
        result["memory"] = "조회 불가"

    # 3) 캐시 히트율 (INFO stats)
    try:
        stats = common.info_section(host, port, password, timeout, "stats", client=client)
        hits = int(stats.get("keyspace_hits", 0) or 0)
        misses = int(stats.get("keyspace_misses", 0) or 0)
        total = hits + misses
        result["hit_rate"] = f"{hits / total * 100:.1f}%" if total > 0 else "데이터 없음"
    except Exception:
        result["hit_rate"] = "조회 불가"

    # 4) Redis 버전 (INFO server)
    try:
        server_info = common.info_section(host, port, password, timeout, "server", client=client)
        result["redis_version"] = server_info.get("redis_version") or server_info.get("version") or "-"
    except Exception:
        result["redis_version"] = "-"

    return result


# ---------------------------------------------------------------------------
# QWidget 탭 클래스 (fetch_stats를 이용해 UI 갱신)
# ---------------------------------------------------------------------------
import os
import logging

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "status_tab.ui")

if _HAS_QT:
    class StatusTab(QWidget):
        """Redis 성능 모니터링 탭. 목표: <2ms 응답, >90% 히트율"""

        def __init__(self, conn_params: dict = None, parent=None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                _logger.warning("[StatusTab] UI 로드 실패: %s", exc)
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
            data = fetch_stats(host, port, password, timeout)

            # 캐시 통계 레이블 갱신
            lbl_keys = getattr(self, "label_key_count", None)
            if lbl_keys:
                lbl_keys.setText(f"키 수: {data['key_count']}")

            lbl_mem = getattr(self, "label_memory", None)
            if lbl_mem:
                lbl_mem.setText(f"메모리 사용량: {data['memory']}")

            lbl_hit = getattr(self, "label_hit_rate", None)
            if lbl_hit:
                lbl_hit.setText(f"히트율: {data['hit_rate']}")

            lbl_ttl = getattr(self, "label_avg_ttl", None)
            if lbl_ttl:
                lbl_ttl.setText(f"평균 TTL: {data['avg_ttl']}")

            # 서버 정보 테이블 갱신
            self._refresh_table(host, port, password, timeout, data)

        def _refresh_table(self, host, port, password, timeout, stats_data) -> None:
            table = getattr(self, "table_status", None)
            if table is None:
                return

            # 서버 INFO 추가 조회 (업타임, OPS 등)
            try:
                server_info = common.info_section(host, port, password, timeout, "server")
                stats_info = common.info_section(host, port, password, timeout, "stats")
            except Exception:
                server_info = {}
                stats_info = {}

            uptime_secs = int(server_info.get("uptime_in_seconds", 0) or 0)
            ops = stats_info.get("instantaneous_ops_per_sec", "-")

            rows = [
                ("Redis 버전", stats_data["redis_version"]),
                ("연결 상태", "🟢 연결됨" if stats_data["status"] == "green" else "🔴 끊김"),
                ("메모리 사용량", stats_data["memory"]),
                ("캐시 히트율", stats_data["hit_rate"]),
                ("총 키 수", stats_data["key_count"]),
                ("업타임", _fmt_uptime(uptime_secs)),
                ("OPS/s", str(ops)),
            ]

            table.setRowCount(len(rows))
            for r, (item, val) in enumerate(rows):
                table.setItem(r, 0, QTableWidgetItem(item))
                table.setItem(r, 1, QTableWidgetItem(val))

else:
    class StatusTab:  # type: ignore[no-redef]
        def __init__(self, conn_params: dict = None, parent=None): pass
        def start_updates(self, interval_ms: int = 3000) -> None: pass
        def stop_updates(self) -> None: pass


def _fmt_uptime(secs: int) -> str:
    """초를 일/시간/분 포맷으로 변환."""
    if secs <= 0:
        return "-"
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days > 0:
        return f"{days}일 {hours}시간 {mins}분"
    if hours > 0:
        return f"{hours}시간 {mins}분"
    return f"{mins}분"