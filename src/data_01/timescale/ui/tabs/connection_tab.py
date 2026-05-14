# -*- coding: utf-8 -*-
"""TimescaleDB 연결 상태 탭 - 실시간 연결 헬스 체크 (QThread Worker 패턴)"""
from __future__ import annotations

import os
import time
import logging
from typing import Optional, Dict

try:
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QHeaderView
    from PyQt5.QtCore import QThread, QTimer, pyqtSignal, pyqtSlot
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "connection_tab.ui")

_DEFAULT_PORT = 58529
_DEFAULT_DB   = "upbit_trader"


def _normalize_host(host: str) -> str:
    """Windows에서 localhost가 ::1(IPv6)로 해석되는 문제를 방지합니다.
    localhost → 127.0.0.1 로 변환하여 항상 IPv4를 사용합니다.
    """
    if not host or str(host).strip().lower() == "localhost":
        return "127.0.0.1"
    return str(host).strip()

if _HAS_QT:
    class ConnectionWorker(QThread):
        """백그라운드에서 DB 연결 및 버전 조회를 수행합니다. 

        메인스레드를 절대 블로킹하지 않습니다.
        Windows IPv6 문제 방지: localhost → 127.0.0.1 자동 변환.

        Signals:
            finished(dict): {"connected": bool, "version": str, "ping_ms": float}
        """

        finished = pyqtSignal(dict)

        def __init__(self, conn_params: dict, parent=None) -> None:
            super().__init__(parent)
            self._conn_params = conn_params or {}

        def run(self) -> None:
            p = self._conn_params
            result: Dict = {"connected": False, "version": "-", "ping_ms": -1.0,
                            "ts_version": "-"}
            t0 = time.monotonic()
            try:
                import psycopg2
                # "db"/"pass" 키(QSettings 저장 형식)와 표준 키를 모두 지원
                # 빈 문자열은 QSettings 미설정으로 취급 → 기본값으로 폴백
                database = next(
                    (p[k] for k in ("database", "dbname", "db")
                     if k in p and p[k] and str(p[k]).strip()),
                    _DEFAULT_DB
                )
                # 비밀번호는 빈 문자열도 유효한 값으로 취급 (key 존재 우선)
                password = next(
                    (p[k] for k in ("password", "pass", "passwd") if k in p),
                    ""
                )
                # Windows IPv6 문제 방지: localhost → 127.0.0.1
                host = _normalize_host(p.get("host", ""))
                conn = psycopg2.connect(
                    host=host,
                    port=int(p.get("port", _DEFAULT_PORT)),
                    database=database,
                    user=p.get("user", "") or "postgres",
                    password=password,
                    connect_timeout=3,
                )
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT version();")
                        row = cur.fetchone()
                        raw = row[0] if row else "-"
                        version_short = raw.split("\n")[0][:80]
                        # TimescaleDB extension 버전 조회
                        ts_ver = "-"
                        try:
                            cur.execute(
                                "SELECT extversion FROM pg_extension "
                                "WHERE extname = 'timescaledb';"
                            )
                            ts_row = cur.fetchone()
                            ts_ver = ts_row[0] if ts_row else "미설치"
                        except Exception:
                            ts_ver = "조회 실패"
                    result = {
                        "connected": True,
                        "version":   version_short,
                        "ping_ms":   elapsed_ms,
                        "ts_version": ts_ver,
                    }
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[ConnectionWorker] 연결 실패: %s", exc)
                result["ping_ms"] = (time.monotonic() - t0) * 1000.0
                result["error_hint"] = str(exc)
            self.finished.emit(result)

    # -------------------------------------------------------------------------

    class ConnectionTab(QWidget):
        """연결 상태 탭.

        DB 헬스 체크와 연결 정보를 5초마다 갱신합니다.
        psycopg2.connect() 는 ConnectionWorker(QThread) 내부에서만 실행됩니다.
        메인스레드 블로킹이 전혀 없습니다.
        Windows IPv6 문제 방지: localhost → 127.0.0.1 자동 변환.
        """

        def __init__(self, conn_params: Optional[Dict] = None, parent=None):
            super().__init__(parent)
            self._conn_params: Dict = conn_params or {}
            self._worker: Optional[ConnectionWorker] = None

            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[ConnectionTab] UI 로드 실패: %s", exc)

            self._setup_table()
            self._populate_conn_info()

            # btnRefresh 클릭 → 즉시 갱신
            btn = getattr(self, "btnRefresh", None)
            if btn is not None:
                btn.clicked.connect(self._update)

            # 자동 갱신 타이머 (5초) — __init__에서 자동 시작 안 함
            self._timer = QTimer(self)
            self._timer.setInterval(5000)
            self._timer.timeout.connect(self._update)

        # ------------------------------------------------------------------
        # 내부 설정
        # ------------------------------------------------------------------

        def _setup_table(self) -> None:
            """연결 정보 테이블 헤더 설정."""
            tbl = getattr(self, "table_conn", None)
            if tbl is None:
                return
            tbl.setColumnCount(2)
            tbl.setHorizontalHeaderLabels(["항목", "값"])
            hdr = tbl.horizontalHeader()
            hdr.setSectionResizeMode(QHeaderView.Stretch)
            tbl.setAlternatingRowColors(True)

        def _populate_conn_info(self) -> None:
            """연결 파라미터(정적 정보)를 테이블에 표시."""
            p = self._conn_params
            # "db"/"pass" 키(QSettings 저장 형식)와 표준 키를 모두 지원
            database = next(
                (p[k] for k in ("database", "dbname", "db")
                 if k in p and p[k] and str(p[k]).strip()),
                _DEFAULT_DB
            )
            # Windows IPv6 문제 방지: localhost → 127.0.0.1
            host = _normalize_host(p.get("host", ""))
            rows = [
                ("호스트",       host),
                ("포트",         str(p.get("port", _DEFAULT_PORT))),
                ("데이터베이스", database),
                ("사용자",       p.get("user", "") or "postgres"),
            ]
            tbl = getattr(self, "table_conn", None)
            if tbl is None:
                return
            tbl.setRowCount(len(rows))
            for i, (key, val) in enumerate(rows):
                tbl.setItem(i, 0, QTableWidgetItem(key))
                tbl.setItem(i, 1, QTableWidgetItem(str(val)))

        # ------------------------------------------------------------------
        # 갱신 로직 (Worker 패턴)
        # ------------------------------------------------------------------

        def _update(self) -> None:
            """Worker가 실행 중이면 건너뜁니다. 아니면 새 Worker를 시작합니다."""
            if self._worker and self._worker.isRunning():
                return
            self._worker = ConnectionWorker(self._conn_params)
            self._worker.finished.connect(self._on_data_ready)
            self._worker.start()

        @pyqtSlot(dict)
        def _on_data_ready(self, data: dict) -> None:
            """Worker 완료 시 메인스레드에서 UI를 갱신합니다."""
            label_status  = getattr(self, "label_status",  None)
            label_ping    = getattr(self, "label_ping",    None)
            label_version = getattr(self, "label_version", None)

            if data.get("connected"):
                if label_status:
                    label_status.setText("🟢 상태: 연결됨")
                    label_status.setStyleSheet("color: #27AE60; font-weight: bold;")
                if label_ping:
                    label_ping.setText(f"응답시간: {data['ping_ms']:.1f} ms")
                if label_version:
                    ts_ver = data.get("ts_version", "-")
                    label_version.setText(
                        f"PostgreSQL: {data['version']}  |  TimescaleDB: {ts_ver}"
                    )
                    label_version.setStyleSheet("")
            else:
                if label_status:
                    label_status.setText("🔴 상태: 연결 실패")
                    label_status.setStyleSheet("color: #E74C3C; font-weight: bold;")
                if label_ping:
                    label_ping.setText("응답시간: -")
                if label_version:
                    p = self._conn_params
                    host = _normalize_host(p.get("host", ""))
                    port = p.get("port", _DEFAULT_PORT)
                    hint = data.get("error_hint", "")
                    hint_msg = (
                        f"연결 실패 — {host}:{port} Docker 컨테이너 실행 여부 확인 필요\n"
                        f"확인: docker ps | grep timescale"
                    )
                    if hint:
                        hint_msg += f"\n오류: {hint[:150]}"
                    label_version.setText(hint_msg)
                    label_version.setStyleSheet("color: #E74C3C;")

        # ------------------------------------------------------------------
        # 생명 주기
        # ------------------------------------------------------------------

        def start_updates(self, interval_ms: int = 5000) -> None:
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
    class ConnectionTab:  # type: ignore[no-redef]
        def __init__(self, conn_params=None, parent=None): pass
        def start_updates(self, interval_ms: int = 5000) -> None: pass
        def stop_updates(self) -> None: pass
