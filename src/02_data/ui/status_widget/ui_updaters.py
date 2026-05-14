# -*- coding: utf-8 -*-
"""
UI 갱신 Mixin (ui_updaters.py)

- flow 상태 레이블, 통신 테이블, 업타임, 상태바, 레이아웃 최적화 등
- TF 탭 연결(update_tf_tabs_summary, append_tf_row 등)
- main.py의 UI 로그 전달(register_ui_log_consumer)과 안전하게 연동 (동적 import)
- 고빈도 입력 처리를 위한 버퍼링/배치 업데이트 추가 (flush 주기: 기본 100ms)
- 진단용 로그 추가: _flush_ui_buffers 호출/버퍼 크기 확인 가능
"""
from __future__ import annotations

import importlib
import logging
import time
import threading
from datetime import datetime
from typing import Dict, Optional, Sequence, Tuple, List

logger = logging.getLogger(__name__)

MAX_COMM_ROWS: int = 500  # 통신 테이블 최대 행 수
MAX_TF_ROWS: int = 1000   # TF 테이블 최대 행 수

# UI에 정의된 타임프레임 순서 (UI 탭 순서와 일치해야 함)
TF_LIST: Tuple[str, ...] = ("all", "1m", "5m", "15m", "1h", "4h", "1d")

# PyQt5 import guard
try:
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QFont
    from PyQt5.QtWidgets import (
        QApplication,
        QCheckBox,
        QHeaderView,
        QProgressBar,
        QTableWidgetItem,
        QAbstractItemView,
    )
    _HAS_QT = True
except Exception:
    _HAS_QT = False


