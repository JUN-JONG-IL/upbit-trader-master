# -*- coding: utf-8 -*-
"""Kafka 데이터 삭제 탭 (QThread Worker 패턴, 메인스레드 블로킹 없음)

지원 작업:
  - 토픽 메시지 Purge (retention.ms=1ms 일시 설정 후 복원)
  - 토픽 삭제
  - 전체 토픽 Purge (2단계 확인)
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

# 기본 retention 복원 값 (7일)
_DEFAULT_RETENTION_MS = "604800000"

# 허용 토픽 목록 (화이트리스트)
_KNOWN_TOPICS = frozenset({
    "upbit.candles.1m", "upbit.candles.5m", "upbit.candles.1h",
    "upbit.ticks", "upbit.orderbook", "upbit.events",
    "db.timescale.archive",
})


def _get_kafka_admin(conn_params: dict):
    """Kafka AdminClient를 반환합니다. 실패 시 None."""
    try:
        from confluent_kafka.admin import AdminClient  # type: ignore[import]
        brokers = (
            conn_params.get("brokers")
            or conn_params.get("bootstrap_servers")
            or os.getenv("KAFKA_BROKERS", "localhost:9092")
        )
        return AdminClient({"bootstrap.servers": brokers})
    except ImportError:
        logger.debug("[Kafka DeleteTab] confluent-kafka 미설치")
        return None
    except Exception as exc:
        logger.debug("[Kafka DeleteTab] Kafka 연결 실패: %s", exc)
        return None


if _HAS_QT:
    # ------------------------------------------------------------------
    # QThread Worker
    # ------------------------------------------------------------------
    class _KafkaWorker(QThread):
        """Kafka 토픽 작업 Worker."""
        finished = pyqtSignal(str)
        error    = pyqtSignal(str)

        ACTION_PURGE        = "purge"
        ACTION_DELETE_TOPIC = "delete_topic"
        ACTION_PURGE_ALL    = "purge_all"

        def __init__(self, conn_params: dict, action: str, topic: str = ""):
            super().__init__()
            self._conn_params = conn_params
            self._action = action
            self._topic  = topic

        def run(self):
            try:
                if self._action == self.ACTION_PURGE:
                    self._purge_topic(self._topic)
                elif self._action == self.ACTION_DELETE_TOPIC:
                    self._delete_topic(self._topic)
                elif self._action == self.ACTION_PURGE_ALL:
                    self._purge_all_topics()
            except Exception as exc:
                self.error.emit(str(exc)[:200])

        def _purge_topic(self, topic: str) -> None:
            from confluent_kafka.admin import ConfigResource  # type: ignore[import]
            admin = _get_kafka_admin(self._conn_params)
            if admin is None:
                self.error.emit("Kafka AdminClient 연결 실패")
                return
            try:
                rtype = ConfigResource.Type.TOPIC
                futures = admin.alter_configs(
                    {ConfigResource(rtype, topic): {"retention.ms": "1"}}
                )
                for _, f in futures.items():
                    f.result()
                QThread.msleep(2000)   # time.sleep 대신 Qt 친화적 msleep 사용
                futures = admin.alter_configs(
                    {ConfigResource(rtype, topic): {"retention.ms": _DEFAULT_RETENTION_MS}}
                )
                for _, f in futures.items():
                    f.result()
                self.finished.emit(f"토픽 '{topic}' Purge 완료 (retention 복원됨)")
            finally:
                admin.close()

        def _delete_topic(self, topic: str) -> None:
            admin = _get_kafka_admin(self._conn_params)
            if admin is None:
                self.error.emit("Kafka AdminClient 연결 실패")
                return
            try:
                fs = admin.delete_topics([topic], operation_timeout=10)
                for t, f in fs.items():
                    f.result()
                self.finished.emit(f"토픽 '{topic}' 삭제 완료")
            finally:
                admin.close()

        def _purge_all_topics(self) -> None:
            from confluent_kafka.admin import ConfigResource  # type: ignore[import]
            admin = _get_kafka_admin(self._conn_params)
            if admin is None:
                self.error.emit("Kafka AdminClient 연결 실패")
                return
            try:
                metadata = admin.list_topics(timeout=10)
                topics = [t for t in metadata.topics if not t.startswith("__")]
                rtype = ConfigResource.Type.TOPIC
                futures = admin.alter_configs(
                    {ConfigResource(rtype, t): {"retention.ms": "1"} for t in topics}
                )
                for _, f in futures.items():
                    f.result()
                QThread.msleep(2000)   # time.sleep 대신 Qt 친화적 msleep 사용
                futures = admin.alter_configs(
                    {ConfigResource(rtype, t): {"retention.ms": _DEFAULT_RETENTION_MS}
                     for t in topics}
                )
                for _, f in futures.items():
                    f.result()
                self.finished.emit(f"전체 {len(topics)}개 토픽 Purge 완료")
            finally:
                admin.close()

    # ------------------------------------------------------------------
    # 탭 위젯
    # ------------------------------------------------------------------
    class DeleteTab(QWidget):
        """Kafka 데이터 삭제 탭.

        토픽 Purge / 토픽 삭제 / 전체 Purge를 QThread Worker로 안전하게 실행합니다.
        """

        def __init__(self, conn_params: Optional[Dict] = None, parent=None):
            super().__init__(parent)
            self._conn_params: Dict = conn_params or {}
            self._worker: Optional[_KafkaWorker] = None

            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[Kafka DeleteTab] UI 로드 실패: %s", exc)
                self._build_fallback_ui()

            self._setup_ui()
            self._bind_signals()

        # ------------------------------------------------------------------
        # UI 초기화
        # ------------------------------------------------------------------

        def _build_fallback_ui(self) -> None:
            from PyQt5.QtWidgets import (
                QVBoxLayout, QLabel, QComboBox, QRadioButton,
                QLineEdit, QPushButton, QProgressBar,
            )
            layout = QVBoxLayout(self)
            self.comboTopic       = QComboBox()
            for t in sorted(_KNOWN_TOPICS):
                self.comboTopic.addItem(t)
            self.comboTopic.addItem("직접 입력")
            self.editCustomTopic  = QLineEdit()
            self.radioPurge       = QRadioButton("메시지 Purge")
            self.radioDeleteTopic = QRadioButton("토픽 삭제")
            self.radioPurgeAll    = QRadioButton("전체 Purge")
            self.radioPurge.setChecked(True)
            self.btnDelete        = QPushButton("🗑️ 선택 작업 실행")
            self.progressDelete   = QProgressBar()
            self.labelResult      = QLabel("")
            for w in (
                self.comboTopic, self.editCustomTopic,
                self.radioPurge, self.radioDeleteTopic, self.radioPurgeAll,
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

            combo = getattr(self, "comboTopic", None)
            if combo is not None:
                combo.currentTextChanged.connect(self._on_topic_changed)

        @pyqtSlot(str)
        def _on_topic_changed(self, text: str) -> None:
            edit = getattr(self, "editCustomTopic", None)
            if edit is not None:
                edit.setEnabled(text == "직접 입력")

        # ------------------------------------------------------------------
        # 삭제 버튼
        # ------------------------------------------------------------------

        def _on_btn_delete_clicked(self) -> None:
            radio_all  = getattr(self, "radioPurgeAll", None)
            radio_del  = getattr(self, "radioDeleteTopic", None)

            if radio_all and radio_all.isChecked():
                # 전체 Purge — 2단계 확인
                ret = QMessageBox.warning(
                    self, "⚠️ 전체 토픽 Purge",
                    "모든 Kafka 토픽의 메시지를 Purge합니다!\n\n이 작업은 취소할 수 없습니다.\n계속하시겠습니까?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                )
                if ret != QMessageBox.Yes:
                    return
                text, ok = QInputDialog.getText(
                    self, "최종 확인",
                    "확인하려면 'PURGE' 를 입력하세요:",
                    QLineEdit.Normal, "",
                )
                if not ok or text.strip() != "PURGE":
                    QMessageBox.information(self, "취소", "작업이 취소되었습니다.")
                    return
                self._run_worker(_KafkaWorker.ACTION_PURGE_ALL, "")
                return

            topic = self._selected_topic()
            if not topic:
                QMessageBox.warning(self, "입력 오류", "유효한 토픽을 선택하거나 입력하세요.")
                return

            action = _KafkaWorker.ACTION_DELETE_TOPIC if (radio_del and radio_del.isChecked()) else _KafkaWorker.ACTION_PURGE
            action_label = "삭제" if action == _KafkaWorker.ACTION_DELETE_TOPIC else "Purge"

            ret = QMessageBox.warning(
                self, "⚠️ 작업 확인",
                f"토픽 '{topic}' 를 {action_label}하시겠습니까?\n\n삭제된 데이터는 복구할 수 없습니다!",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return
            self._run_worker(action, topic)

        def _selected_topic(self) -> str:
            combo = getattr(self, "comboTopic", None)
            if combo is None:
                return ""
            text = combo.currentText()
            if text == "직접 입력":
                edit = getattr(self, "editCustomTopic", None)
                return edit.text().strip() if edit else ""
            return text

        def _run_worker(self, action: str, topic: str) -> None:
            if self._worker and self._worker.isRunning():
                QMessageBox.information(self, "진행 중", "이미 작업이 진행 중입니다.")
                return
            self._set_busy(True)
            self._worker = _KafkaWorker(self._conn_params, action, topic)
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

        @pyqtSlot(str)
        def _on_error(self, msg: str) -> None:
            self._set_busy(False)
            lbl = getattr(self, "labelResult", None)
            if lbl is not None:
                lbl.setStyleSheet("color: #DC2626; font-weight: bold;")
                lbl.setText(f"🔴 오류: {msg[:180]}")
            logger.warning("[Kafka DeleteTab] 오류: %s", msg)

        def _set_busy(self, busy: bool) -> None:
            pb = getattr(self, "progressDelete", None)
            if pb is not None:
                pb.setVisible(busy)
            btn = getattr(self, "btnDelete", None)
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
            """인터페이스 통일용 no-op."""

        def stop_updates(self) -> None:
            if self._worker and self._worker.isRunning():
                self._worker.quit()
                self._worker.wait(2000)

        def closeEvent(self, event) -> None:
            self.stop_updates()
            super().closeEvent(event)

else:
    class DeleteTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 폴백 스텁."""
        def __init__(self, conn_params=None, parent=None): pass
        def start_updates(self, interval_ms: int = 0) -> None: pass
        def stop_updates(self) -> None: pass
