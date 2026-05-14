# -*- coding: utf-8 -*-
"""Tab 2: WebSocket ?섏떊 (Process 1 紐⑤땲?곕쭅) - v3.0
?ㅼ쨷 Redis ???⑦꽩, ?곌껐 吏꾨떒, ?щ낵 ?붾툝?대┃ ?곸꽭蹂닿린 吏??"""
from __future__ import annotations

import asyncio
import logging
import os
import time as _time

logger = logging.getLogger(__name__)


def _load_symbol_limits() -> dict:
    """config.yaml?먯꽌 ?щ낵 ???쒗븳 ?ㅼ젙 濡쒕뱶.
    ?ㅽ뙣 ??{'ui_display_limit': 10000, 'db_fallback_limit': 10000, 'redis_scan_count': 10000} 湲곕낯媛?諛섑솚."""
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
# UI ?щ낵 ?뚯씠釉?理쒕? ?쒖떆 嫄댁닔
_MAX_SYMBOL_COUNT: int = _SYMBOL_LIMITS["ui_display_limit"]
# DB ?대갚 議고쉶 理쒕? 嫄댁닔
_DB_FALLBACK_LIMIT: int = _SYMBOL_LIMITS["db_fallback_limit"]
# Redis scan_iter 諛곗튂 ?뚰듃
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
        """Tab 2: WebSocket ?섏떊 (Process 1 ?곸꽭 紐⑤땲?곕쭅)"""

        def __init__(self, parent=None):
            super().__init__(parent)
            ui_path = os.path.join(os.path.dirname(__file__), "websocket_tab.ui")
            try:
                uic.loadUi(ui_path, self)
                logger.info("[WebSocketTab] ??UI ?뚯씪 濡쒕뱶 ?깃났: %s", ui_path)
            except Exception as exc:
                logger.error("[WebSocketTab] ??UI ?뚯씪 濡쒕뱶 ?ㅽ뙣: %s", exc)

            # ?뚯씠釉??ㅼ쨷 ??蹂듭궗 ?쒖꽦??
            self._setup_table_copy()

            # 踰꾪듉 ?곌껐
            if hasattr(self, "btn_start_ws"):
                self.btn_start_ws.clicked.connect(self._start_websocket)
            if hasattr(self, "btn_stop_ws"):
                self.btn_stop_ws.clicked.connect(self._stop_websocket)
            if hasattr(self, "btn_refresh_ws"):
                self.btn_refresh_ws.clicked.connect(self._update_status)

            # ?щ낵 ?뚯씠釉??붾툝?대┃ ?대깽??
            tbl = getattr(self, "table_ws_status", None)
            if tbl is not None:
                tbl.doubleClicked.connect(self._on_symbol_double_clicked)

            # 1珥덈쭏???곹깭 媛깆떊
            self._timer = QTimer(self)
            self._timer.setInterval(1000)
            self._timer.timeout.connect(self._update_status)
            self._timer.start()

        def start_updates(self, interval_ms: int = 1000) -> None:
            """?먮룞 媛깆떊 ?쒖옉"""
            self._timer.setInterval(max(1000, int(interval_ms)))
            if not self._timer.isActive():
                self._timer.start()
            logger.info("[WebSocketTab] ???먮룞 媛깆떊 ?쒖옉 (%d ms)", interval_ms)

        def stop_updates(self) -> None:
            """?먮룞 媛깆떊 以묒?"""
            if self._timer.isActive():
                self._timer.stop()
            logger.info("[WebSocketTab] ?몌툘 ?먮룞 媛깆떊 以묒?")

        def _start_websocket(self) -> None:
            """WebSocket ?쒖옉 ?붿껌"""
            try:
                from ..utils import get_realtime_manager
                mgr = get_realtime_manager()
                if mgr is None:
                    logger.warning("[WebSocketTab] RealtimeManager ?놁쓬")
                    return
                limit = getattr(self, "spin_symbol_count", None)
                symbol_count = limit.value() if limit is not None else 20
                logger.info("[WebSocketTab] WebSocket ?쒖옉 ?붿껌: %d媛??щ낵", symbol_count)
            except Exception as exc:
                logger.error("[WebSocketTab] WebSocket ?쒖옉 ?ㅽ뙣: %s", exc, exc_info=True)

        def _stop_websocket(self) -> None:
            """WebSocket 以묒? ?붿껌"""
            try:
                from ..utils import get_realtime_manager
                mgr = get_realtime_manager()
                if mgr is not None and hasattr(mgr, "stop_all"):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(mgr.stop_all())
                    except RuntimeError:
                        asyncio.run(mgr.stop_all())
                logger.info("[WebSocketTab] WebSocket 以묒? ?붿껌")
            except Exception as exc:
                logger.error("[WebSocketTab] WebSocket 以묒? ?ㅽ뙣: %s", exc)

        def _get_redis_client(self):
            """Redis ?대씪?댁뼵??諛섑솚 (?④린 ?곌껐)."""
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
            """?ㅼ쨷 Redis ???⑦꽩?쇰줈 ?щ낵蹂?WebSocket ?듦퀎 ?쒖떆."""
            import json as _json
            try:
                table = getattr(self, "table_ws_status", None)
                if table is None:
                    return

                rc = self._get_redis_client()
                if rc is None:
                    self._update_diagnostics(redis_ok=False)
                    table.setRowCount(1)
                    table.setItem(0, 0, QTableWidgetItem("[?ㅻ쪟] Redis 誘몄뿰寃?))
                    table.setItem(0, 1, QTableWidgetItem("[?ㅻ쪟] ?곌껐 ?ㅽ뙣"))
                    for col in range(2, table.columnCount()):
                        table.setItem(0, col, QTableWidgetItem("--"))
                    return

                # Redis ?곌껐 ?뺤씤
                try:
                    rc.ping()
                    redis_ok = True
                except Exception:
                    redis_ok = False
                    self._update_diagnostics(redis_ok=False)
                    return

                self._update_diagnostics(redis_ok=True, rc=rc)

                # ?щ낵 ?섏쭛: ?ㅼ쨷 ?⑦꽩 ?쒖꽌?濡??쒕룄
                symbols = self._collect_symbols(rc)

                if not symbols:
                    table.setRowCount(1)
                    table.setItem(0, 0, QTableWidgetItem("[?湲? WebSocket 誘몄떆??))
                    table.setItem(0, 1, QTableWidgetItem("?뱄툘 ?щ낵 ?놁쓬"))
                    table.setItem(0, 2, QTableWidgetItem("ws:symbols ???놁쓬"))
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

                    status_icon = "[?섏떊以?" if status_str == "active" else "[?湲?"
                    table.setItem(row_idx, 0, QTableWidgetItem(str(symbol)))
                    table.setItem(row_idx, 1, QTableWidgetItem(status_icon))
                    table.setItem(row_idx, 2, QTableWidgetItem(str(last_time)))
                    table.setItem(row_idx, 3, QTableWidgetItem(f"{recv_count:,}"))
                    table.setItem(row_idx, 4, QTableWidgetItem(f"{comp_ratio:.1f}%"))

                table.resizeColumnsToContents()

                # ?곷떒 ?듦퀎 ?덉씠釉?媛깆떊
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
                logger.debug("[WebSocketTab] ?곹깭 媛깆떊 ?ㅽ뙣: %s", exc)

        def _collect_symbols(self, rc) -> list:
            """?ㅼ쨷 Redis ???⑦꽩?쇰줈 ?щ낵 ?섏쭛.

            ?쒖꽌:
              1. ws:symbols (Set)
              2. ws:stats:* ?ㅼ틪
              3. pipeline:ws:* ?ㅼ틪
              4. realtime:recv:* ?ㅼ틪
              5. candle:recv:* ?ㅼ틪
              6. DB(candles ?뚯씠釉?理쒓렐 1?쒓컙) ?대갚
            """
            symbols: list = []

            # ?⑦꽩 1: ws:symbols Set
            try:
                symbols = list(rc.smembers("ws:symbols") or [])
            except Exception:
                pass
            if symbols:
                return symbols

            # ?⑦꽩 2: ws:stats:* ?ㅼ틪
            try:
                symbols = [
                    k.replace("ws:stats:", "")
                    for k in rc.scan_iter("ws:stats:*", count=_REDIS_SCAN_COUNT)
                ]
            except Exception:
                pass
            if symbols:
                return symbols

            # ?⑦꽩 3: pipeline:ws:* ?ㅼ틪
            try:
                symbols = [
                    k.replace("pipeline:ws:", "")
                    for k in rc.scan_iter("pipeline:ws:*", count=_REDIS_SCAN_COUNT)
                ]
            except Exception:
                pass
            if symbols:
                return symbols

            # ?⑦꽩 4: realtime:recv:* ?ㅼ틪
            try:
                symbols = [
                    k.replace("realtime:recv:", "")
                    for k in rc.scan_iter("realtime:recv:*", count=_REDIS_SCAN_COUNT)
                ]
            except Exception:
                pass
            if symbols:
                return symbols

            # ?⑦꽩 5: candle:recv:* ?ㅼ틪
            try:
                symbols = [
                    k.replace("candle:recv:", "")
                    for k in rc.scan_iter("candle:recv:*", count=_REDIS_SCAN_COUNT)
                ]
            except Exception:
                pass
            if symbols:
                return symbols

            # ?⑦꽩 6: DB ?대갚 ??candles ?뚯씠釉?理쒓렐 1?쒓컙 ?щ낵 議고쉶
            symbols = self._collect_symbols_from_db()
            return symbols

        def _collect_symbols_from_db(self) -> list:
            """DB candles ?뚯씠釉붿뿉??理쒓렐 1?쒓컙 ?щ낵 議고쉶 (Redis ?대갚??."""
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
                logger.debug("[WebSocketTab] DB ?щ낵 ?대갚 議고쉶 ?ㅽ뙣: %s", exc)
            return []

        def _get_pipeline_processed(self, rc) -> int:
            """?뚯씠?꾨씪??泥섎━ ?꾩쟻 嫄댁닔 議고쉶 (?ㅼ쨷 ???쒕룄).

            ???곗꽑?쒖쐞:
              1. pipeline:processed_count ???뚯씠?꾨씪???쒖? ??
              2. pipeline:total_processed ???댁쟾 踰꾩쟾 ?명솚 ??
            諛깆뿏?쒓? ?대뒓 ?ㅻ룄 湲곕줉?섏? ?딆쑝硫?-1 諛섑솚.
            """
            for key in ("pipeline:processed_count", "pipeline:total_processed"):
                try:
                    val = rc.get(key)
                    if val is not None:
                        return int(val)
                except Exception:
                    pass
            return -1  # -1: ???놁쓬(諛깆뿏??誘몄???

        def _get_db_committed(self, rc) -> int:
            """DB 諛섏쁺 ?꾩쟻 嫄댁닔 議고쉶 (?ㅼ쨷 ???쒕룄).

            ???곗꽑?쒖쐞:
              1. db:committed_count    ??DB 而ㅻ컠 ?쒖? ??
              2. pipeline:db_committed ???뚯씠?꾨씪????DB 諛섏쁺 ??
              3. candle:insert_count   ??罹붾뱾 INSERT ?잛닔 ??
            諛깆뿏?쒓? ?대뒓 ?ㅻ룄 湲곕줉?섏? ?딆쑝硫?-1 諛섑솚.
            """
            for key in ("db:committed_count", "pipeline:db_committed", "candle:insert_count"):
                try:
                    val = rc.get(key)
                    if val is not None:
                        return int(val)
                except Exception:
                    pass
            return -1  # -1: ???놁쓬(諛깆뿏??誘몄???

        def _get_total_recv(self, rc) -> int:
            """WebSocket ?꾩쟻 ?섏떊 嫄댁닔 議고쉶 (WS ?꾩슜 ?ㅻ쭔 ?ъ슜)."""
            for key in ("ws:total_recv", "ws:recv_count"):
                try:
                    val = rc.get(key)
                    if val is not None:
                        return int(val)
                except Exception:
                    pass
            return 0

        def _get_qps(self, rc) -> int:
            """WebSocket QPS 怨꾩궛 (WS ?꾩슜 ?ㅻ쭔 ?ъ슜)."""
            now_sec = int(_time.time())

            # ws:qps:{珥? ?⑦꽩
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
            """ZeroMQ IPC ?곹깭 議고쉶."""
            try:
                zmq_val = rc.get("zmq:ipc:status")
                if zmq_val:
                    return f"[OK] {zmq_val}"
            except Exception:
                pass
            return "[?뺤긽]" if ws_qps > 0 else "[?湲?"

        def _update_diagnostics(self, redis_ok: bool, rc=None) -> None:
            """WebSocket ?곌껐 吏꾨떒 ?⑤꼸 媛깆떊."""
            try:
                # Redis ?곌껐 ?곹깭
                lbl_redis = getattr(self, "label_diag_redis", None)
                if lbl_redis is not None:
                    lbl_redis.setText("[OK] ?곌껐?? if redis_ok else "[?ㅻ쪟] 誘몄뿰寃?)

                if not redis_ok or rc is None:
                    for name in ("label_diag_process", "label_diag_ws_symbols",
                                 "label_diag_last_activity"):
                        lbl = getattr(self, name, None)
                        if lbl is not None:
                            lbl.setText("-- (Redis 誘몄뿰寃?")
                    return

                # WebSocket ?꾨줈?몄뒪 PID
                lbl_proc = getattr(self, "label_diag_process", None)
                if lbl_proc is not None:
                    try:
                        pid = rc.get("process1:pid")
                        if pid:
                            lbl_proc.setText(f"[OK] PID {pid}")
                        else:
                            lbl_proc.setText("[?湲? 誘몄떆??(PID ?놁쓬)")
                    except Exception:
                        lbl_proc.setText("-- (議고쉶 ?ㅽ뙣)")

                # ws:symbols ??議댁옱 ?щ?
                lbl_syms = getattr(self, "label_diag_ws_symbols", None)
                if lbl_syms is not None:
                    try:
                        sym_count = rc.scard("ws:symbols")
                        lbl_syms.setText(f"[OK] {sym_count}媛? if sym_count else "[寃쎄퀬] ?놁쓬 (0媛?")
                    except Exception:
                        lbl_syms.setText("-- (議고쉶 ?ㅽ뙣)")

                # 留덉?留??쒕룞 ?쒓컙
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
                            lbl_act.setText(f"{elapsed}珥???)
                        else:
                            lbl_act.setText("-- (?섏떊 ?놁쓬)")
                    except Exception:
                        lbl_act.setText("-- (議고쉶 ?ㅽ뙣)")

            except Exception as exc:
                logger.debug("[WebSocketTab] 吏꾨떒 ?⑤꼸 媛깆떊 ?ㅽ뙣: %s", exc)

        def _on_symbol_double_clicked(self, index) -> None:
            """?щ낵 ?뚯씠釉??붾툝?대┃ ???곸꽭 ?곗씠???앹뾽."""
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

                # Redis?먯꽌 ?곸꽭 ?곗씠??議고쉶
                detail_text = f"?щ낵: {symbol}\n"
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
                            detail_text += "\n(Redis???곸꽭 ?곗씠???놁쓬)"
                    except Exception as e:
                        detail_text += f"\n(議고쉶 ?ㅽ뙣: {e})"
                else:
                    detail_text += "\n(Redis 誘몄뿰寃?"

                dlg = QDialog(self)
                dlg.setWindowTitle(f"{symbol} WebSocket ?곸꽭")
                dlg.setMinimumWidth(400)
                layout = QVBoxLayout(dlg)
                txt = QTextEdit()
                txt.setReadOnly(True)
                txt.setPlainText(detail_text)
                layout.addWidget(txt)
                btn_close = QPushButton("???リ린")
                btn_close.clicked.connect(dlg.close)
                layout.addWidget(btn_close)
                dlg.exec_()
            except Exception as exc:
                logger.warning("[WebSocketTab] ?щ낵 ?곸꽭 ?앹뾽 ?ㅽ뙣: %s", exc)

        def update_metrics(
            self, ws_qps: int, total_recv: int, delta_ratio: float,
            zmq_status: str = "",
            pipeline_processed: int = -1,
            db_committed: int = -1,
        ) -> None:
            """?몃??먯꽌 吏???낅뜲?댄듃 (MetricsUpdater ??StatusWidget ???ш린)

            Args:
                ws_qps: ?ㅼ닔??QPS (ws:qps:{珥? Redis ??湲곗?)
                total_recv: ?꾩쟻 ?섏떊 嫄댁닔
                delta_ratio: Delta ?뺤텞瑜?(%)
                zmq_status: ZeroMQ IPC ?곹깭 臾몄옄??
                pipeline_processed: ?뚯씠?꾨씪??泥섎━ 嫄댁닔 (-1?대㈃ 誘몄???
                db_committed: DB 諛섏쁺 嫄댁닔 (-1?대㈃ 誘몄???
            """
            try:
                if hasattr(self, "label_ws_qps"):
                    self.label_ws_qps.setText(f"{ws_qps:,} 嫄?珥?)
                if hasattr(self, "label_total_recv"):
                    self.label_total_recv.setText(f"{total_recv:,} 嫄?)
                if hasattr(self, "label_delta_ratio"):
                    self.label_delta_ratio.setText(f"{delta_ratio:.1f}%")
                if hasattr(self, "label_ipc_status"):
                    if zmq_status:
                        self.label_ipc_status.setText(zmq_status)
                    else:
                        self.label_ipc_status.setText("[?뺤긽]" if ws_qps > 0 else "[?湲?")
                # ?뚯씠?꾨씪??泥섎━ ?덉씠釉?(UI???놁쑝硫?臾댁떆)
                if hasattr(self, "label_pipeline_processed"):
                    if pipeline_processed >= 0:
                        self.label_pipeline_processed.setText(f"{pipeline_processed:,} 嫄?)
                    else:
                        self.label_pipeline_processed.setText("-- 嫄?)
                # DB 諛섏쁺 ?덉씠釉?(UI???놁쑝硫?臾댁떆)
                if hasattr(self, "label_db_committed"):
                    if db_committed >= 0:
                        self.label_db_committed.setText(f"{db_committed:,} 嫄?)
                    else:
                        self.label_db_committed.setText("-- 嫄?)
            except Exception as exc:
                logger.debug("[WebSocketTab] update_metrics ?ㅽ뙣: %s", exc)

else:
    class WebSocketTab:  # type: ignore[no-redef]
        """PyQt5 誘몄꽕移????ъ슜?섎뒗 ?붾? ?대옒??""

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

