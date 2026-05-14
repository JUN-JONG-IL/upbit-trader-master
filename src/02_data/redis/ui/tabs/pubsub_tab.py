# Pub/Sub 채널 조회 - UX 개선: 채널이 없을 때 안내 행을 표시하도록 함
from __future__ import annotations
import logging
import importlib
from typing import List, Tuple, Optional, Any

from . import common

logger = logging.getLogger(__name__)

MAX_CHANNELS = 2000  # UI 과부하 방지


def _normalize_channel_list(raw_list: List[Any]) -> List[str]:
    """
    raw_list 요소들을 안전하게 문자열로 변환.
    """
    out: List[str] = []
    for item in raw_list or []:
        try:
            if isinstance(item, (bytes, bytearray)):
                out.append(item.decode("utf-8", errors="replace"))
            else:
                out.append(str(item))
        except Exception:
            continue
    return out


def _get_numsub_for_channel(ch: str, host: str, port: int, password: Optional[str], timeout: float, client: Optional[Any]) -> int:
    """
    채널의 구독자 수를 조회.
    실패 시 -1 반환.
    """
    try:
        if client:
            try:
                arr = client.execute_command("PUBSUB", "NUMSUB", ch) or []
                if isinstance(arr, (list, tuple)) and len(arr) >= 2:
                    val = arr[1]
                    if isinstance(val, (bytes, bytearray)):
                        val = val.decode("utf-8", errors="replace")
                    return int(val)
                return int(str(arr))
            except Exception as exc:
                logger.debug("[pubsub] client NUMSUB failed for %s: %s", ch, exc, exc_info=True)
        # 폴백
        try:
            cnt_str = common.pubsub_numsub(host, port, password, timeout, ch, client=None)
            return int(cnt_str)
        except Exception:
            return -1
    except Exception:
        return -1


def fetch_pubsub(host: str, port: int, password: Optional[str], timeout: float, client: Optional[Any] = None, pattern: str = "*") -> List[Tuple[str, Any]]:
    """
    Pub/Sub 채널 목록과 구독자 수를 반환합니다.
    - 정상: [(channel, subscribers), ...]
    - 오류: [("!ERROR!", "한글 메시지")]
    - 채널이 전혀 없으면 정보 토큰을 반환: [("!INFO!", "활성 채널 없음 — 현재 구독 채널이 없습니다")]
    """
    local_client = None
    used_local_client = False

    try:
        # 1) client 우선 확보 시도
        if client is None:
            try:
                client = common.get_client_if_available()
            except Exception:
                client = None

        # 2) client가 없으면 로컬 redis 패키지로 임시 클라이언트 시도 (기존 보강로직과 동일)
        if client is None:
            try:
                redis_mod = importlib.import_module("redis")
                # 시도 가능한 클래스들 검사
                ClientClass = getattr(redis_mod, "Redis", None) or getattr(redis_mod, "StrictRedis", None) or getattr(getattr(redis_mod, "client", None), "Redis", None)
                if ClientClass is not None:
                    try:
                        local_client = ClientClass(host=host, port=port, password=password, socket_connect_timeout=timeout, decode_responses=True)
                    except TypeError:
                        local_client = ClientClass(host=host, port=port, password=password, socket_connect_timeout=timeout)
                    try:
                        local_client.ping()
                        client = local_client
                        used_local_client = True
                        logger.debug("[pubsub] created temporary redis client via detected Redis class")
                    except Exception:
                        try:
                            if hasattr(local_client, "close"):
                                local_client.close()
                        except Exception:
                            pass
                        local_client = None
                        client = None
            except Exception as exc:
                logger.debug("[pubsub] import redis or create client failed: %s", exc, exc_info=True)
                client = None

        # 3) client가 여전히 없으면 에러 토큰 반환
        if client is None:
            logger.warning("[pubsub] Redis client unavailable (client=None). PUBSUB 명령을 수행할 수 없습니다.")
            return [("!ERROR!", "Redis 클라이언트 없음 — pip install redis 또는 repo 내 redis.py 이름 충돌 확인")]

        # 4) PUBSUB CHANNELS 요청
        try:
            raw = client.execute_command("PUBSUB", "CHANNELS", pattern) or []
            channels = _normalize_channel_list(raw)
        except Exception as exc:
            logger.debug("[pubsub] client PUBSUB CHANNELS failed: %s", exc, exc_info=True)
            channels = _normalize_channel_list(common.pubsub_channels(host, port, password, timeout, pattern, client=None))

        # 5) 채널이 없으면 명확한 정보 행을 반환(빈 테이블 대신)
        if not channels:
            logger.debug("[pubsub] no channels found (pattern=%s)", pattern)
            return [("!INFO!", "활성 채널 없음 — 현재 구독 채널이 없습니다")]

        # 6) 각 채널에 대해 NUMSUB로 구독자 수를 구한다
        rows: List[Tuple[str, Any]] = []
        for ch in channels[:MAX_CHANNELS]:
            cnt = _get_numsub_for_channel(ch, host, port, password, timeout, client)
            rows.append((ch, cnt if isinstance(cnt, int) else -1))

        # 7) 정렬: 유효한 카운트(>=0)를 앞에 두고 내림차순
        rows_valid = [r for r in rows if isinstance(r[1], int) and r[1] >= 0]
        rows_invalid = [r for r in rows if not (isinstance(r[1], int) and r[1] >= 0)]
        rows_valid.sort(key=lambda t: t[1], reverse=True)
        rows = rows_valid + rows_invalid

        logger.debug("[pubsub] fetched %d channels", len(rows))
        return rows

    except Exception as exc:
        logger.exception("[pubsub] fetch failed: %s", exc)
        return [("!ERROR!", "Pub/Sub 조회 실패 — 로그 확인")]
    finally:
        if used_local_client and local_client:
            try:
                if hasattr(local_client, "close"):
                    local_client.close()
            except Exception:
                pass

