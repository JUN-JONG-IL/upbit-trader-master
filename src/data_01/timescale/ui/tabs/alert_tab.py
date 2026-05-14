# -*- coding: utf-8 -*-
"""TimescaleDB 알림 설정 탭 - 임계값 설정 및 실시간 경보 확인 (QThread Worker 패턴)

psycopg2.connect() 는 AlertWorker(QThread) 내부에서만 실행됩니다.
"""
from __future__ import annotations

import os
import time
import logging
from typing import Optional, Dict, List

try:
    from PyQt5.QtWidgets import (
        QWidget, QTableWidget, QTableWidgetItem,
        QVBoxLayout, QHeaderView, QLabel,
    )
    from PyQt5.QtCore import QThread, QTimer, pyqtSignal, pyqtSlot
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

try:
    from .db_worker import build_connect_kwargs
except ImportError:
    from db_worker import build_connect_kwargs  # type: ignore[no-redef]

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "alert_tab.ui")

# 알림 로그 최대 보관 건수
_MAX_LOG = 50


if _HAS_QT:
    class AlertWorker(QThread):
        """백그라운드에서 DB 연결 응답 시간을 측정합니다.

        Signals:
            finished(dict): {"connected": bool, "elapsed_ms": float}
        """

        finished = pyqtSignal(dict)

        def __init__(self, conn_params: dict, parent=None) -> None:
            super().__init__(parent)
            self._conn_params = conn_params or {}

        def run(self) -> None:
            result = {"connected": False, "elapsed_ms": -1.0}
            t0 = time.monotonic()
            try:
                import psycopg2
                kwargs = build_connect_kwargs(self._conn_params)
                conn = psycopg2.connect(**kwargs)
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                try:
                    conn.close()
                except Exception:
                    pass
                result = {"connected": True, "elapsed_ms": elapsed_ms}
            except Exception as exc:
                logger.debug("[AlertWorker] 연결 실패: %s", exc)
                result["elapsed_ms"] = (time.monotonic() - t0) * 1000.0
            self.finished.emit(result)

    # -------------------------------------------------------------------------

    class AlertTab(QWidget):
        """알림 설정 탭.

        연결 실패 횟수·응답 지연 임계값을 설정하고 경보 이력을 표시합니다.
        psycopg2.connect() 는 AlertWorker(QThread) 내부에서만 실행됩니다.
        """

        def __init__(self, conn_params: Optional[Dict] = None, parent=None):
            super().__init__(parent)
            self._conn_params: Dict = conn_params or {}
            self._alert_log: List[Dict] = []  # {time, type, value, threshold}
            self._worker: Optional[AlertWorker] = None

            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[AlertTab] UI 로드 실패: %s", exc)

            # 알림 이력 테이블을 동적으로 추가 (UI 파일에 없음)
            self._setup_log_table()

            # btnSaveAlerts 클릭 → 임계값 저장 확인 메시지
            btn = getattr(self, "btnSaveAlerts", None)
            if btn is not None:
                btn.clicked.connect(self._save_thresholds)

            # 자동 갱신 타이머 (10초) — __init__에서 자동 시작 안 함
            self._timer = QTimer(self)
            self._timer.setInterval(10_000)
            self._timer.timeout.connect(self._update)

        # ------------------------------------------------------------------
        # 내부 설정
        # ------------------------------------------------------------------

        def _setup_log_table(self) -> None:
            """알림 이력 테이블을 탭 레이아웃 하단에 동적으로 추가합니다."""
            layout = self.layout()
            if layout is None:
                logger.warning("[AlertTab] 레이아웃을 찾을 수 없어 알림 이력 테이블을 추가하지 못했습니다.")
                return

            lbl = QLabel("📋 알림 이력")
            lbl.setStyleSheet("font-weight: bold; margin-top: 8px;")
            layout.addWidget(lbl)

            self._log_table = QTableWidget()
            self._log_table.setColumnCount(4)
            self._log_table.setHorizontalHeaderLabels(["시각", "유형", "측정값", "임계값"])
            hdr = self._log_table.horizontalHeader()
            hdr.setSectionResizeMode(QHeaderView.Stretch)
            self._log_table.setAlternatingRowColors(True)
            self._log_table.setEditTriggers(QTableWidget.NoEditTriggers)
            layout.addWidget(self._log_table)

        # ------------------------------------------------------------------
        # 임계값 저장
        # ------------------------------------------------------------------

        def _save_thresholds(self) -> None:
            """현재 스핀박스 값을 읽어 로그에 기록합니다."""
            conn_fail = getattr(self, "spinConnFail", None)
            latency   = getattr(self, "spinLatency",  None)
            cf_val = conn_fail.value() if conn_fail else 3
            lt_val = latency.value()   if latency   else 500
            logger.info("[AlertTab] 임계값 저장 - 연결실패: %d회, 응답지연: %d ms", cf_val, lt_val)
            btn = getattr(self, "btnSaveAlerts", None)
            if btn:
                btn.setText("✅ 저장 완료")
                import weakref
                btn_ref = weakref.ref(btn)
                def _reset_btn_text():
                    b = btn_ref()
                    if b is not None:
                        try:
                            b.setText("💾 저장")
                        except RuntimeError:
                            pass
                QTimer.singleShot(2000, _reset_btn_text)

        # ------------------------------------------------------------------
        # 갱신 로직 (Worker 패턴)
        # ------------------------------------------------------------------

        def _update(self) -> None:
            """Worker가 실행 중이면 건너뜁니다. 아니면 새 Worker를 시작합니다."""
            if self._worker and self._worker.isRunning():
                return
            self._worker = AlertWorker(self._conn_params)
            self._worker.finished.connect(self._on_data_ready)
            self._worker.start()

        @pyqtSlot(dict)
        def _on_data_ready(self, data: dict) -> None:
            """Worker 완료 시 메인스레드에서 임계값 초과 여부를 확인합니다."""
            latency_spin = getattr(self, "spinLatency", None)
            threshold_ms = latency_spin.value() if latency_spin else 500

            if not data.get("connected"):
                self._add_alert("연결 실패", "-", "연결 불가")
            else:
                elapsed_ms = data.get("elapsed_ms", 0.0)
                if elapsed_ms > threshold_ms:
                    self._add_alert(
                        "응답 지연",
                        f"{elapsed_ms:.0f} ms",
                        f"{threshold_ms} ms",
                    )

        def _add_alert(self, alert_type: str, value: str, threshold: str) -> None:
            """알림 이력 목록에 항목을 추가하고 테이블을 갱신합니다."""
            from datetime import datetime
            entry = {
                "time":      datetime.now().strftime("%H:%M:%S"),
                "type":      alert_type,
                "value":     value,
                "threshold": threshold,
            }
            self._alert_log.insert(0, entry)
            if len(self._alert_log) > _MAX_LOG:
                self._alert_log = self._alert_log[:_MAX_LOG]
            self._render_log()

        def _render_log(self) -> None:
            """알림 이력 테이블을 렌더링합니다."""
            tbl = getattr(self, "_log_table", None)
            if tbl is None:
                return
            tbl.setRowCount(len(self._alert_log))
            for i, entry in enumerate(self._alert_log):
                tbl.setItem(i, 0, QTableWidgetItem(entry["time"]))
                tbl.setItem(i, 1, QTableWidgetItem(entry["type"]))
                tbl.setItem(i, 2, QTableWidgetItem(entry["value"]))
                tbl.setItem(i, 3, QTableWidgetItem(entry["threshold"]))

        # ------------------------------------------------------------------
        # 생명 주기
        # ------------------------------------------------------------------

        def start_updates(self, interval_ms: int = 10_000) -> None:
            """자동 갱신 시작. 즉시 첫 갱신도 실행합니다."""
            self._timer.setInterval(max(1000, int(interval_ms)))
            if not self._timer.isActive():
                self._timer.start()
            self._update()

        def stop_updates(self) -> None:
            """자동 갱신 중지."""
            self._timer.stop()

        def closeEvent(self, event) -> None:
            self._timer.stop()
            if self._worker and self._worker.isRunning():
                self._worker.quit()
                self._worker.wait(2000)
            super().closeEvent(event)

else:
    class AlertTab:  # type: ignore[no-redef]
        def __init__(self, conn_params=None, parent=None): pass
        def start_updates(self, interval_ms: int = 10_000) -> None: pass
        def stop_updates(self) -> None: pass
