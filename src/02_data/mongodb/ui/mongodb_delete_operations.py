# -*- coding: utf-8 -*-
"""
mongodb_delete_operations.py — MongoDB 데이터 삭제 로직 (SRP 분리)

MongoDeleteMixin 클래스를 제공합니다.
MongoDBSettingsDialog 에서 다중 상속으로 사용합니다.

모든 삭제 작업은:
  1. QMessageBox.warning 확인 팝업 필수
  2. 백그라운드 스레드에서 실행 (UI 블록 방지)
  3. 전체 컬렉션 삭제는 2단계 확인
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


class MongoDeleteMixin:
    """MongoDB 데이터 삭제 기능 믹스인.

    사용법:
        class MongoDBSettingsDialog(QDialog, MongoDeleteMixin):
            def __init__(self, ...):
                ...
                self._bind_mongo_delete_signals()
    """

    # ------------------------------------------------------------------
    # 시그널 바인딩
    # ------------------------------------------------------------------

    def _bind_mongo_delete_signals(self) -> None:
        """삭제 탭 버튼들을 슬롯에 연결합니다."""
        btn_map = {
            "btn_drop_metadata": self._on_drop_metadata,
            "btn_drop_strategies": self._on_drop_strategies,
            "btn_drop_ml_models": self._on_drop_ml_models,
            "btn_drop_ui_settings": self._on_drop_ui_settings,
            "btn_clear_all_collections": self._on_clear_all_collections,
        }
        for btn_name, slot in btn_map.items():
            btn = getattr(self, btn_name, None)
            if btn is not None:
                btn.clicked.connect(slot)

    # ------------------------------------------------------------------
    # 삭제 핸들러
    # ------------------------------------------------------------------

    def _on_drop_metadata(self) -> None:
        """metadata 컬렉션 삭제"""
        if self._confirm_mongo_delete("metadata 컬렉션"):
            threading.Thread(
                target=self._exec_drop_collection,
                args=("metadata",),
                daemon=True,
            ).start()

    def _on_drop_strategies(self) -> None:
        """strategies 컬렉션 삭제"""
        if self._confirm_mongo_delete("strategies 컬렉션"):
            threading.Thread(
                target=self._exec_drop_collection,
                args=("strategies",),
                daemon=True,
            ).start()

    def _on_drop_ml_models(self) -> None:
        """ml_models 컬렉션 삭제"""
        if self._confirm_mongo_delete("ml_models 컬렉션"):
            threading.Thread(
                target=self._exec_drop_collection,
                args=("ml_models",),
                daemon=True,
            ).start()

    def _on_drop_ui_settings(self) -> None:
        """ui_settings 컬렉션 삭제 (초기화)"""
        if self._confirm_mongo_delete("ui_settings 컬렉션 (앱 재시작 시 기본값으로 초기화됨)"):
            threading.Thread(
                target=self._exec_drop_collection,
                args=("ui_settings",),
                daemon=True,
            ).start()

    def _on_clear_all_collections(self) -> None:
        """전체 컬렉션 삭제 — 2단계 확인"""
        # 1단계 확인
        ret = QMessageBox.warning(
            self,
            "⚠️ 전체 컬렉션 삭제 경고",
            "MongoDB upbit_trader DB의 모든 컬렉션을 삭제합니다!\n\n이 작업은 취소할 수 없습니다.\n정말로 계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        # 2단계: 텍스트 입력 확인
        text, ok = QInputDialog.getText(
            self,
            "최종 확인",
            "모든 컬렉션이 삭제됩니다.\n확인하려면 'DELETE ALL' 을 입력하세요:",
            QLineEdit.Normal,
            "",
        )
        if not ok or text.strip() != "DELETE ALL":
            QMessageBox.information(self, "취소", "삭제가 취소되었습니다.")
            return
        threading.Thread(target=self._exec_clear_all_collections, daemon=True).start()

    # ------------------------------------------------------------------
    # MongoDB 실행 (백그라운드)
    # ------------------------------------------------------------------

    def _exec_drop_collection(self, collection_name: str) -> None:
        """컬렉션 삭제 실행"""
        try:
            db = self._get_mongo_db()
            if db is None:
                return
            db.drop_collection(collection_name)
            logger.info("[MongoDeleteMixin] 컬렉션 삭제 완료: %s", collection_name)
        except Exception as exc:
            logger.error("[MongoDeleteMixin] 컬렉션 삭제 실패 (%s): %s", collection_name, exc)

    def _exec_clear_all_collections(self) -> None:
        """전체 컬렉션 삭제 실행"""
        try:
            db = self._get_mongo_db()
            if db is None:
                return
            names = db.list_collection_names()
            for name in names:
                db.drop_collection(name)
                logger.info("[MongoDeleteMixin] 컬렉션 삭제: %s", name)
            logger.info("[MongoDeleteMixin] 전체 컬렉션 삭제 완료 (%d개)", len(names))
        except Exception as exc:
            logger.error("[MongoDeleteMixin] 전체 컬렉션 삭제 실패: %s", exc)

    # ------------------------------------------------------------------
    # 유틸리티
    # ------------------------------------------------------------------

    def _confirm_mongo_delete(self, target: str) -> bool:
        """삭제 확인 팝업"""
        ret = QMessageBox.warning(
            self,
            "⚠️ 삭제 확인",
            f"[{target}] 을 삭제하시겠습니까?\n\n삭제된 데이터는 복구할 수 없습니다!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return ret == QMessageBox.Yes

    def _get_mongo_db(self):
        """MongoDB DB 객체를 반환합니다. 실패 시 None."""
        try:
            import pymongo  # type: ignore[import]
            import os
            from urllib.parse import quote_plus
            host = os.getenv("MONGO_HOST", "localhost")
            port = os.getenv("MONGO_PORT", "27017")
            user = (
                os.getenv("MONGO_USER")
                or os.getenv("MONGO_ID")
                or os.getenv("MONGO_INITDB_ROOT_USERNAME")
                or ""
            )
            password = (
                os.getenv("MONGO_PASSWORD")
                or os.getenv("MONGO_PW")
                or os.getenv("MONGO_INITDB_ROOT_PASSWORD")
                or ""
            )
            db_name = os.getenv("MONGO_DB", "upbit_trader")
            if user and password:
                uri = f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db_name}?authSource=admin"
            else:
                uri = f"mongodb://{host}:{port}/{db_name}"
            client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
            return client[db_name]
        except Exception as exc:
            logger.debug("[MongoDeleteMixin] MongoDB 연결 실패: %s", exc)
            return None