# ---------------------------------------------------------------------------
# QWidget 탭 클래스 (fetch_pubsub를 이용해 UI 갱신)
# ---------------------------------------------------------------------------
import os

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem
    from PyQt5.QtCore import QTimer
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_UI_PATH = os.path.join(os.path.dirname(__file__), "pubsub_tab.ui")

if _HAS_QT:
    class PubSubTab(QWidget):
        """Pub/Sub 탭 - 프로세스 간 실시간 이벤트 전달. ZeroMQ와 함께 IPC 역할."""

        def __init__(self, conn_params: dict = None, parent=None):
            super().__init__(parent)
            self._conn_params = conn_params or {}
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[PubSubTab] UI 로드 실패: %s", exc)
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
            rows = fetch_pubsub(host, port, password, timeout)
            self._refresh_table(rows)

        def _refresh_table(self, rows: List[Tuple[str, Any]]) -> None:
            table = getattr(self, "table_pubsub", None)
            if table is None:
                return
            table.setRowCount(len(rows))
            for r, (channel, subs) in enumerate(rows):
                # !ERROR! / !INFO! 토큰 처리
                if channel.startswith("!"):
                    table.setItem(r, 0, QTableWidgetItem(str(subs)))
                    table.setItem(r, 1, QTableWidgetItem("-"))
                    table.setItem(r, 2, QTableWidgetItem("-"))
                else:
                    table.setItem(r, 0, QTableWidgetItem(channel))
                    subs_str = str(subs) if isinstance(subs, int) and subs >= 0 else "-"
                    table.setItem(r, 1, QTableWidgetItem(subs_str))
                    table.setItem(r, 2, QTableWidgetItem("-"))

else:
    class PubSubTab:  # type: ignore[no-redef]
        def __init__(self, conn_params: dict = None, parent=None): pass
        def start_updates(self, interval_ms: int = 5000) -> None: pass
        def stop_updates(self) -> None: pass
