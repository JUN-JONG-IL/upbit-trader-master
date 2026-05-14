# -*- coding: utf-8 -*-
"""Tab 2: WebSocket ?˜ì‹  (Process 1 ëª¨ë‹ˆ?°ë§) - v3.0
?¤ì¤‘ Redis ???¨í„´, ?°ê²° ì§„ë‹¨, ?¬ë³¼ ?”ë¸”?´ë¦­ ?ì„¸ë³´ê¸° ì§€??"""
from __future__ import annotations

import asyncio
import logging
import os
import time as _time

logger = logging.getLogger(__name__)


def _load_symbol_limits() -> dict:
    """config.yaml?ì„œ ?¬ë³¼ ???œí•œ ?¤ì • ë¡œë“œ.
    ?¤íŒ¨ ??{'ui_display_limit': 10000, 'db_fallback_limit': 10000, 'redis_scan_count': 10000} ê¸°ë³¸ê°?ë°˜í™˜."""
    from pathlib import Path
    _defaults = {"ui_display_limit": 10_000, "db_fallback_limit": 10_000, "redis_scan_count": 10_000}
    try:
        import yaml  # type: ignore
        # src/data_01/ui/tabs/ ??parents[3] = src/ ??src/01_core/config/config.yaml
        search_paths = [
            Path(__file__).parents[3] / "01_core" / "config" / "config.yaml",
            Path(__file__).parents[4] / "config.yaml",
        ]
        for p in search_paths:
            if p.exists():
                with open(p, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                sym = data.get("symbols", {})
                if isinstance(sym, dict):
                    return {
                        "ui_display_limit": int(sym.get("ui_display_limit", _defaults["ui_display_limit"])),
                        "db_fallback_limit": int(sym.get("db_fallback_limit", _defaults["db_fallback_limit"])),
                        "redis_scan_count": int(sym.get("redis_scan_count", _defaults["redis_scan_count"])),
                    }
    except Exception:
        pass
    return _defaults


_SYMBOL_LIMITS = _load_symbol_limits()
# UI ?¬ë³¼ ?Œì´ë¸?ìµœë? ?œì‹œ ê±´ìˆ˜
_MAX_SYMBOL_COUNT: int = _SYMBOL_LIMITS["ui_display_limit"]
# DB ?´ë°± ì¡°íšŒ ìµœë? ê±´ìˆ˜
_DB_FALLBACK_LIMIT: int = _SYMBOL_LIMITS["db_fallback_limit"]
# Redis scan_iter ë°°ì¹˜ ?ŒíŠ¸
_REDIS_SCAN_COUNT: int = _SYMBOL_LIMITS["redis_scan_count"]

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import (
        QWidget, QTableWidgetItem, QDialog, QVBoxLayout,
        QTextEdit, QPushButton
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

from ._mixins import TableCopyMixin

if _HAS_QT:
    class WebSocketTab(TableCopyMixin, QWidget):
        """Tab 2: WebSocket ?˜ì‹  (Process 1 ?ì„¸ ëª¨ë‹ˆ?°ë§)"""

        def __init__(self, parent=None):
            super().__init__(parent)
            ui_path = os.path.join(os.path.dirname(__file__), "websocket_tab.ui")
            try:
                uic.loadUi(ui_path, self)
                logger.info("[WebSocketTab] ??UI ?Œì¼ ë¡œë“œ ?±ê³µ: %s", ui_path)
            except Exception as exc:
                logger.error("[WebSocketTab] ??UI ?Œì¼ ë¡œë“œ ?¤íŒ¨: %s", exc)

            # ?Œì´ë¸??¤ì¤‘ ??ë³µì‚¬ ?œì„±??
            self._setup_table_copy()

            # ë²„íŠ¼ ?°ê²°
            if hasattr(self, "btn_start_ws"):
                self.btn_start_ws.clicked.connect(self._start_websocket)
            if hasattr(self, "btn_stop_ws"):
                self.btn_stop_ws.clicked.connect(self._stop_websocket)
            if hasattr(self, "btn_refresh_ws"):
                self.btn_refresh_ws.clicked.connect(self._update_status)

            # ?¬ë³¼ ?Œì´ë¸??”ë¸”?´ë¦­ ?´ë²¤??
            tbl = getattr(self, "table_ws_status", None)
            if tbl is not None:
                tbl.doubleClicked.connect(self._on_symbol_double_clicked)

            # 1ì´ˆë§ˆ???íƒœ ê°±ì‹ 
            self._timer = QTimer(self)
            self._timer.setInterval(1000)
            self._timer.timeout.connect(self._update_status)
            self._timer.start()

        def start_updates(self, interval_ms: int = 1000) -> None:
            """?ë™ ê°±ì‹  ?œì‘"""
            self._timer.setInterval(max(1000, int(interval_ms)))
            if not self._timer.isActive():
                self._timer.start()
            logger.info("[WebSocketTab] ???ë™ ê°±ì‹  ?œì‘ (%d ms)", interval_ms)

        def stop_updates(self) -> None:
            """?ë™ ê°±ì‹  ì¤‘ì?"""
            if self._timer.isActive():
                self._timer.stop()
            logger.info("[WebSocketTab] ?¸ï¸ ?ë™ ê°±ì‹  ì¤‘ì?")

        def _start_websocket(self) -> None:
            """WebSocket ?œì‘ ?”ì²­"""
            try:
                from ..utils import get_realtime_manager
                mgr = get_realtime_manager()
                if mgr is None:
                    logger.warning("[WebSocketTab] RealtimeManager ?†ìŒ")
                    return
                limit = getattr(self, "spin_symbol_count", None)
                symbol_count = limit.value() if limit is not None else 20
                logger.info("[WebSocketTab] WebSocket ?œì‘ ?”ì²­: %dê°??¬ë³¼", symbol_count)
            except Exception as exc:
                logger.error("[WebSocketTab] WebSocket ?œì‘ ?¤íŒ¨: %s", exc, exc_info=True)

        def _stop_websocket(self) -> None:
            """WebSocket ì¤‘ì? ?”ì²­"""
            try:
                from ..utils import get_realtime_manager
                mgr = get_realtime_manager()
                if mgr is not None and hasattr(mgr, "stop_all"):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(mgr.stop_all())
                    except RuntimeError:
                        asyncio.run(mgr.stop_all())
                logger.info("[WebSocketTab] WebSocket ì¤‘ì? ?”ì²­")
            except Exception as exc:
                logger.error("[WebSocketTab] WebSocket ì¤‘ì? ?¤íŒ¨: %s", exc)

        def _get_redis_client(self):
            """Redis ?´ë¼?´ì–¸??ë°˜í™˜ (?¨ê¸° ?°ê²°)."""
            try:
                import redis as _redis_mod  # type: ignore
                host = os.getenv("REDIS_HOST", "localhost")
                port = int(os.getenv("REDIS_PORT", "58530"))
                password = os.getenv("REDIS_PASSWORD") or None
                return _redis_mod.Redis(
                    host=host, port=port, password=password,
                    decode_responses=True, socket_connect_timeout=1,
                )
            except Exception:
                return None

        def _update_status(self) -> None:
            """?¤ì¤‘ Redis ???¨í„´?¼ë¡œ ?¬ë³¼ë³?WebSocket ?µê³„ ?œì‹œ."""
            import json as _json
            try:
                table = getattr(self, "table_ws_status", None)
                if table is None:
                    return

                rc = self._get_redis_client()
                if rc is None:
                    self._update_diagnostics(redis_ok=False)
                    table.setRowCount(1)
                    table.setItem(0, 0, QTableWidgetItem("[?¤ë¥˜] Redis ë¯¸ì—°ê²?))
                    table.setItem(0, 1, QTableWidgetItem("[?¤ë¥˜] ?°ê²° ?¤íŒ¨"))
                    for col in range(2, table.columnCount()):
                        table.setItem(0, col, QTableWidgetItem("--"))
                    return

                # Redis ?°ê²° ?•ì¸
                try:
                    rc.ping()
                    redis_ok = True
                except Exception:
                    redis_ok = False
                    self._update_diagnostics(redis_ok=False)
                    return

                self._update_diagnostics(redis_ok=True, rc=rc)

                # ?¬ë³¼ ?˜ì§‘: ?¤ì¤‘ ?¨í„´ ?œì„œ?€ë¡??œë„
                symbols = self._collect_symbols(rc)

                if not symbols:
                    table.setRowCount(1)
                    table.setItem(0, 0, QTableWidgetItem("[?€ê¸? WebSocket ë¯¸ì‹œ??))
                    table.setItem(0, 1, QTableWidgetItem("?¹ï¸ ?¬ë³¼ ?†ìŒ"))
                    table.setItem(0, 2, QTableWidgetItem("ws:symbols ???†ìŒ"))
                    for col in range(3, table.columnCount()):
                        table.setItem(0, col, QTableWidgetItem("--"))
                    return

                symbols = sorted(symbols)[:_MAX_SYMBOL_COUNT]
                table.setRowCount(len(symbols))

                for row_idx, symbol in enumerate(symbols):
                    stats: dict = {}
                    try:
                        raw = rc.get(f"ws:stats:{symbol}")
                        if raw:
                            stats = _json.loads(raw)
                    except Exception:
                        pass

                    status_str = stats.get("status", "unknown")
                    recv_count = stats.get("recv_count", 0)
                    last_time = stats.get("last_time", "--")
                    comp_ratio = stats.get("compression_ratio", 0.0)

                    status_icon = "[?˜ì‹ ì¤?" if status_str == "active" else "[?€ê¸?"
                    table.setItem(row_idx, 0, QTableWidgetItem(str(symbol)))
                    table.setItem(row_idx, 1, QTableWidgetItem(status_icon))
                    table.setItem(row_idx, 2, QTableWidgetItem(str(last_time)))
                    table.setItem(row_idx, 3, QTableWidgetItem(f"{recv_count:,}"))
                    table.setItem(row_idx, 4, QTableWidgetItem(f"{comp_ratio:.1f}%"))

                table.resizeColumnsToContents()

                # ?ë‹¨ ?µê³„ ?ˆì´ë¸?ê°±ì‹ 
                try:
                    total_recv = self._get_total_recv(rc)
                    ws_qps = self._get_qps(rc)
                    pipeline_processed = self._get_pipeline_processed(rc)
                    db_committed = self._get_db_committed(rc)
                    zmq_status = self._get_zmq_status(rc, ws_qps)
                    self.update_metrics(ws_qps, total_recv, 0.0, zmq_status,
                                        pipeline_processed=pipeline_processed,
                                        db_committed=db_committed)
                except Exception:
                    pass

            except Exception as exc:
                logger.debug("[WebSocketTab] ?íƒœ ê°±ì‹  ?¤íŒ¨: %s", exc)

        def _collect_symbols(self, rc) -> list:
            """?¤ì¤‘ Redis ???¨í„´?¼ë¡œ ?¬ë³¼ ?˜ì§‘.

            ?œì„œ:
              1. ws:symbols (Set)
              2. ws:stats:* ?¤ìº”
              3. pipeline:ws:* ?¤ìº”
              4. realtime:recv:* ?¤ìº”
              5. candle:recv:* ?¤ìº”
              6. DB(candles ?Œì´ë¸?ìµœê·¼ 1?œê°„) ?´ë°±
            """
            symbols: list = []

            # ?¨í„´ 1: ws:symbols Set
            try:
                symbols = list(rc.smembers("ws:symbols") or [])
            except Exception:
                pass
            if symbols:
                return symbols

            # ?¨í„´ 2: ws:stats:* ?¤ìº”
            try:
                symbols = [
                    k.replace("ws:stats:", "")
                    for k in rc.scan_iter("ws:stats:*", count=_REDIS_SCAN_COUNT)
                ]
            except Exception:
                pass
            if symbols:
                return symbols

            # ?¨í„´ 3: pipeline:ws:* ?¤ìº”
            try:
                symbols = [
                    k.replace("pipeline:ws:", "")
                    for k in rc.scan_iter("pipeline:ws:*", count=_REDIS_SCAN_COUNT)
                ]
            except Exception:
                pass
            if symbols:
                return symbols

            # ?¨í„´ 4: realtime:recv:* ?¤ìº”
            try:
                symbols = [
                    k.replace("realtime:recv:", "")
                    for k in rc.scan_iter("realtime:recv:*", count=_REDIS_SCAN_COUNT)
                ]
            except Exception:
                pass
            if symbols:
                return symbols

            # ?¨í„´ 5: candle:recv:* ?¤ìº”
            try:
                symbols = [
                    k.replace("candle:recv:", "")
                    for k in rc.scan_iter("candle:recv:*", count=_REDIS_SCAN_COUNT)
                ]
            except Exception:
                pass
            if symbols:
                return symbols

            # ?¨í„´ 6: DB ?´ë°± ??candles ?Œì´ë¸?ìµœê·¼ 1?œê°„ ?¬ë³¼ ì¡°íšŒ
            symbols = self._collect_symbols_from_db()
            return symbols

        def _collect_symbols_from_db(self) -> list:
            """DB candles ?Œì´ë¸”ì—??ìµœê·¼ 1?œê°„ ?¬ë³¼ ì¡°íšŒ (Redis ?´ë°±??."""
            try:
                import psycopg2  # type: ignore
                host = os.getenv("TIMESCALE_HOST", os.getenv("POSTGRES_HOST", "localhost"))
                port = int(os.getenv("TIMESCALE_PORT", os.getenv("POSTGRES_PORT", "5432")))
                dbname = os.getenv("TIMESCALE_DB", os.getenv("POSTGRES_DB", "upbit_trader"))
                user = os.getenv("TIMESCALE_USER", os.getenv("POSTGRES_USER", "postgres"))
                password = os.getenv("TIMESCALE_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))
                conn = psycopg2.connect(
                    host=host, port=port, dbname=dbname, user=user, password=password,
                    connect_timeout=2,
                )
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT DISTINCT symbol FROM candles "
                            "WHERE time > NOW() - INTERVAL '1 hour' "
                            f"ORDER BY symbol LIMIT {_DB_FALLBACK_LIMIT}"
                        )
                        return [row[0] for row in cur.fetchall()]
                finally:
                    conn.close()
            except Exception as exc:
                logger.debug("[WebSocketTab] DB ?¬ë³¼ ?´ë°± ì¡°íšŒ ?¤íŒ¨: %s", exc)
            return []

        def _get_pipeline_processed(self, rc) -> int:
            """?Œì´?„ë¼??ì²˜ë¦¬ ?„ì  ê±´ìˆ˜ ì¡°íšŒ (?¤ì¤‘ ???œë„).

            ???°ì„ ?œìœ„:
              1. pipeline:processed_count ???Œì´?„ë¼???œì? ??
              2. pipeline:total_processed ???´ì „ ë²„ì „ ?¸í™˜ ??
            ë°±ì—”?œê? ?´ëŠ ?¤ë„ ê¸°ë¡?˜ì? ?Šìœ¼ë©?-1 ë°˜í™˜.
            """
            for key in ("pipeline:processed_count", "pipeline:total_processed"):
                try:
                    val = rc.get(key)
                    if val is not None:
                        return int(val)
                except Exception:
                    pass
            return -1  # -1: ???†ìŒ(ë°±ì—”??ë¯¸ì???

        def _get_db_committed(self, rc) -> int:
            """DB ë°˜ì˜ ?„ì  ê±´ìˆ˜ ì¡°íšŒ (?¤ì¤‘ ???œë„).

            ???°ì„ ?œìœ„:
              1. db:committed_count    ??DB ì»¤ë°‹ ?œì? ??
              2. pipeline:db_committed ???Œì´?„ë¼????DB ë°˜ì˜ ??
              3. candle:insert_count   ??ìº”ë“¤ INSERT ?Ÿìˆ˜ ??
            ë°±ì—”?œê? ?´ëŠ ?¤ë„ ê¸°ë¡?˜ì? ?Šìœ¼ë©?-1 ë°˜í™˜.
            """
            for key in ("db:committed_count", "pipeline:db_committed", "candle:insert_count"):
                try:
                    val = rc.get(key)
                    if val is not None:
                        return int(val)
                except Exception:
                    pass
            return -1  # -1: ???†ìŒ(ë°±ì—”??ë¯¸ì???

        def _get_total_recv(self, rc) -> int:
            """WebSocket ?„ì  ?˜ì‹  ê±´ìˆ˜ ì¡°íšŒ (WS ?„ìš© ?¤ë§Œ ?¬ìš©)."""
            for key in ("ws:total_recv", "ws:recv_count"):
                try:
                    val = rc.get(key)
                    if val is not None:
                        return int(val)
                except Exception:
                    pass
            return 0

        def _get_qps(self, rc) -> int:
            """WebSocket QPS ê³„ì‚° (WS ?„ìš© ?¤ë§Œ ?¬ìš©)."""
            now_sec = int(_time.time())

            # ws:qps:{ì´? ?¨í„´
            qps_vals = []
            for sec_offset in range(5):
                try:
                    v = rc.get(f"ws:qps:{now_sec - sec_offset}")
                    if v:
                        qps_vals.append(int(v))
                except Exception:
                    pass

            if qps_vals:
                return int(sum(qps_vals) / len(qps_vals))
            return 0

        def _get_zmq_status(self, rc, ws_qps: int) -> str:
            """ZeroMQ IPC ?íƒœ ì¡°íšŒ."""
            try:
                zmq_val = rc.get("zmq:ipc:status")
                if zmq_val:
                    return f"[OK] {zmq_val}"
            except Exception:
                pass
            return "[?•ìƒ]" if ws_qps > 0 else "[?€ê¸?"

        def _update_diagnostics(self, redis_ok: bool, rc=None) -> None:
            """WebSocket ?°ê²° ì§„ë‹¨ ?¨ë„ ê°±ì‹ ."""
            try:
                # Redis ?°ê²° ?íƒœ
                lbl_redis = getattr(self, "label_diag_redis", None)
                if lbl_redis is not None:
                    lbl_redis.setText("[OK] ?°ê²°?? if redis_ok else "[?¤ë¥˜] ë¯¸ì—°ê²?)

                if not redis_ok or rc is None:
                    for name in ("label_diag_process", "label_diag_ws_symbols",
                                 "label_diag_last_activity"):
                        lbl = getattr(self, name, None)
                        if lbl is not None:
                            lbl.setText("-- (Redis ë¯¸ì—°ê²?")
                    return

                # WebSocket ?„ë¡œ?¸ìŠ¤ PID
                lbl_proc = getattr(self, "label_diag_process", None)
                if lbl_proc is not None:
                    try:
                        pid = rc.get("process1:pid")
                        if pid:
                            lbl_proc.setText(f"[OK] PID {pid}")
                        else:
                            lbl_proc.setText("[?€ê¸? ë¯¸ì‹œ??(PID ?†ìŒ)")
                    except Exception:
                        lbl_proc.setText("-- (ì¡°íšŒ ?¤íŒ¨)")

                # ws:symbols ??ì¡´ì¬ ?¬ë?
                lbl_syms = getattr(self, "label_diag_ws_symbols", None)
                if lbl_syms is not None:
                    try:
                        sym_count = rc.scard("ws:symbols")
                        lbl_syms.setText(f"[OK] {sym_count}ê°? if sym_count else "[ê²½ê³ ] ?†ìŒ (0ê°?")
                    except Exception:
                        lbl_syms.setText("-- (ì¡°íšŒ ?¤íŒ¨)")

                # ë§ˆì?ë§??œë™ ?œê°„
                lbl_act = getattr(self, "label_diag_last_activity", None)
                if lbl_act is not None:
                    try:
                        now_sec = int(_time.time())
                        last_ts = None
                        for sec_offset in range(60):
                            v = rc.get(f"ws:qps:{now_sec - sec_offset}")
                            if v:
                                last_ts = now_sec - sec_offset
                                break
                        if last_ts:
                            elapsed = now_sec - last_ts
                            lbl_act.setText(f"{elapsed}ì´???)
                        else:
                            lbl_act.setText("-- (?˜ì‹  ?†ìŒ)")
                    except Exception:
                        lbl_act.setText("-- (ì¡°íšŒ ?¤íŒ¨)")

            except Exception as exc:
                logger.debug("[WebSocketTab] ì§„ë‹¨ ?¨ë„ ê°±ì‹  ?¤íŒ¨: %s", exc)

        def _on_symbol_double_clicked(self, index) -> None:
            """?¬ë³¼ ?Œì´ë¸??”ë¸”?´ë¦­ ???ì„¸ ?°ì´???ì—…."""
            import json as _json
            tbl = getattr(self, "table_ws_status", None)
            if tbl is None:
                return
            row = index.row()
            try:
                symbol_item = tbl.item(row, 0)
                if symbol_item is None:
                    return
                symbol = symbol_item.text()

                # Redis?ì„œ ?ì„¸ ?°ì´??ì¡°íšŒ
                detail_text = f"?¬ë³¼: {symbol}\n"
                rc = self._get_redis_client()
                if rc:
                    try:
                        raw = rc.get(f"ws:stats:{symbol}")
                        if raw:
                            stats = _json.loads(raw)
                            detail_text += f"\n=== ws:stats:{symbol} ===\n"
                            for k, v in stats.items():
                                detail_text += f"  {k}: {v}\n"
                        else:
                            detail_text += "\n(Redis???ì„¸ ?°ì´???†ìŒ)"
                    except Exception as e:
                        detail_text += f"\n(ì¡°íšŒ ?¤íŒ¨: {e})"
                else:
                    detail_text += "\n(Redis ë¯¸ì—°ê²?"

                dlg = QDialog(self)
                dlg.setWindowTitle(f"{symbol} WebSocket ?ì„¸")
                dlg.setMinimumWidth(400)
                layout = QVBoxLayout(dlg)
                txt = QTextEdit()
                txt.setReadOnly(True)
                txt.setPlainText(detail_text)
                layout.addWidget(txt)
                btn_close = QPushButton("???«ê¸°")
                btn_close.clicked.connect(dlg.close)
                layout.addWidget(btn_close)
                dlg.exec_()
            except Exception as exc:
                logger.warning("[WebSocketTab] ?¬ë³¼ ?ì„¸ ?ì—… ?¤íŒ¨: %s", exc)

        def update_metrics(
            self, ws_qps: int, total_recv: int, delta_ratio: float,
            zmq_status: str = "",
            pipeline_processed: int = -1,
            db_committed: int = -1,
        ) -> None:
            """?¸ë??ì„œ ì§€???…ë°?´íŠ¸ (MetricsUpdater ??StatusWidget ???¬ê¸°)

            Args:
                ws_qps: ?¤ìˆ˜??QPS (ws:qps:{ì´? Redis ??ê¸°ì?)
                total_recv: ?„ì  ?˜ì‹  ê±´ìˆ˜
                delta_ratio: Delta ?•ì¶•ë¥?(%)
                zmq_status: ZeroMQ IPC ?íƒœ ë¬¸ì??
                pipeline_processed: ?Œì´?„ë¼??ì²˜ë¦¬ ê±´ìˆ˜ (-1?´ë©´ ë¯¸ì???
                db_committed: DB ë°˜ì˜ ê±´ìˆ˜ (-1?´ë©´ ë¯¸ì???
            """
            try:
                if hasattr(self, "label_ws_qps"):
                    self.label_ws_qps.setText(f"{ws_qps:,} ê±?ì´?)
                if hasattr(self, "label_total_recv"):
                    self.label_total_recv.setText(f"{total_recv:,} ê±?)
                if hasattr(self, "label_delta_ratio"):
                    self.label_delta_ratio.setText(f"{delta_ratio:.1f}%")
                if hasattr(self, "label_ipc_status"):
                    if zmq_status:
                        self.label_ipc_status.setText(zmq_status)
                    else:
                        self.label_ipc_status.setText("[?•ìƒ]" if ws_qps > 0 else "[?€ê¸?")
                # ?Œì´?„ë¼??ì²˜ë¦¬ ?ˆì´ë¸?(UI???†ìœ¼ë©?ë¬´ì‹œ)
                if hasattr(self, "label_pipeline_processed"):
                    if pipeline_processed >= 0:
                        self.label_pipeline_processed.setText(f"{pipeline_processed:,} ê±?)
                    else:
                        self.label_pipeline_processed.setText("-- ê±?)
                # DB ë°˜ì˜ ?ˆì´ë¸?(UI???†ìœ¼ë©?ë¬´ì‹œ)
                if hasattr(self, "label_db_committed"):
                    if db_committed >= 0:
                        self.label_db_committed.setText(f"{db_committed:,} ê±?)
                    else:
                        self.label_db_committed.setText("-- ê±?)
            except Exception as exc:
                logger.debug("[WebSocketTab] update_metrics ?¤íŒ¨: %s", exc)

else:
    class WebSocketTab:  # type: ignore[no-redef]
        """PyQt5 ë¯¸ì„¤ì¹????¬ìš©?˜ëŠ” ?”ë? ?´ë˜??""

        def __init__(self, parent=None):
            pass

        def start_updates(self, interval_ms: int = 1000) -> None:
            pass

        def stop_updates(self) -> None:
            pass

        def update_metrics(
            self, ws_qps: int, total_recv: int, delta_ratio: float,
            zmq_status: str = "",
            pipeline_processed: int = -1,
            db_committed: int = -1,
        ) -> None:
            pass

