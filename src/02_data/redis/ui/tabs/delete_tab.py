# -*- coding: utf-8 -*-
"""Redis 데이터 삭제 탭 (QThread Worker 패턴, 메인스레드 블로킹 없음)

지원 작업:
  - 패턴별 키 삭제 (SCAN + DEL): candles:*, ticker:*, feature:*, gap_fill_queue 등
  - 사용자 정의 패턴 삭제
  - FLUSHDB (전체 삭제, 2단계 확인)
"""
from __future__ import annotations

import os
import logging
from typing import Optional, Dict

try:
    from PyQt5.QtWidgets import QWidget, QMessageBox, QInputDialog, QLineEdit
    from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "delete_tab.ui")


def _get_redis_client(conn_params: dict):
    """Redis 클라이언트를 반환합니다. 실패 시 None."""
    try:
        import redis as redis_mod  # type: ignore[import]
        redis_url = conn_params.get("url") or os.getenv("REDIS_URL")
        if redis_url:
            return redis_mod.Redis.from_url(redis_url, socket_connect_timeout=3)
        host     = conn_params.get("host") or os.getenv("REDIS_HOST", "127.0.0.1")
        port     = int(conn_params.get("port") or os.getenv("REDIS_PORT", "6379"))
        password = conn_params.get("password") or os.getenv("REDIS_PASSWORD") or None
        db_num   = int(conn_params.get("db") or os.getenv("REDIS_DB", "0"))
        return redis_mod.Redis(
            host=host, port=port, password=password, db=db_num,
            socket_connect_timeout=3, decode_responses=False,
        )
    except Exception as exc:
        logger.debug("[Redis DeleteTab] 연결 실패: %s", exc)
        return None