if _HAS_QT:
    class UIUpdatersMixin:
        """UI 직접 갱신 Mixin.

        - StatusWidget 등과 믹스인되어 사용됩니다.
        - main.register_ui_log_consumer 에 런타임으로 안전하게 등록 시도합니다.
        - 고빈도 데이터 처리를 위해 내부 버퍼에 수집한 뒤 UI 스레드 타이머로 일괄 반영합니다.
        """

        # flush 주기(밀리초) — 필요 시 설정화 가능
        UI_FLUSH_INTERVAL_MS = 100

        def __init__(self, *args, **kwargs):
            # 믹스인 안전 초기화
            try:
                super().__init__(*args, **kwargs)
            except Exception:
                pass

            # UI 로그 등록 플래그가 상위에서 설정되어 있을 수 있음
            self._ui_log_registered = getattr(self, "_ui_log_registered", False)

            # --- 버퍼/락/flush 타이머 초기화 ---
            if not hasattr(self, "_ui_buffer_lock"):
                self._ui_buffer_lock = threading.Lock()
            if not hasattr(self, "_comm_buffer"):
                self._comm_buffer: List[Sequence[str]] = []
            if not hasattr(self, "_tf_buffers"):
                self._tf_buffers: Dict[str, List[Sequence[str]]] = {tf: [] for tf in TF_LIST}

            # flush 타이머: UI 스레드에서 주기적으로 버퍼를 비움
            try:
                if not hasattr(self, "_ui_flush_timer") or getattr(self, "_ui_flush_timer", None) is None:
                    self._ui_flush_timer = QTimer(self)
                    self._ui_flush_timer.setInterval(self.UI_FLUSH_INTERVAL_MS)
                    self._ui_flush_timer.timeout.connect(self._flush_ui_buffers)
                    try:
                        self._ui_flush_timer.start()
                        logger.debug("[UIUpdaters] ui_flush_timer started (interval=%dms)", self.UI_FLUSH_INTERVAL_MS)
                    except Exception:
                        logger.debug("[UIUpdaters] ui_flush_timer start failed", exc_info=True)
            except Exception:
                logger.debug("[UIUpdaters] ui_flush_timer init failed", exc_info=True)

        # --------------------------
        # 레이아웃 초기화 / 최적화
        # --------------------------
        def _optimize_layout(self) -> None:
            """레이아웃 및 위젯 초기 설정.

            - flow 레이블 폰트/워드래핑 설정
            - table_comm 및 table_tf_* 헤더/스크롤 모드 설정
            - 그룹박스 마진 정리
            - 가능한 경우 main.register_ui_log_consumer에 콜백 등록 시도
            """
            try:
                # flow labels 설정
                flow_labels = [
                    "label_flow_websocket",
                    "label_flow_pipeline",
                    "label_flow_db",
                    "label_flow_ui",
                ]
                font = QFont("맑은 고딕", 9)
                for name in flow_labels:
                    lbl = getattr(self, name, None)
                    if lbl is None:
                        continue
                    try:
                        lbl.setWordWrap(True)
                        lbl.setMinimumHeight(30)
                        lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                        lbl.setFont(font)
                    except Exception:
                        logger.debug("[UIUpdaters] flow label init failed: %s", name)

                # table_comm 초기화
                tbl = getattr(self, "table_comm", None)
                if tbl is not None:
                    try:
                        header = tbl.horizontalHeader()
                        for col in range(tbl.columnCount()):
                            header.setSectionResizeMode(col, QHeaderView.Interactive)
                        if tbl.columnCount() >= 5:
                            header.resizeSection(0, 160)
                            header.resizeSection(1, 80)
                            header.resizeSection(2, 140)
                            header.resizeSection(3, 360)
                            header.resizeSection(4, 80)
                        header.setStretchLastSection(False)
                        tbl.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
                        tbl.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                        tbl.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                        try:
                            tbl.setAlternatingRowColors(True)
                        except Exception:
                            pass
                    except Exception:
                        logger.debug("[UIUpdaters] table_comm header init failed")

                # TF 테이블 초기화
                for tf in TF_LIST:
                    tbl_name = f"table_tf_{tf}"
                    tbl_tf = getattr(self, tbl_name, None)
                    if tbl_tf is None:
                        continue
                    try:
                        th = tbl_tf.horizontalHeader()
                        for c in range(tbl_tf.columnCount()):
                            th.setSectionResizeMode(c, QHeaderView.Interactive)
                        if tbl_tf.columnCount() >= 6:
                            th.resizeSection(0, 40)
                            th.resizeSection(1, 100)
                            th.resizeSection(2, 80)
                            th.resizeSection(3, 80)
                            th.resizeSection(4, 120)
                            th.resizeSection(5, 60)
                        tbl_tf.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
                        try:
                            tbl_tf.setAlternatingRowColors(True)
                        except Exception:
                            pass
                    except Exception:
                        logger.debug("[UIUpdaters] TF table init failed: %s", tbl_name)

                # 그룹박스 마진 보정
                for gname in ("groupBox_flow", "groupBox_comm", "groupBox_tf_tabs"):
                    g = getattr(self, gname, None)
                    if g is not None:
                        try:
                            g.setContentsMargins(8, 12, 8, 8)
                        except Exception:
                            pass

                # UI 로그 consumer 등록 시도 (기존 방식 유지)
                try:
                    if not getattr(self, "_ui_log_registered", False):
                        self._try_register_ui_log_consumer()
                except Exception:
                    logger.debug("[UIUpdaters] attempted register_ui_log_consumer and failed", exc_info=True)

                # Ensure flush timer is running (defensive)
                try:
                    if getattr(self, "_ui_flush_timer", None) is not None and not self._ui_flush_timer.isActive():
                        self._ui_flush_timer.start()
                        logger.debug("[UIUpdaters] ui_flush_timer restarted from _optimize_layout")
                except Exception:
                    pass

            except Exception as exc:
                logger.debug("[UIUpdaters] _optimize_layout error: %s", exc)

        def _try_register_ui_log_consumer(self) -> None:
            """main.register_ui_log_consumer에 런타임으로 등록 시도 (importlib 사용)."""
            try:
                mod = importlib.import_module("main")
            except Exception:
                logger.debug("[UIUpdaters] main module not importable for ui log registration")
                return

            try:
                reg = getattr(mod, "register_ui_log_consumer", None)
                if callable(reg):
                    try:
                        reg(self._on_ui_log_received)
                        self._ui_log_registered = True
                        logger.debug("[UIUpdaters] registered UI log consumer")
                    except Exception:
                        logger.debug("[UIUpdaters] register_ui_log_consumer call failed", exc_info=True)
                else:
                    logger.debug("[UIUpdaters] main.register_ui_log_consumer not found or not callable")
            except Exception:
                logger.debug("[UIUpdaters] unexpected error while registering UI log consumer", exc_info=True)

        # ---------------------------
        # flow 상태 업데이트
        # ---------------------------
        def update_flow_status(self, stage: str, status: str) -> None:
            """플로우 상태 레이블 갱신 (쓰로틀 적용)."""
            try:
                if not hasattr(self, "_last_update_time") or self._last_update_time is None:
                    self._last_update_time = {}
                if not hasattr(self, "_update_interval_ms"):
                    self._update_interval_ms = 100.0

                now_ms = time.perf_counter() * 1000.0
                last_ms = self._last_update_time.get(stage, 0.0)
                if now_ms - last_ms < float(self._update_interval_ms):
                    return
                self._last_update_time[stage] = now_ms

                label_map = {
                    "websocket": "label_flow_websocket",
                    "pipeline": "label_flow_pipeline",
                    "db": "label_flow_db",
                    "ui": "label_flow_ui",
                }
                stage_labels = {
                    "websocket": "WebSocket",
                    "pipeline": "Pipeline",
                    "db": "DB 저장",
                    "ui": "UI 갱신",
                }
                label_name = label_map.get(stage)
                if not label_name:
                    return
                lbl = getattr(self, label_name, None)
                if lbl is None:
                    return
                prefix = stage_labels.get(stage, stage)
                try:
                    lbl.setText(f"{prefix}: {status}")
                except Exception:
                    logger.debug("[UIUpdaters] setText failed for %s", label_name)
            except Exception as exc:
                logger.debug("[UIUpdaters] update_flow_status error: %s", exc)

        # ---------------------------
        # 통신 테이블(행 추가) - 버퍼링
        # ---------------------------
        def add_comm_row(
            self,
            time_str: str,
            kind: str,
            symbol: str,
            data: str,
            latency_ms: str,
            target: Optional[str] = None,
        ) -> None:
            """통신 테이블에 행을 추가합니다 (버퍼에 적재)."""
            try:
                vals = ["" if v is None else str(v) for v in (time_str, kind, symbol, data, latency_ms)]
                tgt = str(target) if target is not None else ""
                try:
                    with self._ui_buffer_lock:
                        self._comm_buffer.append((tgt, vals))
                except Exception:
                    # fallback without lock
                    try:
                        self._comm_buffer.append((tgt, vals))
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[UIUpdaters] add_comm_row buffer error: %s", exc)

        # ---------------------------
        # TF 행 추가 - 버퍼링
        # ---------------------------
        def append_tf_row(self, timeframe: str, row: Sequence[str]) -> None:
            """TF 테이블에 행을 추가합니다 (버퍼링)."""
            try:
                if timeframe not in TF_LIST:
                    logger.debug("[UIUpdaters] append_tf_row invalid timeframe: %s", timeframe)
                    return
                try:
                    rlist = ["" if v is None else str(v) for v in row]
                except Exception:
                    rlist = [str(v) if v is not None else "" for v in row]
                try:
                    with self._ui_buffer_lock:
                        self._tf_buffers.setdefault(timeframe, []).append(rlist)
                except Exception:
                    try:
                        self._tf_buffers.setdefault(timeframe, []).append(rlist)
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[UIUpdaters] append_tf_row buffer error (%s): %s", timeframe, exc)

        def clear_tf_table(self, timeframe: str) -> None:
            try:
                if timeframe not in TF_LIST:
                    return
                tbl = getattr(self, f"table_tf_{timeframe}", None)
                if tbl is not None:
                    try:
                        tbl.setUpdatesEnabled(False)
                        tbl.setRowCount(0)
                        tbl.setUpdatesEnabled(True)
                    except Exception:
                        logger.debug("[UIUpdaters] clear_tf_table failed on widget: %s", timeframe)
                try:
                    with self._ui_buffer_lock:
                        if timeframe in self._tf_buffers:
                            self._tf_buffers[timeframe].clear()
                except Exception:
                    try:
                        self._tf_buffers[timeframe] = []
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[UIUpdaters] clear_tf_table error (%s): %s", timeframe, exc)

        # ---------------------------
        # UI 버퍼 플러시 (UI 스레드에서 호출되어야 함)
        # ---------------------------
        def _flush_ui_buffers(self) -> None:
            """UI 스레드에서 주기적으로 호출되어 버퍼를 비우고 테이블에 배치 삽입합니다."""
            try:
                # swap buffers under lock to minimize lock holding time
                try:
                    with self._ui_buffer_lock:
                        comm_buf = list(self._comm_buffer)
                        self._comm_buffer.clear()
                        tf_bufs = {tf: list(buf) for tf, buf in self._tf_buffers.items()}
                        for tf in self._tf_buffers:
                            self._tf_buffers[tf].clear()
                except Exception:
                    comm_buf = getattr(self, "_comm_buffer", [])[:]
                    self._comm_buffer = []
                    tf_bufs = {tf: getattr(self, "_tf_buffers", {}).get(tf, [])[:] for tf in TF_LIST}
                    for tf in TF_LIST:
                        try:
                            self._tf_buffers[tf] = []
                        except Exception:
                            pass

                # Diagnostic log to confirm _flush_ui_buffers is running and counts
                try:
                    total_tf = sum(len(v) for v in tf_bufs.values())
                    logger.debug("[UIUpdaters] _flush_ui_buffers called: comm=%d tf_total=%d", len(comm_buf), total_tf)
                except Exception:
                    pass

                # Process comm buffer
                if comm_buf:
                    try:
                        grouped: Dict[str, List[List[str]]] = {}
                        for tgt, vals in comm_buf:
                            grouped.setdefault(tgt or "comm", []).append(vals)

                        for tgt, rows in grouped.items():
                            if tgt == "comm" or tgt == "":
                                tbl = getattr(self, "table_comm", None)
                            elif tgt == "comm_net" or tgt.lower() == "comm_net":
                                tbl = getattr(self, "table_comm_net", None)
                            else:
                                tbl = getattr(self, "table_comm", None)
                            if tbl is None:
                                continue

                            try:
                                tbl.setUpdatesEnabled(False)
                                # prune if necessary
                                try:
                                    cur = tbl.rowCount()
                                except Exception:
                                    cur = 0
                                total_new = len(rows)
                                target_total = cur + total_new
                                if target_total > MAX_COMM_ROWS:
                                    remove_n = min(cur, target_total - MAX_COMM_ROWS)
                                    for _ in range(remove_n):
                                        try:
                                            tbl.removeRow(0)
                                        except Exception:
                                            pass

                                # bulk append
                                for vals in rows:
                                    try:
                                        r = tbl.rowCount()
                                        tbl.insertRow(r)
                                        for col, v in enumerate(vals):
                                            try:
                                                it = QTableWidgetItem("" if v is None else str(v))
                                                if col == 3:
                                                    it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                                                tbl.setItem(r, col, it)
                                            except Exception:
                                                try:
                                                    tbl.setItem(r, col, QTableWidgetItem(""))
                                                except Exception:
                                                    pass
                                    except Exception:
                                        continue
                            finally:
                                try:
                                    vscroll = tbl.verticalScrollBar()
                                    max_val = vscroll.maximum()
                                    cur_val = vscroll.value()
                                    if max_val - cur_val <= 20:
                                        tbl.scrollToBottom()
                                except Exception:
                                    try:
                                        tbl.scrollToBottom()
                                    except Exception:
                                        pass
                                try:
                                    tbl.setUpdatesEnabled(True)
                                except Exception:
                                    pass
                    except Exception:
                        logger.debug("[UIUpdaters] error while flushing comm buffer", exc_info=True)

                # Process TF buffers
                if tf_bufs:
                    try:
                        for tf, rows in tf_bufs.items():
                            if not rows:
                                continue
                            tbl = getattr(self, f"table_tf_{tf}", None)
                            if tbl is None:
                                continue
                            try:
                                tbl.setUpdatesEnabled(False)
                                try:
                                    cur = tbl.rowCount()
                                except Exception:
                                    cur = 0
                                total_new = len(rows)
                                target_total = cur + total_new
                                if target_total > MAX_TF_ROWS:
                                    remove_n = min(cur, target_total - MAX_TF_ROWS)
                                    for _ in range(remove_n):
                                        try:
                                            tbl.removeRow(0)
                                        except Exception:
                                            pass

                                cols = tbl.columnCount()
                                for row_vals in rows:
                                    try:
                                        r = tbl.rowCount()
                                        tbl.insertRow(r)
                                        for c in range(cols):
                                            try:
                                                text = row_vals[c] if c < len(row_vals) else ""
                                                tbl.setItem(r, c, QTableWidgetItem("" if text is None else str(text)))
                                            except Exception:
                                                try:
                                                    tbl.setItem(r, c, QTableWidgetItem(""))
                                                except Exception:
                                                    pass
                                    except Exception:
                                        continue
                                try:
                                    tbl.scrollToBottom()
                                except Exception:
                                    pass
                            finally:
                                try:
                                    tbl.setUpdatesEnabled(True)
                                except Exception:
                                    pass
                    except Exception:
                        logger.debug("[UIUpdaters] error while flushing tf buffers", exc_info=True)

            except Exception:
                logger.debug("[UIUpdaters] _flush_ui_buffers unexpected error", exc_info=True)

        # ---------------------------
        # main.py에서 전달한 로그 수신 콜백
        # ---------------------------
        def _on_ui_log_received(self, formatted_message: str, record: logging.LogRecord) -> None:
            """main.QtLogHandler에서 전달된 로그를 UI 테이블에 추가."""
            try:
                if not self._ui_log_passes_filter(record):
                    return

                try:
                    ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
                except Exception:
                    ts = ""

                level = getattr(record, "levelname", "")
                module = getattr(record, "name", "")
                msg = record.getMessage()

                try:
                    app = QApplication.instance()
                    if app is not None:
                        QTimer.singleShot(0, lambda: self.add_comm_row(ts, level, module, msg, "-"))
                    else:
                        self.add_comm_row(ts, level, module, msg, "-")
                except Exception:
                    try:
                        self.add_comm_row(ts, level, module, msg, "-")
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[UIUpdaters] _on_ui_log_received error: %s", exc)

        # ---------------------------
        # 체크박스 검색 (필터링용)
        # ---------------------------
        def _find_checkbox_by_text(self, keyword: str) -> Optional[QCheckBox]:
            if not keyword:
                return None
            try:
                key = keyword.lower()
            except Exception:
                return None

            for attr_name in dir(self):
                try:
                    attr = getattr(self, attr_name, None)
                except Exception:
                    continue
                try:
                    if not isinstance(attr, QCheckBox):
                        continue
                except Exception:
                    continue
                try:
                    txt = attr.text()
                except Exception:
                    continue
                if txt and key in txt.lower():
                    return attr
            return None

        def _ui_log_passes_filter(self, record: logging.LogRecord) -> bool:
            """UI 체크박스 상태와 로그 레벨에 따라 로그 표시 여부 결정.

            정책:
            - WARNING 이상은 UI에 표시하지 않음(콘솔 전용).
            - 체크박스(WebSocket, Pipeline, Gap)가 존재하면, 체크 상태에 따라
              record.name OR record.getMessage()에 포함된 키워드로 필터링.
            - 체크박스가 없으면 기본적으로 표시(다만 WARNING 이상은 제외).
            """
            try:
                # 1) 레벨 필터: WARNING 이상은 UI에 표시하지 않음(터미널 전용)
                try:
                    lvl = getattr(record, "levelno", logging.INFO)
                except Exception:
                    lvl = logging.INFO
                if lvl >= logging.WARNING:
                    return False

                # message and logger name (lowercase) for keyword matching
                try:
                    name = (record.name or "").lower()
                except Exception:
                    name = ""
                try:
                    message = (record.getMessage() or "").lower()
                except Exception:
                    message = ""

                # Try to find checkboxes by visible text
                try:
                    ws_cb = self._find_checkbox_by_text("WebSocket")
                except Exception:
                    ws_cb = self._find_checkbox_by_text("websocket")
                try:
                    pl_cb = self._find_checkbox_by_text("Pipeline")
                except Exception:
                    pl_cb = self._find_checkbox_by_text("pipeline")
                try:
                    gap_cb = self._find_checkbox_by_text("Gap")
                except Exception:
                    gap_cb = self._find_checkbox_by_text("gap")

                # If specific checkbox exists and is unchecked, and the record relates to that category,
                # then block it.
                try:
                    # Helper to check if keyword present in name or message
                    def _contains_keyword(k: str) -> bool:
                        if not k:
                            return False
                        k = k.lower()
                        return (k in name) or (k in message)

                    if ws_cb is not None:
                        try:
                            if not ws_cb.isChecked() and _contains_keyword("websocket"):
                                return False
                        except Exception:
                            pass
                    if pl_cb is not None:
                        try:
                            if not pl_cb.isChecked() and _contains_keyword("pipeline"):
                                return False
                        except Exception:
                            pass
                    if gap_cb is not None:
                        try:
                            if not gap_cb.isChecked() and _contains_keyword("gap"):
                                return False
                        except Exception:
                            pass
                except Exception:
                    # on unexpected error, allow the record (but this should be rare)
                    return True

                # default allow (it's INFO/DEBUG and not suppressed by checkboxes)
                return True
            except Exception:
                # On any unexpected error, be conservative and allow the record
                return True

        # ---------------------------
        # 업타임 / 상태바
        # ---------------------------
        def _update_uptime(self) -> None:
            try:
                start = getattr(self, "_start_time", None)
                if start is None:
                    self._start_time = datetime.now()
                    start = self._start_time
                elapsed = datetime.now() - start
                total_secs = int(elapsed.total_seconds())
                h, rem = divmod(total_secs, 3600)
                m, s = divmod(rem, 60)
                lbl = getattr(self, "label_uptime", None)
                if lbl is not None:
                    try:
                        lbl.setText(f"업타임: {h:02d}:{m:02d}:{s:02d}")
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[UIUpdaters] _update_uptime error: %s", exc)

        def _update_status_bar(self) -> None:
            try:
                lbl = getattr(self, "label_status_bar", None)
                if lbl is None:
                    return
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                try:
                    lbl.setText(f"최종 갱신: {now_str}")
                except Exception:
                    pass
            except Exception as exc:
                logger.debug("[UIUpdaters] _update_status_bar error: %s", exc)

        def _on_timer_tick(self) -> None:
            try:
                self._update_status_bar()
            except Exception as exc:
                logger.debug("[UIUpdaters] _on_timer_tick error: %s", exc)

        # ---------------------------
        # TF 탭 관련 유틸리티
        # ---------------------------
        def _find_tf_widgets(self, tf: str):
            try:
                if tf not in TF_LIST:
                    return None, None, None, None
                pb = getattr(self, f"pb_tf_{tf}", None)
                pct_lbl = getattr(self, f"lbl_tf_{tf}_pct", None)
                state_lbl = getattr(self, f"lbl_tf_{tf}_state", None)
                table = getattr(self, f"table_tf_{tf}", None)
                return pb, pct_lbl, state_lbl, table
            except Exception as exc:
                logger.debug("[UIUpdaters] _find_tf_widgets error: %s", exc)
                return None, None, None, None

        def update_tf_tabs_summary(self, summary: Dict[str, Dict]) -> None:
            try:
                if not isinstance(summary, dict):
                    return
                for tf, info in summary.items():
                    if tf not in TF_LIST:
                        continue
                    try:
                        if isinstance(info, dict):
                            raw_pct = info.get("pct", 0.0)
                            state = info.get("state", "")
                        else:
                            raw_pct = float(info)
                            state = ""
                        try:
                            pct = float(raw_pct)
                        except Exception:
                            pct = 0.0
                        pct = max(0.0, min(100.0, pct))
                        pb, pct_lbl, state_lbl, tbl = self._find_tf_widgets(tf)

                        if pb is not None and isinstance(pb, QProgressBar):
                            try:
                                pb.setValue(int(round(pct)))
                            except Exception:
                                pass
                        if pct_lbl is not None:
                            try:
                                pct_lbl.setText(f"{int(round(pct))}%")
                            except Exception:
                                pass
                        if state_lbl is not None:
                            try:
                                state_lbl.setText(str(state))
                            except Exception:
                                pass
                    except Exception:
                        logger.debug("[UIUpdaters] update error for tf=%s", tf)
            except Exception as exc:
                logger.debug("[UIUpdaters] update_tf_tabs_summary error: %s", exc)

else:
    class UIUpdatersMixin:
        def _optimize_layout(self) -> None:
            return None

        def update_flow_status(self, stage: str, status: str) -> None:
            return None

        def add_comm_row(
            self,
            time_str: str,
            kind: str,
            symbol: str,
            data: str,
            latency_ms: str,
            target: Optional[str] = None,
        ) -> None:
            return None

        def _update_uptime(self) -> None:
            return None

        def _update_status_bar(self) -> None:
            return None

        def _on_timer_tick(self) -> None:
            return None

        def update_tf_tabs_summary(self, summary: Dict[str, Dict]) -> None:
            return None

        def append_tf_row(self, timeframe: str, row: Sequence[str]) -> None:
            return None

        def clear_tf_table(self, timeframe: str) -> None:
            return None

        def set_active_tf_tab(self, timeframe: str) -> None:
            return None