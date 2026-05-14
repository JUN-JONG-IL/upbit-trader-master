# -*- coding: utf-8 -*-
"""Tab 3: 시스템 설정 (수집 설정 + 데이터 관리 통합)"""
from __future__ import annotations
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QAbstractItemView
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if _HAS_QT:
    class SettingsTab(QWidget):
        """Tab 3: 시스템 설정 — 수집 설정과 데이터 관리를 서브 탭으로 통합"""

        def __init__(self, parent=None):
            super().__init__(parent)

            # 서브 탭 위젯 구성
            self._sub_tab = QTabWidget(self)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._sub_tab)

            # 수집 설정 서브 탭
            self._collection_tab = self._load_collection_tab()
            if self._collection_tab is not None:
                self._sub_tab.addTab(self._collection_tab, "📡 수집 설정")
            else:
                _placeholder = QWidget(self)
                self._sub_tab.addTab(_placeholder, "📡 수집 설정")

            # 데이터 관리 서브 탭
            self._data_mgmt_tab = self._load_data_mgmt_tab()
            if self._data_mgmt_tab is not None:
                self._sub_tab.addTab(self._data_mgmt_tab, "🗂️ 데이터 관리")
            else:
                _placeholder2 = QWidget(self)
                self._sub_tab.addTab(_placeholder2, "🗂️ 데이터 관리")

            self._settings_ctrl = None

        # ------------------------------------------------------------------
        # 서브 탭 로드 헬퍼
        # ------------------------------------------------------------------

        def _load_collection_tab(self) -> Optional[QWidget]:
            """CollectionTab을 로드합니다."""
            try:
                from .collection_tab import CollectionTab
                return CollectionTab(parent=self)
            except Exception as exc:
                logger.warning("[SettingsTab] CollectionTab 로드 실패: %s", exc)
                return None

        def _load_data_mgmt_tab(self) -> Optional[QWidget]:
            """DataMgmtTab을 로드합니다."""
            try:
                from .data_mgmt_tab import DataMgmtTab
                return DataMgmtTab(parent=self)
            except Exception as exc:
                logger.warning("[SettingsTab] DataMgmtTab 로드 실패: %s", exc)
                return None

        # ------------------------------------------------------------------
        # CollectionTab 인터페이스 프록시 (status_widget.py 호환성)
        # ------------------------------------------------------------------

        def set_controller(self, ctrl) -> None:
            """CollectionSettings 컨트롤러를 CollectionTab에 주입합니다."""
            self._settings_ctrl = ctrl
            if self._collection_tab is not None and hasattr(self._collection_tab, "set_controller"):
                self._collection_tab.set_controller(ctrl)

        def get_selected_timeframes(self) -> list:
            """CollectionTab의 선택된 타임프레임 목록을 반환합니다."""
            if self._collection_tab is not None and hasattr(self._collection_tab, "get_selected_timeframes"):
                return self._collection_tab.get_selected_timeframes()
            return ["1m", "5m", "1h"]

        def get_lookback_days(self) -> int:
            """CollectionTab의 백필 기간(일수)을 반환합니다."""
            if self._collection_tab is not None and hasattr(self._collection_tab, "get_lookback_days"):
                return self._collection_tab.get_lookback_days()
            return 3

        def update_disk_usage(self, ts_gb: float, redis_mb: float, ch_gb: float) -> None:
            """CollectionTab의 디스크 용량 레이블을 갱신합니다."""
            if self._collection_tab is not None and hasattr(self._collection_tab, "update_disk_usage"):
                self._collection_tab.update_disk_usage(ts_gb, redis_mb, ch_gb)

        def start_updates(self, interval_ms: int = 3000) -> None:
            """서브 탭의 자동 갱신을 시작합니다."""
            for tab in (self._collection_tab, self._data_mgmt_tab):
                if tab is not None and hasattr(tab, "start_updates"):
                    tab.start_updates(interval_ms)

        def stop_updates(self) -> None:
            """서브 탭의 자동 갱신을 중지합니다."""
            for tab in (self._collection_tab, self._data_mgmt_tab):
                if tab is not None and hasattr(tab, "stop_updates"):
                    tab.stop_updates()

else:
    class SettingsTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""

        def __init__(self, parent=None):
            pass

        def set_controller(self, ctrl) -> None:
            pass

        def get_selected_timeframes(self) -> list:
            return ["1m", "5m", "1h"]

        def get_lookback_days(self) -> int:
            return 3

        def update_disk_usage(self, *args, **kwargs) -> None:
            pass

        def start_updates(self, interval_ms: int = 3000) -> None:
            pass

        def stop_updates(self) -> None:
            pass