if _HAS_QT:
    # ------------------------------------------------------------------
    # QThread Worker
    # ------------------------------------------------------------------
    class _RedisWorker(QThread):
        """Redis 키 삭제 Worker."""
        finished = pyqtSignal(str)
        error    = pyqtSignal(str)

        ACTION_PATTERN  = "pattern"
        ACTION_KEY      = "key"
        ACTION_FLUSHDB  = "flushdb"

        def __init__(self, conn_params: dict, action: str, target: str = ""):
            super().__init__()
            self._conn_params = conn_params
            self._action  = action
            self._target  = target

        def run(self):
            try:
                r = _get_redis_client(self._conn_params)
                if r is None:
                    self.error.emit("Redis 연결 실패 — 환경 변수(REDIS_HOST 등) 확인")
                    return
                if self._action == self.ACTION_FLUSHDB:
                    r.flushdb()
                    self.finished.emit("FLUSHDB 완료 — 모든 키 삭제됨")
                elif self._action == self.ACTION_PATTERN:
                    count = self._scan_del(r, self._target)
                    self.finished.emit(f"패턴 '{self._target}' 키 {count:,}개 삭제 완료")
                elif self._action == self.ACTION_KEY:
                    r.delete(self._target)
                    self.finished.emit(f"키 '{self._target}' 삭제 완료")
            except Exception as exc:
                self.error.emit(str(exc)[:200])

        def _scan_del(self, r, pattern: str) -> int:
            deleted = 0
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor, match=pattern, count=500)
                if keys:
                    r.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            return deleted

    class _CountWorker(QThread):
        """Redis DBSIZE Worker."""
        finished = pyqtSignal(str)
        error    = pyqtSignal(str)

        def __init__(self, conn_params: dict):
            super().__init__()
            self._conn_params = conn_params

        def run(self):
            try:
                r = _get_redis_client(self._conn_params)
                if r is None:
                    self.error.emit("연결 실패")
                    return
                count = r.dbsize()
                self.finished.emit(f"전체 키 수: {count:,}")
            except Exception as exc:
                self.error.emit(str(exc)[:100])

    # ------------------------------------------------------------------
    # 탭 위젯
    # ------------------------------------------------------------------
    class DeleteTab(QWidget):
        """Redis 데이터 삭제 탭.

        패턴 삭제 / FLUSHDB를 QThread Worker로 안전하게 실행합니다.
        """

        def __init__(self, conn_params: Optional[Dict] = None, parent=None):
            super().__init__(parent)
            self._conn_params: Dict = conn_params or {}
            self._worker: Optional[_RedisWorker] = None
            self._count_worker: Optional[_CountWorker] = None

            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[Redis DeleteTab] UI 로드 실패: %s", exc)
                self._build_fallback_ui()

            self._setup_ui()
            self._bind_signals()

        # ------------------------------------------------------------------
        # UI 초기화
        # ------------------------------------------------------------------

        def _build_fallback_ui(self) -> None:
            from PyQt5.QtWidgets import (
                QVBoxLayout, QLabel, QLineEdit, QPushButton, QProgressBar,
            )
            layout = QVBoxLayout(self)
            self.labelKeyCount          = QLabel("전체 키 수: -")
            self.btnRefreshCount        = QPushButton("🔄 키 수 새로고침")
            self.btnDeleteCandles       = QPushButton("🗑️ candles:* 삭제")
            self.btnDeleteTicker        = QPushButton("🗑️ ticker:* 삭제")
            self.btnDeleteFeature       = QPushButton("🗑️ feature:* 삭제")
            self.btnDeleteGapQueue      = QPushButton("🗑️ gap_fill_queue 삭제")
            self.editCustomPattern      = QLineEdit()
            self.btnDeleteCustomPattern = QPushButton("🗑️ 패턴 삭제")
            self.btnFlushDb             = QPushButton("🔥 FLUSHDB 실행")
            self.progressDelete         = QProgressBar()
            self.labelResult            = QLabel("")
            for w in (
                self.labelKeyCount, self.btnRefreshCount,
                self.btnDeleteCandles, self.btnDeleteTicker,
                self.btnDeleteFeature, self.btnDeleteGapQueue,
                self.editCustomPattern, self.btnDeleteCustomPattern,
                self.btnFlushDb, self.progressDelete, self.labelResult,
            ):
                layout.addWidget(w)

        def _setup_ui(self) -> None:
            pb = getattr(self, "progressDelete", None)
            if pb is not None:
                pb.setVisible(False)
                pb.setMaximum(0)

        # ------------------------------------------------------------------
        # 시그널 연결
        # ------------------------------------------------------------------

        def _bind_signals(self) -> None:
            pattern_buttons = {
                "btnDeleteCandles":       "candles:*",
                "btnDeleteTicker":        "ticker:*",
                "btnDeleteFeature":       "feature:*",
            }
            for btn_name, pattern in pattern_buttons.items():
                btn = getattr(self, btn_name, None)
                if btn is not None:
                    btn.clicked.connect(
                        lambda checked=False, p=pattern: self._confirm_and_run_pattern(p)
                    )

            btn_gap = getattr(self, "btnDeleteGapQueue", None)
            if btn_gap is not None:
                btn_gap.clicked.connect(
                    lambda: self._confirm_and_run_key("gap_fill_queue")
                )

            btn_custom = getattr(self, "btnDeleteCustomPattern", None)
            if btn_custom is not None:
                btn_custom.clicked.connect(self._on_custom_pattern_clicked)

            btn_flush = getattr(self, "btnFlushDb", None)
            if btn_flush is not None:
                btn_flush.clicked.connect(self._on_flushdb_clicked)

            btn_cnt = getattr(self, "btnRefreshCount", None)
            if btn_cnt is not None:
                btn_cnt.clicked.connect(self._refresh_count)

        # ------------------------------------------------------------------
        # 핸들러
        # ------------------------------------------------------------------

        def _confirm_and_run_pattern(self, pattern: str) -> None:
            ret = QMessageBox.warning(
                self, "⚠️ 삭제 확인",
                f"패턴 '{pattern}' 에 해당하는 모든 키를 삭제하시겠습니까?\n\n삭제된 데이터는 복구할 수 없습니다!",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return
            self._run_worker(_RedisWorker.ACTION_PATTERN, pattern)

        def _confirm_and_run_key(self, key: str) -> None:
            ret = QMessageBox.warning(
                self, "⚠️ 삭제 확인",
                f"키 '{key}' 를 삭제하시겠습니까?\n\n삭제된 데이터는 복구할 수 없습니다!",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return
            self._run_worker(_RedisWorker.ACTION_KEY, key)

        def _on_custom_pattern_clicked(self) -> None:
            edit = getattr(self, "editCustomPattern", None)
            pattern = edit.text().strip() if edit else ""
            if not pattern:
                QMessageBox.warning(self, "입력 오류", "삭제할 패턴을 입력하세요.")
                return
            self._confirm_and_run_pattern(pattern)

        def _on_flushdb_clicked(self) -> None:
            # 1단계 경고
            ret = QMessageBox.warning(
                self, "⚠️ Redis 전체 삭제",
                "Redis DB의 모든 키를 삭제합니다!\n\n이 작업은 취소할 수 없습니다.\n정말로 계속하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return
            # 2단계 텍스트 확인
            text, ok = QInputDialog.getText(
                self, "최종 확인",
                "확인하려면 'FLUSH' 를 입력하세요:",
                QLineEdit.Normal, "",
            )
            if not ok or text.strip() != "FLUSH":
                QMessageBox.information(self, "취소", "작업이 취소되었습니다.")
                return
            self._run_worker(_RedisWorker.ACTION_FLUSHDB, "")

        # ------------------------------------------------------------------
        # 건수 조회
        # ------------------------------------------------------------------

        def _refresh_count(self) -> None:
            if self._count_worker and self._count_worker.isRunning():
                return
            lbl = getattr(self, "labelKeyCount", None)
            if lbl is not None:
                lbl.setText("전체 키 수: 조회 중...")
            self._count_worker = _CountWorker(self._conn_params)
            self._count_worker.finished.connect(
                lambda msg: lbl.setText(msg) if lbl else None
            )
            self._count_worker.error.connect(
                lambda _: lbl.setText("전체 키 수: 조회 실패") if lbl else None
            )
            self._count_worker.start()

        def _run_worker(self, action: str, target: str) -> None:
            if self._worker and self._worker.isRunning():
                QMessageBox.information(self, "진행 중", "이미 작업이 진행 중입니다.")
                return
            self._set_busy(True)
            self._worker = _RedisWorker(self._conn_params, action, target)
            self._worker.finished.connect(self._on_finished)
            self._worker.error.connect(self._on_error)
            self._worker.start()

        # ------------------------------------------------------------------
        # Worker 완료 슬롯
        # ------------------------------------------------------------------

        @pyqtSlot(str)
        def _on_finished(self, msg: str) -> None:
            self._set_busy(False)
            lbl = getattr(self, "labelResult", None)
            if lbl is not None:
                lbl.setStyleSheet("color: #16A34A; font-weight: bold;")
                lbl.setText(f"✅ {msg}")
            self._refresh_count()

        @pyqtSlot(str)
        def _on_error(self, msg: str) -> None:
            self._set_busy(False)
            lbl = getattr(self, "labelResult", None)
            if lbl is not None:
                lbl.setStyleSheet("color: #DC2626; font-weight: bold;")
                lbl.setText(f"🔴 오류: {msg[:180]}")
            logger.warning("[Redis DeleteTab] 오류: %s", msg)

        def _set_busy(self, busy: bool) -> None:
            pb = getattr(self, "progressDelete", None)
            if pb is not None:
                pb.setVisible(busy)
            for name in (
                "btnDeleteCandles", "btnDeleteTicker", "btnDeleteFeature",
                "btnDeleteGapQueue", "btnDeleteCustomPattern",
                "btnFlushDb", "btnRefreshCount",
            ):
                btn = getattr(self, name, None)
                if btn is not None:
                    btn.setEnabled(not busy)
            if busy:
                lbl = getattr(self, "labelResult", None)
                if lbl is not None:
                    lbl.setStyleSheet("")
                    lbl.setText("⏳ 작업 진행 중...")

        # ------------------------------------------------------------------
        # 생명 주기
        # ------------------------------------------------------------------

        def start_updates(self, interval_ms: int = 0) -> None:
            self._refresh_count()

        def stop_updates(self) -> None:
            for worker in (self._worker, self._count_worker):
                if worker is not None and worker.isRunning():
                    worker.quit()
                    worker.wait(2000)

        def closeEvent(self, event) -> None:
            self.stop_updates()
            super().closeEvent(event)

else:
    class DeleteTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 폴백 스텁."""
        def __init__(self, conn_params=None, parent=None): pass
        def start_updates(self, interval_ms: int = 0) -> None: pass
        def stop_updates(self) -> None: pass
