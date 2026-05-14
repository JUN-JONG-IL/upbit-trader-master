# -*- coding: utf-8 -*-
"""MongoDB 데이터 삭제 탭 (QThread Worker 패턴, 메인스레드 블로킹 없음)

지원 작업:
  - 전체 문서 삭제 (delete_many, 컬렉션 유지)
  - 컬렉션 Drop
  - 전체 컬렉션 Drop (2단계 확인)
"""
from __future__ import annotations

import os
import logging
from typing import Optional, Dict
from urllib.parse import quote_plus

try:
    from PyQt5.QtWidgets import QWidget, QMessageBox, QInputDialog, QLineEdit
    from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)
_UI_PATH = os.path.join(os.path.dirname(__file__), "delete_tab.ui")

# 허용 컬렉션 화이트리스트
_ALLOWED_COLLECTIONS = frozenset({
    "symbols", "ui_settings", "strategies",
    "performance_baseline", "collection_stats",
})


def _get_mongo_db(conn_params: dict):
    """MongoDB DB 객체를 반환합니다. 실패 시 None."""
    try:
        import pymongo  # type: ignore[import]
        host     = conn_params.get("host") or os.getenv("MONGO_HOST", "localhost")
        port     = conn_params.get("port") or os.getenv("MONGO_PORT", "27017")
        user     = conn_params.get("user") or os.getenv("MONGO_USER") or ""
        password = conn_params.get("password") or os.getenv("MONGO_PASSWORD") or ""
        db_name  = conn_params.get("database") or os.getenv("MONGO_DB", "upbit_trader")
        if user and password:
            uri = (
                f"mongodb://{quote_plus(user)}:{quote_plus(password)}"
                f"@{host}:{port}/{db_name}?authSource=admin"
            )
        else:
            uri = f"mongodb://{host}:{port}/{db_name}"
        client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
        return client[db_name]
    except Exception as exc:
        logger.debug("[Mongo DeleteTab] 연결 실패: %s", exc)
        return None


