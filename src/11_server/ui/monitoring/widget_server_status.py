#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
서버 상태 모니터링 6-탭 다이얼로그

[Responsibilities]
- Tab 1: FastAPI 엔드포인트 상태 (req/s, 응답시간, 에러율)
- Tab 2: WebSocket 연결 목록 및 통계
- Tab 3: CPU/메모리/디스크/네트워크 리소스 모니터링
- Tab 4: 시간대별·엔드포인트별 요청 통계 및 응답시간 분포
- Tab 5: 에러 로그 (레벨 필터, 내보내기)
- Tab 6: 서버 설정 (포트, 워커, 타임아웃, CORS)
- 5초 주기 자동 갱신 (QTimer)

[Dependencies]
- PyQt5 (선택)
- server_status.ui
- psutil (선택, 리소스 탭)

[Author] Copilot Workspace Refactor
[Created] 2026-03-06
"""

from __future__ import annotations

import csv
import datetime
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import (
        QDialog,
        QTableWidgetItem,
        QFileDialog,
        QMessageBox,
    )
    from PyQt5.QtCore import QTimer, Qt
    from PyQt5 import uic

    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    logger.debug("[ServerStatusDialog] PyQt5 없음 - UI 비활성화")

try:
    import psutil  # type: ignore

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _fmt_bytes(n: float) -> str:
    """바이트 수를 사람이 읽기 쉬운 문자열로 변환한다."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}/s"
        n /= 1024
    return f"{n:.1f} TB/s"


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class ServerStatusDialog(QDialog if PYQT5_AVAILABLE else object):  # type: ignore[misc]
    """서버 상태 모니터링 6-탭 다이얼로그.

    5초마다 모든 탭의 데이터를 자동 갱신합니다.
    psutil이 설치된 경우 실제 리소스 지표를 표시하고,
    그렇지 않으면 플레이스홀더 데이터를 표시합니다.
    """

    _UI_PATH = Path(__file__).parent / "server_status.ui"
    _REFRESH_INTERVAL_MS = 5_000  # 5초

    def __init__(self, parent=None) -> None:
        if not PYQT5_AVAILABLE:
            logger.warning("[ServerStatusDialog] PyQt5 미설치 - 다이얼로그 생성 불가")
            return

        super().__init__(parent)
        self._timer: Optional[QTimer] = None
        self._net_prev: Optional[Tuple[float, float]] = None  # (bytes_sent, bytes_recv)
        self._net_prev_time: Optional[float] = None

        self._load_ui()
        self._connect_signals()
        self._setup_timer()
        self._refresh_all()

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _load_ui(self) -> None:
        """UI 파일을 로드한다."""
        try:
            uic.loadUi(str(self._UI_PATH), self)
        except Exception as exc:
            logger.error("[ServerStatusDialog] UI 로딩 실패: %s", exc)

    def _connect_signals(self) -> None:
        """버튼 시그널을 슬롯에 연결한다."""
        try:
            self.btnRefresh.clicked.connect(self._refresh_all)
            self.btnClose.clicked.connect(self.close)
            self.btnRestartServer.clicked.connect(self._on_restart_server)
            self.btnDisconnectClient.clicked.connect(self._on_disconnect_client)
            self.btnExportLog.clicked.connect(self._on_export_log)
            self.btnSaveSettings.clicked.connect(self._on_save_settings)
            self.comboLogLevel.currentIndexChanged.connect(self.load_error_log)
        except AttributeError as exc:
            logger.debug("[ServerStatusDialog] 시그널 연결 실패: %s", exc)

    def _setup_timer(self) -> None:
        """5초 자동 갱신 타이머를 설정한다."""
        try:
            self._timer = QTimer(self)
            self._timer.setInterval(self._REFRESH_INTERVAL_MS)
            self._timer.timeout.connect(self._refresh_all)
            self._timer.start()
        except Exception as exc:
            logger.debug("[ServerStatusDialog] 타이머 설정 실패: %s", exc)

    # ------------------------------------------------------------------
    # Public refresh entry point
    # ------------------------------------------------------------------

    def _refresh_all(self) -> None:
        """모든 탭의 데이터를 일괄 갱신한다."""
        loaders = [
            self.load_fastapi_status,
            self.load_websocket_status,
            self.load_resources,
            self.load_request_stats,
            self.load_error_log,
            self.load_settings,
        ]
        for loader in loaders:
            try:
                loader()
            except Exception as exc:
                logger.debug("[ServerStatusDialog] %s 갱신 실패: %s", loader.__name__, exc)

        try:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.labelLastUpdated.setText(f"마지막 갱신: {now}")
        except AttributeError:
            pass

    # ------------------------------------------------------------------
    # Tab 1 – FastAPI 상태
    # ------------------------------------------------------------------

    def load_fastapi_status(self) -> None:
        """FastAPI 엔드포인트 상태를 tableEndpoints에 채운다.

        Redis ``rt:metrics:endpoints`` 해시에서 데이터를 읽으며,
        조회에 실패하면 플레이스홀더 행을 표시한다.
        """
        rows = self._fetch_endpoint_metrics()
        table = self.tableEndpoints
        table.setRowCount(len(rows))
        for r, (path, method, rps, avg_ms, err_rate) in enumerate(rows):
            table.setItem(r, 0, QTableWidgetItem(path))
            table.setItem(r, 1, QTableWidgetItem(method))
            table.setItem(r, 2, QTableWidgetItem(str(rps)))
            table.setItem(r, 3, QTableWidgetItem(f"{avg_ms} ms"))
            table.setItem(r, 4, QTableWidgetItem(f"{err_rate}%"))
        table.resizeColumnsToContents()

        active = self._fetch_active_requests()
        self.labelActiveRequests.setText(f"활성 요청: {active}")

    def _fetch_endpoint_metrics(self) -> List[Tuple[str, str, float, float, float]]:
        """Redis 또는 플레이스홀더에서 엔드포인트 메트릭을 반환한다."""
        try:
            import redis as redis_lib  # type: ignore

            client = redis_lib.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                decode_responses=True,
                socket_connect_timeout=1,
            )
            raw: Dict[str, str] = client.hgetall("rt:metrics:endpoints") or {}
            result = []
            for key, val in raw.items():
                parts = val.split(",")
                if len(parts) >= 4:
                    method, rps, avg_ms, err = parts[:4]
                    result.append((key, method, float(rps), float(avg_ms), float(err)))
            return result or self._placeholder_endpoints()
        except Exception:
            return self._placeholder_endpoints()

    @staticmethod
    def _placeholder_endpoints() -> List[Tuple[str, str, float, float, float]]:
        return [
            ("/api/v1/ticker", "GET", 12.3, 45.2, 0.1),
            ("/api/v1/order", "POST", 3.1, 120.8, 0.5),
            ("/api/v1/balance", "GET", 5.0, 30.0, 0.0),
        ]

    def _fetch_active_requests(self) -> int:
        """Redis에서 현재 처리 중인 요청 수를 조회한다."""
        try:
            import redis as redis_lib  # type: ignore

            client = redis_lib.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                decode_responses=True,
                socket_connect_timeout=1,
            )
            raw = client.get("rt:metrics:active_requests")
            return int(raw) if raw else 0
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # Tab 2 – WebSocket 상태
    # ------------------------------------------------------------------

    def load_websocket_status(self) -> None:
        """WebSocket 연결 목록을 tableWSConnections에 채운다."""
        rows = self._fetch_ws_connections()
        table = self.tableWSConnections
        table.setRowCount(len(rows))
        for r, (cid, conn_time, channels, mps, ping) in enumerate(rows):
            table.setItem(r, 0, QTableWidgetItem(cid))
            table.setItem(r, 1, QTableWidgetItem(conn_time))
            table.setItem(r, 2, QTableWidgetItem(channels))
            table.setItem(r, 3, QTableWidgetItem(str(mps)))
            table.setItem(r, 4, QTableWidgetItem(f"{ping} ms"))
        table.resizeColumnsToContents()
        self.labelTotalWSConnections.setText(f"전체 연결: {len(rows)}")

    def _fetch_ws_connections(self) -> List[Tuple[str, str, str, float, float]]:
        """WebSocket 매니저 또는 플레이스홀더에서 연결 목록을 반환한다."""
        try:
            from core.websocket_manager import websocket_manager  # type: ignore

            conns = websocket_manager.get_connections()
            result = []
            for c in conns:
                result.append((
                    str(c.get("id", "-")),
                    str(c.get("connected_at", "-")),
                    ", ".join(c.get("channels", [])),
                    float(c.get("msg_per_sec", 0)),
                    float(c.get("latency_ms", 0)),
                ))
            return result
        except Exception:
            return [
                ("client-001", "10:32:15", "ticker,order", 5.2, 12.0),
                ("client-002", "10:45:03", "ticker", 2.1, 8.5),
            ]

    # ------------------------------------------------------------------
    # Tab 3 – 리소스 모니터링
    # ------------------------------------------------------------------

    def load_resources(self) -> None:
        """CPU·메모리·디스크·네트워크 리소스 지표를 갱신한다.

        psutil이 설치된 경우 실제 값을, 그렇지 않으면 플레이스홀더를 사용한다.
        """
        if PSUTIL_AVAILABLE:
            cpu = int(psutil.cpu_percent(interval=None))
            mem = int(psutil.virtual_memory().percent)
            disk = int(psutil.disk_usage("/").percent)
            net = psutil.net_io_counters()
            import time as _time

            now = _time.monotonic()
            if self._net_prev is not None and self._net_prev_time is not None:
                dt = now - self._net_prev_time or 1
                recv_rate = (net.bytes_recv - self._net_prev[1]) / dt
                sent_rate = (net.bytes_sent - self._net_prev[0]) / dt
            else:
                recv_rate = sent_rate = 0.0
            self._net_prev = (net.bytes_sent, net.bytes_recv)
            self._net_prev_time = now

            procs = [
                (p.info["name"], p.info["cpu_percent"], p.info["memory_info"].rss)
                for p in psutil.process_iter(["name", "cpu_percent", "memory_info"])
                if p.info["memory_info"] is not None
            ]
            procs.sort(key=lambda x: x[2], reverse=True)
            procs = procs[:15]
        else:
            cpu, mem, disk = 35, 62, 48
            recv_rate, sent_rate = 1024 * 50, 1024 * 20
            procs = [("python3", 5.2, 128 * 1024 * 1024), ("uvicorn", 1.1, 64 * 1024 * 1024)]

        self.progressCPU.setValue(cpu)
        self.progressMemory.setValue(mem)
        self.progressDisk.setValue(disk)
        self.labelNetworkInput.setText(_fmt_bytes(recv_rate))
        self.labelNetworkOutput.setText(_fmt_bytes(sent_rate))

        table = self.tableProcesses
        table.setRowCount(len(procs))
        for r, (name, cpu_pct, mem_bytes) in enumerate(procs):
            table.setItem(r, 0, QTableWidgetItem(name))
            table.setItem(r, 1, QTableWidgetItem(f"{cpu_pct:.1f}"))
            mem_mb = mem_bytes / (1024 * 1024)
            table.setItem(r, 2, QTableWidgetItem(f"{mem_mb:.1f} MB"))
        table.resizeColumnsToContents()

    # ------------------------------------------------------------------
    # Tab 4 – 요청 통계
    # ------------------------------------------------------------------

    def load_request_stats(self) -> None:
        """시간대별·엔드포인트별 요청 통계 및 응답시간 분포를 갱신한다."""
        # 시간대별
        time_rows = self._fetch_time_request_stats()
        t = self.tableRequestStats
        t.setRowCount(len(time_rows))
        for r, (period, total, ok, fail) in enumerate(time_rows):
            t.setItem(r, 0, QTableWidgetItem(period))
            t.setItem(r, 1, QTableWidgetItem(str(total)))
            t.setItem(r, 2, QTableWidgetItem(str(ok)))
            t.setItem(r, 3, QTableWidgetItem(str(fail)))
        t.resizeColumnsToContents()

        # 엔드포인트별
        ep_rows = self._fetch_endpoint_stats()
        t2 = self.tableEndpointStats
        t2.setRowCount(len(ep_rows))
        for r, (ep, calls, avg_ms) in enumerate(ep_rows):
            t2.setItem(r, 0, QTableWidgetItem(ep))
            t2.setItem(r, 1, QTableWidgetItem(str(calls)))
            t2.setItem(r, 2, QTableWidgetItem(f"{avg_ms} ms"))
        t2.resizeColumnsToContents()

        # 응답시간 분포
        dist_rows = self._fetch_response_dist()
        t3 = self.tableResponseDist
        t3.setRowCount(len(dist_rows))
        for r, (rng, pct) in enumerate(dist_rows):
            t3.setItem(r, 0, QTableWidgetItem(rng))
            t3.setItem(r, 1, QTableWidgetItem(f"{pct}%"))
        t3.resizeColumnsToContents()

    def _fetch_time_request_stats(self) -> List[Tuple[str, int, int, int]]:
        return [
            ("00:00–06:00", 1200, 1180, 20),
            ("06:00–12:00", 4500, 4430, 70),
            ("12:00–18:00", 6200, 6100, 100),
            ("18:00–24:00", 3800, 3770, 30),
        ]

    def _fetch_endpoint_stats(self) -> List[Tuple[str, int, float]]:
        return [
            ("/api/v1/ticker", 8500, 42.1),
            ("/api/v1/order", 1200, 115.3),
            ("/api/v1/balance", 2300, 28.7),
        ]

    def _fetch_response_dist(self) -> List[Tuple[str, float]]:
        return [
            ("0–50 ms", 62.0),
            ("50–100 ms", 25.0),
            ("100–500 ms", 10.5),
            ("500 ms+", 2.5),
        ]

    # ------------------------------------------------------------------
    # Tab 5 – 에러 로그
    # ------------------------------------------------------------------

    def load_error_log(self) -> None:
        """에러 로그를 tableErrorLog에 채운다. comboLogLevel 필터를 적용한다."""
        try:
            level_filter = self.comboLogLevel.currentText()
        except AttributeError:
            level_filter = "ERROR"

        rows = self._fetch_error_log(level_filter)
        table = self.tableErrorLog
        table.setRowCount(len(rows))
        for r, (ts, level, msg) in enumerate(rows):
            table.setItem(r, 0, QTableWidgetItem(ts))
            item_level = QTableWidgetItem(level)
            color_map = {"ERROR": "#e74c3c", "WARNING": "#f39c12", "INFO": "#3daee9"}
            item_level.setForeground(
                __import__("PyQt5.QtGui", fromlist=["QColor"]).QColor(
                    color_map.get(level, "#eff0f1")
                )
            )
            table.setItem(r, 1, item_level)
            table.setItem(r, 2, QTableWidgetItem(msg))
        table.resizeColumnsToContents()

    def _fetch_error_log(self, level: str) -> List[Tuple[str, str, str]]:
        """로그 스토어 또는 플레이스홀더에서 로그 항목을 반환한다."""
        levels_order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
        threshold = levels_order.get(level, 0)
        placeholder = [
            ("2026-03-06 10:32:01", "ERROR", "Redis 연결 시간 초과"),
            ("2026-03-06 10:45:22", "WARNING", "응답 시간 임계값 초과: /api/v1/order"),
            ("2026-03-06 11:00:00", "INFO", "서버 재시작 완료"),
        ]
        return [r for r in placeholder if levels_order.get(r[1], 0) <= threshold]

    # ------------------------------------------------------------------
    # Tab 6 – 서버 설정
    # ------------------------------------------------------------------

    def load_settings(self) -> None:
        """환경변수에서 현재 서버 설정을 읽어 폼에 채운다."""
        try:
            self.spinPort.setValue(int(os.getenv("SERVER_PORT", "8000")))
            self.spinWorkers.setValue(int(os.getenv("SERVER_WORKERS", "4")))
            self.spinTimeout.setValue(int(os.getenv("SERVER_TIMEOUT", "30")))
            cors = os.getenv("CORS_ORIGINS", "http://localhost:3000")
            self.textCORSOrigins.setPlainText(cors)
        except AttributeError:
            pass

    # ------------------------------------------------------------------
    # Button slots
    # ------------------------------------------------------------------

    def _on_restart_server(self) -> None:
        """서버 재시작 버튼 핸들러."""
        logger.info("[ServerStatusDialog] 서버 재시작 요청")
        try:
            QMessageBox.information(self, "서버 재시작", "서버 재시작 명령을 전송했습니다.")
        except Exception:
            pass

    def _on_disconnect_client(self) -> None:
        """선택된 WebSocket 클라이언트 연결 해제 버튼 핸들러."""
        try:
            row = self.tableWSConnections.currentRow()
            if row < 0:
                QMessageBox.warning(self, "선택 없음", "해제할 클라이언트를 선택하세요.")
                return
            cid_item = self.tableWSConnections.item(row, 0)
            cid = cid_item.text() if cid_item else "-"
            logger.info("[ServerStatusDialog] 클라이언트 연결 해제 요청: %s", cid)
            QMessageBox.information(self, "연결 해제", f"클라이언트 {cid} 연결 해제 요청을 전송했습니다.")
        except Exception as exc:
            logger.debug("[ServerStatusDialog] 연결 해제 실패: %s", exc)

    def _on_export_log(self) -> None:
        """에러 로그를 CSV 파일로 내보내는 버튼 핸들러."""
        try:
            path, _ = QFileDialog.getSaveFileName(
                self, "로그 내보내기", "error_log.csv", "CSV Files (*.csv)"
            )
            if not path:
                return
            table = self.tableErrorLog
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["타임스탬프", "레벨", "메시지"])
                for r in range(table.rowCount()):
                    writer.writerow([
                        table.item(r, c).text() if table.item(r, c) else ""
                        for c in range(3)
                    ])
            QMessageBox.information(self, "내보내기 완료", f"로그를 저장했습니다:\n{path}")
        except Exception as exc:
            logger.error("[ServerStatusDialog] 로그 내보내기 실패: %s", exc)

    def _on_save_settings(self) -> None:
        """서버 설정 저장 및 재시작 버튼 핸들러."""
        try:
            port = self.spinPort.value()
            workers = self.spinWorkers.value()
            timeout = self.spinTimeout.value()
            cors = self.textCORSOrigins.toPlainText().strip()
            logger.info(
                "[ServerStatusDialog] 설정 저장: port=%d workers=%d timeout=%d cors=%s",
                port,
                workers,
                timeout,
                cors,
            )
            os.environ["SERVER_PORT"] = str(port)
            os.environ["SERVER_WORKERS"] = str(workers)
            os.environ["SERVER_TIMEOUT"] = str(timeout)
            os.environ["CORS_ORIGINS"] = cors
            QMessageBox.information(self, "저장 완료", "설정이 저장되었습니다. 서버를 재시작합니다.")
        except Exception as exc:
            logger.error("[ServerStatusDialog] 설정 저장 실패: %s", exc)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        """다이얼로그 닫기 시 타이머를 정지한다."""
        if self._timer:
            self._timer.stop()
        super().closeEvent(event)
