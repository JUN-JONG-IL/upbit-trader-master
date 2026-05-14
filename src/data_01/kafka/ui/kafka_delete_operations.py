# -*- coding: utf-8 -*-
"""
kafka_delete_operations.py — Kafka 데이터 삭제 로직 (SRP 분리)

KafkaDeleteMixin 클래스를 제공합니다.
KafkaSettingsDialog 에서 다중 상속으로 사용합니다.

지원 작업:
  - 특정 토픽 메시지 정리 (Retention=0으로 임시 설정 후 복원)
  - 특정 토픽 삭제
  - 전체 토픽 메시지 Purge
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import QMessageBox, QInputDialog, QLineEdit
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


class KafkaDeleteMixin:
    """Kafka 데이터 삭제 기능 믹스인.

    사용법:
        class KafkaSettingsDialog(QDialog, KafkaDeleteMixin):
            def __init__(self, ...):
                ...
                self._bind_kafka_delete_signals()
    """

    # ------------------------------------------------------------------
    # 시그널 바인딩
    # ------------------------------------------------------------------

    def _bind_kafka_delete_signals(self) -> None:
        """삭제 탭 버튼들을 슬롯에 연결합니다."""
        btn_map = {
            "btn_delete_candles_topic": self._on_delete_candles_topic,
            "btn_delete_ticker_topic": self._on_delete_ticker_topic,
            "btn_purge_all_topics": self._on_purge_all_topics,
            "btn_delete_specific_topic": self._on_delete_specific_topic,
        }
        for btn_name, slot in btn_map.items():
            btn = getattr(self, btn_name, None)
            if btn is not None:
                btn.clicked.connect(slot)

    # ------------------------------------------------------------------
    # 삭제 핸들러
    # ------------------------------------------------------------------

    def _on_delete_candles_topic(self) -> None:
        """candles 토픽 삭제"""
        if self._confirm_kafka_delete("upbit-candles 토픽"):
            threading.Thread(
                target=self._exec_delete_topic,
                args=("upbit-candles",),
                daemon=True,
            ).start()

    def _on_delete_ticker_topic(self) -> None:
        """ticker 토픽 삭제"""
        if self._confirm_kafka_delete("upbit-ticker 토픽"):
            threading.Thread(
                target=self._exec_delete_topic,
                args=("upbit-ticker",),
                daemon=True,
            ).start()

    def _on_purge_all_topics(self) -> None:
        """전체 토픽 메시지 Purge — 2단계 확인"""
        ret = QMessageBox.warning(
            self,
            "⚠️ 전체 토픽 Purge 경고",
            "모든 Kafka 토픽의 메시지를 삭제합니다!\n\n이 작업은 취소할 수 없습니다.\n정말로 계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        text, ok = QInputDialog.getText(
            self,
            "최종 확인",
            "모든 토픽 메시지가 삭제됩니다.\n확인하려면 'PURGE' 를 입력하세요:",
            QLineEdit.Normal,
            "",
        )
        if not ok or text.strip() != "PURGE":
            QMessageBox.information(self, "취소", "Purge가 취소되었습니다.")
            return
        threading.Thread(target=self._exec_purge_all_topics, daemon=True).start()

    def _on_delete_specific_topic(self) -> None:
        """입력된 토픽 삭제"""
        edit = getattr(self, "edit_delete_topic_name", None)
        topic = edit.text().strip() if edit is not None else ""
        if not topic:
            QMessageBox.warning(self, "입력 오류", "삭제할 토픽명을 입력하세요.")
            return
        if self._confirm_kafka_delete(f"{topic} 토픽"):
            threading.Thread(
                target=self._exec_delete_topic,
                args=(topic,),
                daemon=True,
            ).start()

    # ------------------------------------------------------------------
    # Kafka 실행 (백그라운드)
    # ------------------------------------------------------------------

    def _exec_delete_topic(self, topic_name: str) -> None:
        """토픽 삭제 실행"""
        try:
            admin = self._get_kafka_admin()
            if admin is None:
                return
            admin.delete_topics([topic_name], timeout_ms=10000)
            logger.info("[KafkaDeleteMixin] 토픽 삭제 완료: %s", topic_name)
            admin.close()
        except Exception as exc:
            logger.error("[KafkaDeleteMixin] 토픽 삭제 실패 (%s): %s", topic_name, exc)

    def _exec_purge_all_topics(self) -> None:
        """전체 토픽 메시지 Purge (Retention을 0으로 설정 후 복원)"""
        try:
            admin = self._get_kafka_admin()
            if admin is None:
                return
            metadata = admin.list_topics(timeout=10)
            topics = [t for t in metadata.topics if not t.startswith("__")]
            from confluent_kafka.admin import ConfigResource  # type: ignore[import]
            resource_type = ConfigResource.Type.TOPIC
            # 1) Retention=1ms 설정
            configs = {
                ConfigResource(resource_type, t): {"retention.ms": "1"}
                for t in topics
            }
            futures = admin.alter_configs(configs)
            for _, f in futures.items():
                f.result()
            import time
            time.sleep(2)
            # 2) 원래 Retention 복원
            restore = {
                ConfigResource(resource_type, t): {"retention.ms": "604800000"}
                for t in topics
            }
            futures = admin.alter_configs(restore)
            for _, f in futures.items():
                f.result()
            logger.info("[KafkaDeleteMixin] 전체 토픽 Purge 완료 (%d개)", len(topics))
            admin.close()
        except Exception as exc:
            logger.error("[KafkaDeleteMixin] 전체 Purge 실패: %s", exc)

    # ------------------------------------------------------------------
    # 유틸리티
    # ------------------------------------------------------------------

    def _confirm_kafka_delete(self, target: str) -> bool:
        """삭제 확인 팝업"""
        ret = QMessageBox.warning(
            self,
            "⚠️ 삭제 확인",
            f"[{target}] 을 삭제하시겠습니까?\n\n삭제된 데이터는 복구할 수 없습니다!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return ret == QMessageBox.Yes

    def _get_kafka_admin(self):
        """Kafka AdminClient 를 반환합니다. 실패 시 None."""
        try:
            from confluent_kafka.admin import AdminClient  # type: ignore[import]
            import os
            brokers = os.getenv("KAFKA_BROKERS", "localhost:9092")
            return AdminClient({"bootstrap.servers": brokers})
        except ImportError:
            logger.debug("[KafkaDeleteMixin] confluent-kafka 미설치")
            return None
        except Exception as exc:
            logger.debug("[KafkaDeleteMixin] Kafka 연결 실패: %s", exc)
            return None
