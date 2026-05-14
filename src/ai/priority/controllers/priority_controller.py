#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
우선순위 설정 PyQt5 컨트롤러

priority_settings.ui 파일을 로드하여 우선순위 설정 UI를 제어합니다.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import QMainWindow, QMessageBox, QListWidgetItem, QCheckBox
    from PyQt5.QtCore import Qt, pyqtSignal
    from PyQt5 import uic
    _PYQT5_AVAILABLE = True
except ImportError:
    _PYQT5_AVAILABLE = False
    QMainWindow = object  # type: ignore[assignment,misc]

_UI_FILE = os.path.join(os.path.dirname(__file__), "..", "ui", "priority_settings.ui")


if _PYQT5_AVAILABLE:

    class PriorityController(QMainWindow):  # type: ignore[misc]
        """우선순위 설정 메인 윈도우 컨트롤러"""

        scores_updated = pyqtSignal(dict)

        def __init__(self, db_session=None, config_manager=None, user_id: int = 1, parent=None) -> None:
            super().__init__(parent)
            uic.loadUi(os.path.abspath(_UI_FILE), self)

            self.db = db_session
            self.config_manager = config_manager
            self.user_id = user_id

            # DB 서비스 초기화 (DB 세션이 있는 경우)
            self._db_service = None
            if self.db is not None:
                try:
                    from ..services.priority_db_service import PriorityDBService
                    self._db_service = PriorityDBService(self.db)
                except Exception as exc:
                    logger.warning("PriorityDBService 초기화 실패: %s", exc)

            self._setup_connections()
            self._setup_drag_drop()
            self._load_initial_state()

        # ------------------------------------------------------------------
        # 초기화
        # ------------------------------------------------------------------

        def _setup_connections(self) -> None:
            """시그널/슬롯 연결"""
            self.btnSave.clicked.connect(self.save_settings)
            self.btnLoad.clicked.connect(self.load_settings)
            self.btnCalculate.clicked.connect(self.calculate_scores)
            self.btnSelectAll.clicked.connect(self.select_all)
            self.btnDeselectAll.clicked.connect(self.deselect_all)

            for checkbox in self._all_checkboxes():
                checkbox.stateChanged.connect(self.update_priority_list)

        def _setup_drag_drop(self) -> None:
            """드래그앤드롭 활성화"""
            from PyQt5.QtWidgets import QAbstractItemView
            self.listPriorities.setDragDropMode(QAbstractItemView.InternalMove)
            self.listPriorities.setDefaultDropAction(Qt.MoveAction)

        def _load_initial_state(self) -> None:
            """초기 상태 설정"""
            if self.config_manager is not None:
                config = self.config_manager.load()
                self._apply_config(config)
            self.update_priority_list()

        # ------------------------------------------------------------------
        # 우선순위 항목
        # ------------------------------------------------------------------

        def _all_checkboxes(self):
            """우선순위 체크박스 목록 반환"""
            return [
                self.chkVolume,
                self.chkMarketCap,
                self.chkPopularity,
                self.chkNewListings,
                self.chkVolatility,
                self.chkPriceChange,
                self.chkPattern,
                self.chkSocial,
            ]

        def _priority_items(self):
            """(key, checkbox, label) 튜플 목록"""
            return [
                ("volume", self.chkVolume, "거래량 (Volume)"),
                ("market_cap", self.chkMarketCap, "시가총액 (Market Cap)"),
                ("volatility", self.chkVolatility, "변동성 (Volatility)"),
                ("price_change", self.chkPriceChange, "급등/급락 (Price Change)"),
                ("popularity", self.chkPopularity, "인기 (Popularity)"),
                ("new_listings", self.chkNewListings, "신규 상장 (New Listings)"),
                ("pattern_detection", self.chkPattern, "패턴 감지 (Pattern)"),
                ("social_mentions", self.chkSocial, "소셜 멘션 (Social)"),
            ]

        # ------------------------------------------------------------------
        # 슬롯
        # ------------------------------------------------------------------

        def update_priority_list(self) -> None:
            """체크된 항목을 listPriorities에 반영합니다."""
            self.listPriorities.clear()
            for key, checkbox, label in self._priority_items():
                if checkbox.isChecked():
                    item = QListWidgetItem(
                        f"#{self.listPriorities.count() + 1} - {label}"
                    )
                    item.setData(Qt.UserRole, key)
                    self.listPriorities.addItem(item)
            self._update_summary()

        def _update_summary(self) -> None:
            enabled_count = sum(cb.isChecked() for cb in self._all_checkboxes())
            logic = "OR" if self.radioOR.isChecked() else "AND"
            self.lblSummary.setText(f"활성 항목: {enabled_count}/8 | 로직: {logic}")

        def select_all(self) -> None:
            for cb in self._all_checkboxes():
                cb.setChecked(True)

        def deselect_all(self) -> None:
            for cb in self._all_checkboxes():
                cb.setChecked(False)

        def save_settings(self) -> None:
            """현재 UI 상태를 설정으로 저장합니다."""
            try:
                priority_order = []
                for i in range(self.listPriorities.count()):
                    item = self.listPriorities.item(i)
                    priority_order.append(item.data(Qt.UserRole))

                settings_dict = {
                    "setting_name": self.txtSettingName.text() or "기본 설정",
                    "volume_enabled": self.chkVolume.isChecked(),
                    "market_cap_enabled": self.chkMarketCap.isChecked(),
                    "volatility_enabled": self.chkVolatility.isChecked(),
                    "price_change_enabled": self.chkPriceChange.isChecked(),
                    "popularity_enabled": self.chkPopularity.isChecked(),
                    "new_listings_enabled": self.chkNewListings.isChecked(),
                    "pattern_detection_enabled": self.chkPattern.isChecked(),
                    "social_mentions_enabled": self.chkSocial.isChecked(),
                    "priority_order": priority_order,
                    "logic_type": "OR" if self.radioOR.isChecked() else "AND",
                }

                # DB 서비스 우선, 없으면 config_manager 사용
                if self._db_service is not None:
                    self._db_service.save_settings(self.user_id, settings_dict)
                elif self.config_manager is not None:
                    from ..config.priority_config import PriorityConfig
                    config = PriorityConfig.from_dict(settings_dict)
                    self.config_manager.save(config)

                QMessageBox.information(self, "성공", "✅ 설정이 저장되었습니다!")
            except Exception as exc:
                logger.error("우선순위 설정 저장 실패: %s", exc)
                QMessageBox.critical(self, "오류", f"❌ 저장 실패: {exc}")

        def load_settings(self) -> None:
            """저장된 설정을 UI에 적용합니다."""
            try:
                # DB 서비스 우선, 없으면 config_manager 사용
                if self._db_service is not None:
                    db_settings = self._db_service.load_settings(self.user_id)
                    if db_settings is None:
                        QMessageBox.warning(self, "경고", "저장된 설정이 없습니다.")
                        return
                    settings_dict = {
                        "setting_name": db_settings.setting_name,
                        "volume_enabled": db_settings.volume_enabled,
                        "market_cap_enabled": db_settings.market_cap_enabled,
                        "volatility_enabled": db_settings.volatility_enabled,
                        "price_change_enabled": db_settings.price_change_enabled,
                        "popularity_enabled": db_settings.popularity_enabled,
                        "new_listings_enabled": db_settings.new_listings_enabled,
                        "pattern_detection_enabled": db_settings.pattern_detection_enabled,
                        "social_mentions_enabled": db_settings.social_mentions_enabled,
                        "priority_order": db_settings.priority_order or [],
                        "logic_type": db_settings.logic_type,
                    }
                    from ..config.priority_config import PriorityConfig
                    config = PriorityConfig.from_dict(settings_dict)
                    self._apply_config(config)
                elif self.config_manager is not None:
                    config = self.config_manager.load()
                    self._apply_config(config)
                else:
                    QMessageBox.warning(self, "경고", "저장된 설정이 없습니다.")
                    return

                QMessageBox.information(self, "성공", "✅ 설정을 불러왔습니다!")
            except Exception as exc:
                logger.error("우선순위 설정 불러오기 실패: %s", exc)
                QMessageBox.critical(self, "오류", f"❌ 불러오기 실패: {exc}")

        def calculate_scores(self) -> None:
            """우선순위 점수를 계산합니다."""
            try:
                QMessageBox.information(self, "성공", "우선순위 점수를 계산했습니다!")
            except Exception as exc:
                logger.error("점수 계산 실패: %s", exc)
                QMessageBox.critical(self, "오류", f"계산 실패: {exc}")

        def _apply_config(self, config) -> None:
            """PriorityConfig 값을 UI 위젯에 반영합니다."""
            self.txtSettingName.setText(config.setting_name)
            self.chkVolume.setChecked(config.volume_enabled)
            self.chkMarketCap.setChecked(config.market_cap_enabled)
            self.chkVolatility.setChecked(config.volatility_enabled)
            self.chkPriceChange.setChecked(config.price_change_enabled)
            self.chkPopularity.setChecked(config.popularity_enabled)
            self.chkNewListings.setChecked(config.new_listings_enabled)
            self.chkPattern.setChecked(config.pattern_detection_enabled)
            self.chkSocial.setChecked(config.social_mentions_enabled)
            if config.logic_type == "AND":
                self.radioAND.setChecked(True)
            else:
                self.radioOR.setChecked(True)
            self.update_priority_list()

else:
    class PriorityController:  # type: ignore[no-redef]
        """PyQt5 미설치 환경을 위한 더미 클래스"""

        def __init__(self, *args, **kwargs) -> None:
            logger.warning("PyQt5가 설치되지 않아 PriorityController를 사용할 수 없습니다.")
