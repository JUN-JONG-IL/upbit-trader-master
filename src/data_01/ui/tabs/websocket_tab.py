# -*- coding: utf-8 -*-
"""Tab 2: WebSocket 수신 (Process 1 모니터링) - v3.0
다중 Redis 키 패턴, 연결 진단, 심볼 더블클릭 상세보기 지원."""
from __future__ import annotations

import asyncio
import logging
import os
import time as _time

logger = logging.getLogger(__name__)


def _load_symbol_limits() -> dict:
    """config.yaml에서 심볼 수 제한 설정 로드.
    실패 시 {'ui_display_limit': 10000, 'db_fallback_limit': 10000, 'redis_scan_count': 10000} 기본값 반환."""
    from pathlib import Path
    _defaults = {"ui_display_limit": 10_000, "db_fallback_limit": 10_000, "redis_scan_count": 10_000}
    try:
        import yaml  # type: ignore
        # src/data_01/ui/tabs/ → parents[3] = src/ → src/core/config/config.yaml
        search_paths = [
            Path(__file__).parents[3] / "core" / "config" / "config.yaml",
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
# UI 심볼 테이블 최대 표시 건수
_MAX_SYMBOL_COUNT: int = _SYMBOL_LIMITS["ui_display_limit"]
# DB 폴백 조회 최대 건수
_DB_FALLBACK_LIMIT: int = _SYMBOL_LIMITS["db_fallback_limit"]
# Redis scan_iter 배치 힌트
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
        """Tab 2: WebSocket 수신 (Process 1 상세 모니터링)"""

        def __init__(self, parent=None):
            super().__init__(parent)
            ui_path = os.path.join(os.path.dirname(__file__), "websocket_tab.ui")
            try:
                uic.loadUi(ui_path, self)
                logger.info("[WebSocketTab] ✅ UI 파일 로드 성공: %s", ui_path)
            except Exception as exc:
                logger.error("[WebSocketTab] ❌ UI 파일 로드 실패: %s", exc)

            # 테이블 다중 행 복사 활성화
            self._setup_table_copy()

            # 버튼 연결
            if hasattr(self, "btn_start_ws"):
                self.btn_start_ws.clicked.connect(self._start_websocket)
            if hasattr(self, "btn_stop_ws"):
                self.btn_stop_ws.clicked.connect(self._stop_websocket)
            if hasattr(self, "btn_refresh_ws"):
                self.btn_refresh_ws.clicked.connect(self._update_status)

            # 심볼 테이블 더블클릭 이벤트
            tbl = getattr(self, "table_ws_status", None)
            if tbl is not None:
                tbl.doubleClicked.connect(self._on_symbol_double_clicked)

            # 1초마다 상태 갱신
            self._timer = QTimer(self)
            self._timer.setInterval(1000)
            self._timer.timeout.connect(self._update_status)
            self._timer.start()

        def start_updates(self, interval_ms: int = 1000) -> None:
            """자동 갱신 시작"""
            self._timer.setInterval(max(1000, int(interval_ms)))
            if not self._timer.isActive():
                self._timer.start()
            logger.info("[WebSocketTab] ✅ 자동 갱신 시작 (%d ms)", interval_ms)

        def stop_updates(self) -> None:
            """자동 갱신 중지"""
            if self._timer.isActive():
                self._timer.stop()
            logger.info("[WebSocketTab] ⏸️ 자동 갱신 중지")

        def _start_websocket(self) -> None:
            """WebSocket 시작 요청"""
            try:
                from ..utils import get_realtime_manager
                mgr = get_realtime_manager()
                if mgr is None:
                    logger.warning("[WebSocketTab] RealtimeManager 없음")
                    return
                limit = getattr(self, "spin_symbol_count", None)
                symbol_count = limit.value() if limit is not None else 20
                logger.info("[WebSocketTab] WebSocket 시작 요청: %d개 심볼", symbol_count)
            except Exception as exc:
                logger.error("[WebSocketTab] WebSocket 시작 실패: %s", exc, exc_info=True)

        def _stop_websocket(self) -> None:
            """WebSocket 중지 요청"""
            try:
                from ..utils import get_realtime_manager
                mgr = get_realtime_manager()
                if mgr is not None and hasattr(mgr, "stop_all"):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(mgr.stop_all())
                    except RuntimeError:
                        asyncio.run(mgr.stop_all())
                logger.info("[WebSocketTab] WebSocket 중지 요청")
            except Exception as exc:
                logger.error("[WebSocketTab] WebSocket 중지 실패: %s", exc)

        def _get_redis_client(self):
            """Redis 클라이언트 반환 (단기 연결)."""
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
            """다중 Redis 키 패턴으로 심볼별 WebSocket 통계 표시."""
            import json as _json
            try:
                table = getattr(self, "table_ws_status", None)
                if table is None:
                    return

                rc = self._get_redis_client()
                if rc is None:
                    self._update_diagnostics(redis_ok=False)
                    table.setRowCount(1)
                    table.setItem(0, 0, QTableWidgetItem("[오류] Redis 미연결"))
                    table.setItem(0, 1, QTableWidgetItem("[오류] 연결 실패"))
                    for col in range(2, table.columnCount()):
                        table.setItem(0, col, QTableWidgetItem("--"))
                    return

                # Redis 연결 확인
                try:
                    rc.ping()
                    redis_ok = True
                except Exception:
                    redis_ok = False
                    self._update_diagnostics(redis_ok=False)
                    return

                self._update_diagnostics(redis_ok=True, rc=rc)

                # 심볼 수집: 다중 패턴 순서대로 시도
                symbols = self._collect_symbols(rc)

                if not symbols:
                    table.setRowCount(1)
                    table.setItem(0, 0, QTableWidgetItem("[대기] WebSocket 미시작"))
                    table.setItem(0, 1, QTableWidgetItem("ℹ️ 심볼 없음"))
                    table.setItem(0, 2, QTableWidgetItem("ws:symbols 키 없음"))
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

                    status_icon = "[수신중]" if status_str == "active" else "[대기]"
                    table.setItem(row_idx, 0, QTableWidgetItem(str(symbol)))
                    table.setItem(row_idx, 1, QTableWidgetItem(status_icon))
                    table.setItem(row_idx, 2, QTableWidgetItem(str(last_time)))
                    table.setItem(row_idx, 3, QTableWidgetItem(f"{recv_count:,}"))
                    table.setItem(row_idx, 4, QTableWidgetItem(f"{comp_ratio:.1f}%"))

                table.resizeColumnsToContents()

                # 상단 통계 레이블 갱신
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
                logger.debug("[WebSocketTab] 상태 갱신 실패: %s", exc)

        def _collect_symbols(self, rc) -> list:
            """다중 Redis 키 패턴으로 심볼 수집.

            순서:
              1. ws:symbols (Set)
              2. ws:stats:* 스캔
              3. pipeline:ws:* 스캔
              4. realtime:recv:* 스캔
              5. candle:recv:* 스캔
              6. DB(candles 테이블 최근 1시간) 폴백
            """
            symbols: list = []

            # 패턴 1: ws:symbols Set
            try:
                symbols = list(rc.smembers("ws:symbols") or [])
            except Exception:
                pass
            if symbols:
                return symbols

            # 패턴 2: ws:stats:* 스캔
            try:
                symbols = [
                    k.replace("ws:stats:", "")
                    for k in rc.scan_iter("ws:stats:*", count=_REDIS_SCAN_COUNT)
                ]
            except Exception:
                pass
            if symbols:
                return symbols

            # 패턴 3: pipeline:ws:* 스캔
            try:
                symbols = [
                    k.replace("pipeline:ws:", "")
                    for k in rc.scan_iter("pipeline:ws:*", count=_REDIS_SCAN_COUNT)
                ]
            except Exception:
                pass
            if symbols:
                return symbols

            # 패턴 4: realtime:recv:* 스캔
            try:
                symbols = [
                    k.replace("realtime:recv:", "")
                    for k in rc.scan_iter("realtime:recv:*", count=_REDIS_SCAN_COUNT)
                ]
            except Exception:
                pass
            if symbols:
                return symbols

            # 패턴 5: candle:recv:* 스캔
            try:
                symbols = [
                    k.replace("candle:recv:", "")
                    for k in rc.scan_iter("candle:recv:*", count=_REDIS_SCAN_COUNT)
                ]
            except Exception:
                pass
            if symbols:
                return symbols

            # 패턴 6: DB 폴백 — candles 테이블 최근 1시간 심볼 조회
            symbols = self._collect_symbols_from_db()
            return symbols

        def _collect_symbols_from_db(self) -> list:
            """DB candles 테이블에서 최근 1시간 심볼 조회 (Redis 폴백용)."""
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
                logger.debug("[WebSocketTab] DB 심볼 폴백 조회 실패: %s", exc)
            return []

        def _get_pipeline_processed(self, rc) -> int:
            """파이프라인 처리 누적 건수 조회 (다중 키 시도).

            키 우선순위:
              1. pipeline:processed_count — 파이프라인 표준 키
              2. pipeline:total_processed — 이전 버전 호환 키
            백엔드가 어느 키도 기록하지 않으면 -1 반환.
            """
            for key in ("pipeline:processed_count", "pipeline:total_processed"):
                try:
                    val = rc.get(key)
                    if val is not None:
                        return int(val)
                except Exception:
                    pass
            return -1  # -1: 키 없음(백엔드 미지원)

        def _get_db_committed(self, rc) -> int:
            """DB 반영 누적 건수 조회 (다중 키 시도).

            키 우선순위:
              1. db:committed_count    — DB 커밋 표준 키
              2. pipeline:db_committed — 파이프라인 내 DB 반영 키
              3. candle:insert_count   — 캔들 INSERT 횟수 키
            백엔드가 어느 키도 기록하지 않으면 -1 반환.
            """
            for key in ("db:committed_count", "pipeline:db_committed", "candle:insert_count"):
                try:
                    val = rc.get(key)
                    if val is not None:
                        return int(val)
                except Exception:
                    pass
            return -1  # -1: 키 없음(백엔드 미지원)

        def _get_total_recv(self, rc) -> int:
            """WebSocket 누적 수신 건수 조회 (WS 전용 키만 사용)."""
            for key in ("ws:total_recv", "ws:recv_count"):
                try:
                    val = rc.get(key)
                    if val is not None:
                        return int(val)
                except Exception:
                    pass
            return 0

        def _get_qps(self, rc) -> int:
            """WebSocket QPS 계산 (WS 전용 키만 사용)."""
            now_sec = int(_time.time())

            # ws:qps:{초} 패턴
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
            """ZeroMQ IPC 상태 조회."""
            try:
                zmq_val = rc.get("zmq:ipc:status")
                if zmq_val:
                    return f"[OK] {zmq_val}"
            except Exception:
                pass
            return "[정상]" if ws_qps > 0 else "[대기]"

        def _update_diagnostics(self, redis_ok: bool, rc=None) -> None:
            """WebSocket 연결 진단 패널 갱신."""
            try:
                # Redis 연결 상태
                lbl_redis = getattr(self, "label_diag_redis", None)
                if lbl_redis is not None:
                    lbl_redis.setText("[OK] 연결됨" if redis_ok else "[오류] 미연결")

                if not redis_ok or rc is None:
                    for name in ("label_diag_process", "label_diag_ws_symbols",
                                 "label_diag_last_activity"):
                        lbl = getattr(self, name, None)
                        if lbl is not None:
                            lbl.setText("-- (Redis 미연결)")
                    return

                # WebSocket 프로세스 PID
                lbl_proc = getattr(self, "label_diag_process", None)
                if lbl_proc is not None:
                    try:
                        pid = rc.get("process1:pid")
                        if pid:
                            lbl_proc.setText(f"[OK] PID {pid}")
                        else:
                            lbl_proc.setText("[대기] 미시작 (PID 없음)")
                    except Exception:
                        lbl_proc.setText("-- (조회 실패)")

                # ws:symbols 키 존재 여부
                lbl_syms = getattr(self, "label_diag_ws_symbols", None)
                if lbl_syms is not None:
                    try:
                        sym_count = rc.scard("ws:symbols")
                        lbl_syms.setText(f"[OK] {sym_count}개" if sym_count else "[경고] 없음 (0개)")
                    except Exception:
                        lbl_syms.setText("-- (조회 실패)")

                # 마지막 활동 시간
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
                            lbl_act.setText(f"{elapsed}초 전")
                        else:
                            lbl_act.setText("-- (수신 없음)")
                    except Exception:
                        lbl_act.setText("-- (조회 실패)")

            except Exception as exc:
                logger.debug("[WebSocketTab] 진단 패널 갱신 실패: %s", exc)

        def _on_symbol_double_clicked(self, index) -> None:
            """심볼 테이블 더블클릭 시 상세 데이터 팝업."""
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

                # Redis에서 상세 데이터 조회
                detail_text = f"심볼: {symbol}\n"
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
                            detail_text += "\n(Redis에 상세 데이터 없음)"
                    except Exception as e:
                        detail_text += f"\n(조회 실패: {e})"
                else:
                    detail_text += "\n(Redis 미연결)"

                dlg = QDialog(self)
                dlg.setWindowTitle(f"{symbol} WebSocket 상세")
                dlg.setMinimumWidth(400)
                layout = QVBoxLayout(dlg)
                txt = QTextEdit()
                txt.setReadOnly(True)
                txt.setPlainText(detail_text)
                layout.addWidget(txt)
                btn_close = QPushButton("✖ 닫기")
                btn_close.clicked.connect(dlg.close)
                layout.addWidget(btn_close)
                dlg.exec_()
            except Exception as exc:
                logger.warning("[WebSocketTab] 심볼 상세 팝업 실패: %s", exc)

        def update_metrics(
            self, ws_qps: int, total_recv: int, delta_ratio: float,
            zmq_status: str = "",
            pipeline_processed: int = -1,
            db_committed: int = -1,
        ) -> None:
            """외부에서 지표 업데이트 (MetricsUpdater → StatusWidget → 여기)

            Args:
                ws_qps: 실수신 QPS (ws:qps:{초} Redis 키 기준)
                total_recv: 누적 수신 건수
                delta_ratio: Delta 압축률 (%)
                zmq_status: ZeroMQ IPC 상태 문자열
                pipeline_processed: 파이프라인 처리 건수 (-1이면 미지원)
                db_committed: DB 반영 건수 (-1이면 미지원)
            """
            try:
                if hasattr(self, "label_ws_qps"):
                    self.label_ws_qps.setText(f"{ws_qps:,} 건/초")
                if hasattr(self, "label_total_recv"):
                    self.label_total_recv.setText(f"{total_recv:,} 건")
                if hasattr(self, "label_delta_ratio"):
                    self.label_delta_ratio.setText(f"{delta_ratio:.1f}%")
                if hasattr(self, "label_ipc_status"):
                    if zmq_status:
                        self.label_ipc_status.setText(zmq_status)
                    else:
                        self.label_ipc_status.setText("[정상]" if ws_qps > 0 else "[대기]")
                # 파이프라인 처리 레이블 (UI에 없으면 무시)
                if hasattr(self, "label_pipeline_processed"):
                    if pipeline_processed >= 0:
                        self.label_pipeline_processed.setText(f"{pipeline_processed:,} 건")
                    else:
                        self.label_pipeline_processed.setText("-- 건")
                # DB 반영 레이블 (UI에 없으면 무시)
                if hasattr(self, "label_db_committed"):
                    if db_committed >= 0:
                        self.label_db_committed.setText(f"{db_committed:,} 건")
                    else:
                        self.label_db_committed.setText("-- 건")
            except Exception as exc:
                logger.debug("[WebSocketTab] update_metrics 실패: %s", exc)

else:
    class WebSocketTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""

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
