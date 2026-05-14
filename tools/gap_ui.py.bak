# -*- coding: utf-8 -*-
r"""
Gap 상태 단일 창 UI (Health 사전 점검 포함)

변경 요약:
- /status 요청 전에 /health 엔드포인트로 사전 점검을 수행합니다.
- health 실패 시 상태바에 요약을 출력하고, 사용자가 선택하면 내부적으로 서버를 자동 시작하도록 선택할 수 있습니다.
- 자동 재시도(기본)와 자동 서버 시작 옵션을 함께 사용하면 네트워크/서버 불안 시 UI가 자동 복구를 시도합니다.
- 운영 환경에서는 인증/보안/비동기 호출 보강을 권장합니다.
"""
from __future__ import annotations

import sys
import json
import subprocess
import threading
from typing import Any, Dict, List, Optional

import requests
from PyQt5 import QtWidgets, QtCore

DEFAULT_API_URL = "http://127.0.0.1:8080/status?limit=10"
DEFAULT_HEALTH_URL = "http://127.0.0.1:8080/health"
TABLE_COLUMNS = [
    "symbol",
    "job_id",
    "gap_seconds",
    "score",
    "attempts",
    "count_by_tradeid",
    "count_by_window",
    "start",
    "end",
]


class ApiWorker(QtCore.QThread):
    """
    /status 호출을 백그라운드에서 실행하는 QThread.
    """
    result_ready = QtCore.pyqtSignal(dict)
    error = QtCore.pyqtSignal(str)

    def __init__(self, url: str, timeout: float = 6.0):
        super().__init__()
        self.url = url
        self.timeout = timeout

    def run(self):
        try:
            resp = requests.get(self.url, timeout=self.timeout)
            if resp.status_code != 200:
                self.error.emit(f"HTTP {resp.status_code}: {resp.text}")
                return
            data = resp.json()
            self.result_ready.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class GapStatusModel:
    @staticmethod
    def parse_api_response(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = data.get("items") if isinstance(data, dict) else None
        if not items:
            return []
        out = []
        for it in items:
            row = {
                "symbol": it.get("symbol"),
                "job_id": it.get("job_id"),
                "gap_seconds": it.get("gap_seconds"),
                "score": it.get("score"),
                "attempts": it.get("attempts"),
                "count_by_tradeid": it.get("count_by_tradeid"),
                "count_by_window": it.get("count_by_window"),
                "start": it.get("start"),
                "end": it.get("end"),
            }
            out.append(row)
        return out


class GapStatusWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gap Status Viewer")
        self.resize(1100, 520)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        vbox = QtWidgets.QVBoxLayout(central)

        # 상단 컨트롤: API URL, 새로고침, 자동재시도, 재시도 간격, 자동 서버 시작 토글, 서버 시작 버튼, 원본 보기
        h = QtWidgets.QHBoxLayout()
        self.api_input = QtWidgets.QLineEdit(DEFAULT_API_URL)
        self.api_input.setToolTip("Gap status API URL (예: http://127.0.0.1:8080/status?limit=10)")
        h.addWidget(self.api_input)

        self.refresh_btn = QtWidgets.QPushButton("새로고침")
        self.refresh_btn.clicked.connect(self.on_refresh)
        h.addWidget(self.refresh_btn)

        self.auto_retry_cb = QtWidgets.QCheckBox("자동 재시도")
        h.addWidget(self.auto_retry_cb)

        self.retry_spin = QtWidgets.QSpinBox()
        self.retry_spin.setRange(1, 600)
        self.retry_spin.setValue(5)
        self.retry_spin.setSuffix("초")
        self.retry_spin.setToolTip("자동 재시도 간격(초)")
        h.addWidget(self.retry_spin)

        self.auto_start_cb = QtWidgets.QCheckBox("서버 자동 시작 실패 시")
        self.auto_start_cb.setToolTip("health 실패 시 자동으로 로컬 status_api를 시작하려면 체크")
        h.addWidget(self.auto_start_cb)

        self.start_api_btn = QtWidgets.QPushButton("서버 시작")
        self.start_api_btn.setToolTip("로컬 status_api를 동일한 Python 환경으로 새 프로세스에서 시작합니다(개발용).")
        self.start_api_btn.clicked.connect(self.on_start_api)
        h.addWidget(self.start_api_btn)

        self.raw_btn = QtWidgets.QPushButton("원본 JSON 보기")
        self.raw_btn.clicked.connect(self.on_show_raw)
        h.addWidget(self.raw_btn)

        vbox.addLayout(h)

        # 테이블
        self.table = QtWidgets.QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        vbox.addWidget(self.table)

        # 상태 표시줄
        self.status = QtWidgets.QLabel("Ready")
        self.statusBar().addWidget(self.status)

        # 내부 상태
        self._last_raw_json: Optional[Dict[str, Any]] = None
        self._worker: Optional[ApiWorker] = None
        self._auto_retry_timer: Optional[QtCore.QTimer] = None
        self._api_process: Optional[subprocess.Popen] = None

        # 초기 로드(지연)
        QtCore.QTimer.singleShot(100, self.on_refresh)

    def set_status(self, text: str):
        self.status.setText(text)
        QtWidgets.QApplication.processEvents()

    def on_show_raw(self):
        if not self._last_raw_json:
            QtWidgets.QMessageBox.information(self, "원본 없음", "원본 JSON이 없습니다. 먼저 새로고침하세요.")
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("원본 JSON")
        dlg.resize(900, 600)
        lay = QtWidgets.QVBoxLayout(dlg)
        te = QtWidgets.QPlainTextEdit()
        te.setReadOnly(True)
        pretty = json.dumps(self._last_raw_json, ensure_ascii=False, indent=2)
        te.setPlainText(pretty)
        lay.addWidget(te)
        btn = QtWidgets.QPushButton("닫기")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn)
        dlg.exec_()

    def check_health(self, health_url: str = DEFAULT_HEALTH_URL, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
        """
        /health 를 동기 호출하여 결과를 반환. 실패 시 None 반환.
        - UI 블로킹을 짧게 하므로 timeout은 작게 설정(기본 2s)
        """
        try:
            resp = requests.get(health_url, timeout=timeout)
            if resp.status_code in (200, 503):
                try:
                    return resp.json()
                except Exception:
                    return {"status": "unknown", "raw_status": resp.status_code}
            return None
        except Exception:
            return None

    def on_refresh(self):
        """
        새로고침: /health 선검사 -> /status 호출
        """
        url = self.api_input.text().strip() or DEFAULT_API_URL
        # health URL 유추
        health_url = url.split("?")[0].replace("/status", "/health")

        self.set_status(f"health 체크: {health_url} ...")
        QtWidgets.QApplication.processEvents()

        health = self.check_health(health_url, timeout=2.0)
        if health is None:
            # health 체크 실패
            self.set_status("Health 체크 실패")
            # 자동 서버 시작 옵션이 켜져 있으면 시도
            if self.auto_start_cb.isChecked():
                self.set_status("Health 실패 — 서버 자동 시작 시도")
                QtWidgets.QApplication.processEvents()
                self.on_start_api(auto=True)
                # 서버가 올라올 시간을 기다리고 재시도 타이머 설정
                self.schedule_retry()
                return
            else:
                # 자동 재시도 설정에 따라 타이머 설정
                if self.auto_retry_cb.isChecked():
                    self.set_status("Health 실패 — 자동 재시도 대기")
                    self.schedule_retry()
                else:
                    QtWidgets.QMessageBox.warning(self, "요청 실패", "서버의 /health 검사에 실패했습니다.\n서버가 실행 중인지 확인하세요.")
                return

        # health 반환값이 있을 때 상태 판단
        status_val = health.get("status") if isinstance(health, dict) else None
        if status_val not in ("ok",):
            # degraded 혹은 기타 상태
            self.set_status(f"서버 상태: {status_val}")
            if self.auto_retry_cb.isChecked():
                self.schedule_retry()
            QtWidgets.QMessageBox.warning(self, "서버 상태", f"/health 상태: {status_val}\n상세: {json.dumps(health, ensure_ascii=False)}")
            return

        # health ok -> 실제 /status 호출 (비동기 Worker)
        self.set_status(f"/status 요청: {url}")
        if self._worker is not None and self._worker.isRunning():
            try:
                self._worker.terminate()
                self._worker.wait(200)
            except Exception:
                pass
        self._worker = ApiWorker(url)
        self._worker.result_ready.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def schedule_retry(self):
        interval = max(1, self.retry_spin.value()) * 1000
        if self._auto_retry_timer is None:
            self._auto_retry_timer = QtCore.QTimer(self)
            self._auto_retry_timer.timeout.connect(self.on_refresh)
        self._auto_retry_timer.start(interval)
        self.set_status(f"자동 재시도 예약: {self.retry_spin.value()}초 후")

    def _on_result(self, data: Dict[str, Any]):
        self._last_raw_json = data
        rows = GapStatusModel.parse_api_response(data)
        self._populate_table(rows)
        self.set_status(f"완료: {len(rows)} 항목")
        if self._auto_retry_timer:
            self._auto_retry_timer.stop()

    def _on_error(self, err: str):
        self.set_status(f"요청 실패: {err}")
        QtWidgets.QMessageBox.warning(self, "요청 실패", f"API 호출 중 예외가 발생했습니다:\n{err}")
        if self.auto_retry_cb.isChecked():
            self.schedule_retry()

    def _populate_table(self, rows: List[Dict[str, Any]]):
        self.table.setRowCount(0)
        for r in rows:
            row_index = self.table.rowCount()
            self.table.insertRow(row_index)
            for col_idx, col in enumerate(TABLE_COLUMNS):
                val = r.get(col)
                txt = "" if val is None else str(val)
                item = QtWidgets.QTableWidgetItem(txt)
                if len(txt) > 120:
                    item.setToolTip(txt)
                self.table.setItem(row_index, col_idx, item)

    def on_start_api(self, auto: bool = False):
        """
        현재 Python 환경으로 status_api를 새 프로세스로 시작.
        - auto=True 이면 사용자 확인 없이 시도(자동 시작 옵션 시 사용)
        """
        if self._api_process is not None and self._api_process.poll() is None:
            self.set_status("이미 서버가 실행 중입니다.")
            return

        py = sys.executable
        args = [py, "-m", "src.02_data.gap.status_api", "--host", "127.0.0.1", "--port", "8080", "--redis-url", "redis://localhost:6379/0"]

        try:
            creationflags = 0
            if sys.platform.startswith("win"):
                creationflags = 0x00000010  # CREATE_NEW_CONSOLE
            self._api_process = subprocess.Popen(args, creationflags=creationflags)
            if not auto:
                QtWidgets.QMessageBox.information(self, "서버 시작", f"status_api를 새 프로세스로 시작했습니다. PID={self._api_process.pid}")
            # 잠시 대기 후 자동 새로고침 시도
            threading.Timer(1.5, self.on_refresh).start()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "서버 시작 실패", f"서버 시작 중 예외: {e}")

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            try:
                self._worker.terminate()
                self._worker.wait(200)
            except Exception:
                pass
        if self._auto_retry_timer is not None and self._auto_retry_timer.isActive():
            self._auto_retry_timer.stop()
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = GapStatusWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()