if _HAS_QT:
    # ------------------------------------------------------------------
    # QThread Worker
    # ------------------------------------------------------------------
    class _MongoWorker(QThread):
        """MongoDB 컬렉션 작업 Worker."""
        finished = pyqtSignal(str)
        error    = pyqtSignal(str)

        ACTION_DELETE_ALL   = "delete_all"
        ACTION_DROP         = "drop"
        ACTION_DROP_ALL     = "drop_all"

        def __init__(self, conn_params: dict, action: str, collection: str = ""):
            super().__init__()
            self._conn_params = conn_params
            self._action     = action
            self._collection = collection

        def run(self):
            try:
                db = _get_mongo_db(self._conn_params)
                if db is None:
                    self.error.emit("MongoDB 연결 실패 — 환경 변수(MONGO_HOST 등) 확인")
                    return
                if self._action == self.ACTION_DELETE_ALL:
                    result = db[self._collection].delete_many({})
                    self.finished.emit(
                        f"컬렉션 '{self._collection}' 전체 문서 {result.deleted_count:,}건 삭제 완료"
                    )
                elif self._action == self.ACTION_DROP:
                    db.drop_collection(self._collection)
                    self.finished.emit(f"컬렉션 '{self._collection}' Drop 완료")
                elif self._action == self.ACTION_DROP_ALL:
                    names = db.list_collection_names()
                    for name in names:
                        db.drop_collection(name)
                    self.finished.emit(f"전체 {len(names)}개 컬렉션 Drop 완료")
            except Exception as exc:
                self.error.emit(str(exc)[:200])

    class _CountWorker(QThread):
        """문서 수 조회 Worker."""
        finished = pyqtSignal(str)
        error    = pyqtSignal(str)

        def __init__(self, conn_params: dict, collection: str):
            super().__init__()
            self._conn_params = conn_params
            self._collection = collection

        def run(self):
            try:
                db = _get_mongo_db(self._conn_params)
                if db is None:
                    self.error.emit("연결 실패")
                    return
                # estimated_document_count()는 메타데이터 기반으로 빠르지만
                # 진행 중인 쓰기가 많을 경우 약간 오래된 값을 반환할 수 있음.
                # 정확한 수가 필요하면 count_documents({})로 교체 가능.
                count = db[self._collection].estimated_document_count()
                self.finished.emit(f"문서 수: {count:,} 건")
            except Exception as exc:
                self.error.emit(str(exc)[:100])

    # ------------------------------------------------------------------
    # 탭 위젯
    # ------------------------------------------------------------------
    class DeleteTab(QWidget):
        """MongoDB 데이터 삭제 탭.

        전체 문서 삭제 / 컬렉션 Drop / 전체 Drop을 QThread Worker로 안전하게 실행합니다.
        """

        def __init__(self, conn_params: Optional[Dict] = None, parent=None):
            super().__init__(parent)
            self._conn_params: Dict = conn_params or {}
            self._worker: Optional[_MongoWorker] = None
            self._count_worker: Optional[_CountWorker] = None

            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[Mongo DeleteTab] UI 로드 실패: %s", exc)
                self._build_fallback_ui()

            self._setup_ui()
            self._bind_signals()

        # ------------------------------------------------------------------
        # UI 초기화
        # ------------------------------------------------------------------

        def _build_fallback_ui(self) -> None:
            from PyQt5.QtWidgets import (
                QVBoxLayout, QLabel, QComboBox, QRadioButton,
                QPushButton, QProgressBar,
            )
            layout = QVBoxLayout(self)
            self.comboCollection   = QComboBox()
            for c in sorted(_ALLOWED_COLLECTIONS):
                self.comboCollection.addItem(c)
            self.radioDeleteAll    = QRadioButton("전체 문서 삭제")
            self.radioDropCollection = QRadioButton("컬렉션 Drop")
            self.radioDropAll      = QRadioButton("전체 컬렉션 Drop")
            self.radioDeleteAll.setChecked(True)
            self.labelDocCount     = QLabel("문서 수: -")
            self.btnRefreshCount   = QPushButton("🔄 건수 새로고침")
            self.btnDelete         = QPushButton("🗑️ 선택 작업 실행")
            self.progressDelete    = QProgressBar()
            self.labelResult       = QLabel("")
            for w in (
                self.comboCollection,
                self.radioDeleteAll, self.radioDropCollection, self.radioDropAll,
                self.labelDocCount, self.btnRefreshCount,
                self.btnDelete, self.progressDelete, self.labelResult,
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
            btn = getattr(self, "btnDelete", None)
            if btn is not None:
                btn.clicked.connect(self._on_btn_delete_clicked)
            btn_cnt = getattr(self, "btnRefreshCount", None)
            if btn_cnt is not None:
                btn_cnt.clicked.connect(self._refresh_count)
            combo = getattr(self, "comboCollection", None)
            if combo is not None:
                combo.currentTextChanged.connect(lambda _: self._refresh_count())

        # ------------------------------------------------------------------
        # 건수 조회
        # ------------------------------------------------------------------

        def _refresh_count(self) -> None:
            col = self._selected_collection()
            if not col:
                return
            if self._count_worker and self._count_worker.isRunning():
                return
            lbl = getattr(self, "labelDocCount", None)
            if lbl is not None:
                lbl.setText("문서 수: 조회 중...")
            self._count_worker = _CountWorker(self._conn_params, col)
            self._count_worker.finished.connect(
                lambda msg: lbl.setText(msg) if lbl else None
            )
            self._count_worker.error.connect(
                lambda _: lbl.setText("문서 수: 조회 실패") if lbl else None
            )
            self._count_worker.start()

        # ------------------------------------------------------------------
        # 삭제 버튼
        # ------------------------------------------------------------------

        def _on_btn_delete_clicked(self) -> None:
            radio_all = getattr(self, "radioDropAll", None)
            if radio_all and radio_all.isChecked():
                # 전체 Drop — 2단계 확인
                ret = QMessageBox.warning(
                    self, "⚠️ 전체 컬렉션 Drop",
                    "MongoDB의 모든 컬렉션을 Drop합니다!\n\n이 작업은 취소할 수 없습니다.\n계속하시겠습니까?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                )
                if ret != QMessageBox.Yes:
                    return
                text, ok = QInputDialog.getText(
                    self, "최종 확인",
                    "확인하려면 'DELETE ALL' 을 입력하세요:",
                    QLineEdit.Normal, "",
                )
                if not ok or text.strip() != "DELETE ALL":
                    QMessageBox.information(self, "취소", "작업이 취소되었습니다.")
                    return
                self._run_worker(_MongoWorker.ACTION_DROP_ALL, "")
                return

            col = self._selected_collection()
            if not col:
                QMessageBox.warning(self, "오류", "유효한 컬렉션을 선택하세요.")
                return

            radio_drop = getattr(self, "radioDropCollection", None)
            action = _MongoWorker.ACTION_DROP if (radio_drop and radio_drop.isChecked()) else _MongoWorker.ACTION_DELETE_ALL
            action_label = "Drop" if action == _MongoWorker.ACTION_DROP else "전체 문서 삭제"

            ret = QMessageBox.warning(
                self, "⚠️ 삭제 확인",
                f"컬렉션 '{col}' 를 {action_label}하시겠습니까?\n\n삭제된 데이터는 복구할 수 없습니다!",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return
            self._run_worker(action, col)

        def _selected_collection(self) -> str:
            combo = getattr(self, "comboCollection", None)
            if combo is None:
                return ""
            return combo.currentText().strip()

        def _run_worker(self, action: str, collection: str) -> None:
            if self._worker and self._worker.isRunning():
                QMessageBox.information(self, "진행 중", "이미 작업이 진행 중입니다.")
                return
            self._set_busy(True)
            self._worker = _MongoWorker(self._conn_params, action, collection)
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
            logger.warning("[Mongo DeleteTab] 오류: %s", msg)

        def _set_busy(self, busy: bool) -> None:
            pb = getattr(self, "progressDelete", None)
            if pb is not None:
                pb.setVisible(busy)
            for name in ("btnDelete", "btnRefreshCount"):
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
