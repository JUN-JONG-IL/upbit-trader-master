#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
우선순위 설정 다이얼로그 위젯 (v2.0)

UI 파일: priority_settings.ui

기능:
- 거래량/시가총액/인기/신규상장/변동성/가격변동/패턴/소셜 체크박스
- OR / AND 로직 선택
- 설정 저장/불러오기 (MongoDB priority_settings 컬렉션)
- 우선순위 점��� 계산 트리거
- 체크박스 체크 시 자동으로 우선순위 리스트에 추가/제거

변경 이력:
- v2.0: 체크박스 상태 변경 시 우선순위 리스트 자동 업데이트 기능 추가
- v2.0: MongoDB 연결 실패 시에도 UI 동작하도록 개선
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PyQt5 임포트 (선택적 — 헤드리스 환경 호환)
# ---------------------------------------------------------------------------
try:
    from PyQt5 import uic
    from PyQt5.QtWidgets import (
        QMainWindow,
        QMessageBox,
        QWidget,
    )
    _PYQT5_AVAILABLE = True
except ImportError:
    _PYQT5_AVAILABLE = False
    logger.warning("[PrioritySettingsDialog] PyQt5 미설치 — 더미 클래스를 사용합니다.")

# ---------------------------------------------------------------------------
# pymongo 임포트 (선택적)
# ---------------------------------------------------------------------------
try:
    from pymongo import MongoClient
    _PYMONGO_AVAILABLE = True
except ImportError:
    _PYMONGO_AVAILABLE = False
    logger.warning("[PrioritySettingsDialog] pymongo 미설치 — DB 저장 기능이 비활성화됩니다.")

# ---------------------------------------------------------------------------
# UI 파일 경로
# ---------------------------------------------------------------------------
_UI_DIR = os.path.dirname(os.path.abspath(__file__))
_UI_FILE = os.path.join(_UI_DIR, "priority_settings.ui")

_MONGO_URI = os.getenv("MONGODB_URI", "mongodb://admin:password@localhost:27017")
_DB_NAME = os.getenv("MONGODB_DB", "upbit_trader")

# 체크박스 이름 → DB 키 및 표시 이름 매핑
_CHECKBOX_MAP: Dict[str, Dict[str, str]] = {
    "chkVolume": {"key": "volume", "label": "거래량 (Volume)"},
    "chkMarketCap": {"key": "market_cap", "label": "시가총액 (Market Cap)"},
    "chkPopularity": {"key": "popularity", "label": "인기 (Popularity)"},
    "chkNewListings": {"key": "new_listings", "label": "신규 상장 (New Listings)"},
    "chkVolatility": {"key": "volatility", "label": "변동성 (Volatility)"},
    "chkPriceChange": {"key": "price_change", "label": "급등/급락 (Price Change %)"},
    "chkPattern": {"key": "pattern", "label": "패턴 감지 (Pattern Detection)"},
    "chkSocial": {"key": "social", "label": "소셜 멘션 (Social Mentions)"},
}


# ---------------------------------------------------------------------------
# 다이얼로그 클래스 (QMainWindow 기반)
# ---------------------------------------------------------------------------
if _PYQT5_AVAILABLE:
    class PrioritySettingsDialog(QMainWindow):
        """우선순위 종목 설정 다이얼로그

        priority_settings.ui 를 로드하여 체크박스/라디오버튼 기반으로
        우선수집 항목을 설정하고 MongoDB 에 저장합니다.
        
        v2.0: 체크박스 체크 시 자동으로 우선순위 리스트에 추가/제거
        """

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)

            # .ui 파일 로드
            if os.path.exists(_UI_FILE):
                uic.loadUi(_UI_FILE, self)
            else:
                logger.warning("[PrioritySettingsDialog] UI 파일 없음: %s", _UI_FILE)
                self.resize(700, 820)
                self.setWindowTitle("우선순위 설정 (Priority Settings)")

            self._init_ui()
            self._connect_signals()

        # ------------------------------------------------------------------
        # 초기화
        # ------------------------------------------------------------------

        def _init_ui(self) -> None:
            """MongoDB 에서 기존 설정을 로드하여 UI 에 반영합니다."""
            settings = self._load_from_db()
            
            if settings:
                items: Dict[str, bool] = settings.get("items", {})
                for widget_name, info in _CHECKBOX_MAP.items():
                    chk = getattr(self, widget_name, None)
                    if chk is not None:
                        chk.setChecked(items.get(info["key"], False))

                logic = settings.get("logic", "OR")
                radio_or = getattr(self, "radioOR", None)
                radio_and = getattr(self, "radioAND", None)
                if radio_or and radio_and:
                    if logic == "AND":
                        radio_and.setChecked(True)
                    else:
                        radio_or.setChecked(True)

                name_line = getattr(self, "txtSettingName", None)
                if name_line:
                    name_line.setText(settings.get("name", ""))

                # 기존 순서 복원
                priority_order = settings.get("priority_order", [])
                self._populate_priority_list(priority_order)
            else:
                # DB에서 로드 실패 시 기본값으로 리스트 초기화
                self._update_priority_list()

            self._update_summary()

        def _connect_signals(self) -> None:
            """버튼/체크박스 시그널 연결"""
            # 저장 / 불러오기 / 점수 계산
            for btn_name, handler in [
                ("btnSave", self._save_settings),
                ("btnLoad", self._load_settings),
                ("btnCalculate", self._calculate_scores),
                ("btnSelectAll", self._select_all),
                ("btnDeselectAll", self._deselect_all),
            ]:
                btn = getattr(self, btn_name, None)
                if btn is not None:
                    btn.clicked.connect(handler)

            # 체크박스 변경 시 요약 갱신 + 우선순위 리스트 업데이트
            for widget_name in _CHECKBOX_MAP:
                chk = getattr(self, widget_name, None)
                if chk is not None:
                    chk.stateChanged.connect(self._on_checkbox_changed)

            # 라디오버튼 변경 시 요약 갱신
            for radio_name in ("radioOR", "radioAND"):
                radio = getattr(self, radio_name, None)
                if radio is not None:
                    radio.toggled.connect(self._update_summary)

        # ------------------------------------------------------------------
        # 체크박스 상태 변경 핸들러
        # ------------------------------------------------------------------

        def _on_checkbox_changed(self) -> None:
            """체크박스 상태가 변경되면 우선순위 리스트를 업데이트합니다."""
            self._update_priority_list()
            self._update_summary()

        def _update_priority_list(self) -> None:
            """체크된 항목만 우선순위 리스트에 표시합니다."""
            list_widget = getattr(self, "listPriorities", None)
            if list_widget is None:
                return

            # 기존 순서 저장 (드래그앤드롭으로 변경된 순서 유지)
            existing_order = []
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if item:
                    existing_order.append(item.text())

            # 체크된 항목 목록 생성
            checked_items = []
            for widget_name, info in _CHECKBOX_MAP.items():
                chk = getattr(self, widget_name, None)
                if chk and chk.isChecked():
                    checked_items.append(info["label"])

            # 기존 순서 유지하면서 새로운 항목 추가
            new_order = [item for item in existing_order if item in checked_items]
            for item in checked_items:
                if item not in new_order:
                    new_order.append(item)

            # 리스트 위젯 업데이트
            self._populate_priority_list(new_order)

        def _populate_priority_list(self, items: List[str]) -> None:
            """우선순위 리스트를 주어진 항목으로 채웁니다."""
            list_widget = getattr(self, "listPriorities", None)
            if list_widget is None:
                return

            list_widget.clear()
            for item_label in items:
                list_widget.addItem(item_label)

        # ------------------------------------------------------------------
        # UI 헬퍼
        # ------------------------------------------------------------------

        def _update_summary(self) -> None:
            """활성 항목 수와 로직 모드를 요약 라벨에 표시합니다."""
            lbl = getattr(self, "lblSummary", None)
            if lbl is None:
                return
            active = sum(
                1
                for name in _CHECKBOX_MAP
                if getattr(getattr(self, name, None), "isChecked", lambda: False)()
            )
            radio_and = getattr(self, "radioAND", None)
            logic = "AND" if (radio_and and radio_and.isChecked()) else "OR"
            lbl.setText(f"활성 항목: {active}/{len(_CHECKBOX_MAP)} | 로직: {logic}")

        def _select_all(self) -> None:
            for name in _CHECKBOX_MAP:
                chk = getattr(self, name, None)
                if chk:
                    chk.setChecked(True)

        def _deselect_all(self) -> None:
            for name in _CHECKBOX_MAP:
                chk = getattr(self, name, None)
                if chk:
                    chk.setChecked(False)

        # ------------------------------------------------------------------
        # DB 연동
        # ------------------------------------------------------------------

        def _get_priority_order(self) -> List[str]:
            """현재 우선순위 리스트의 순서를 반환합니다."""
            list_widget = getattr(self, "listPriorities", None)
            if list_widget is None:
                return []
            
            order = []
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if item:
                    order.append(item.text())
            return order

        def _build_settings_dict(self) -> Dict[str, Any]:
            """현재 UI 상태에서 설정 딕셔너리를 생성합니다."""
            items = {
                info["key"]: bool(
                    getattr(getattr(self, widget_name, None), "isChecked", lambda: False)()
                )
                for widget_name, info in _CHECKBOX_MAP.items()
            }
            radio_and = getattr(self, "radioAND", None)
            logic = "AND" if (radio_and and radio_and.isChecked()) else "OR"
            name_line = getattr(self, "txtSettingName", None)
            name = name_line.text().strip() if name_line else ""
            
            return {
                "user_id": "default",
                "name": name,
                "items": items,
                "logic": logic,
                "priority_order": self._get_priority_order(),
                "updated_at": datetime.now(tz=timezone.utc),
            }

        def _load_from_db(self) -> Optional[Dict[str, Any]]:
            """MongoDB 에서 설정을 조회합니다."""
            if not _PYMONGO_AVAILABLE:
                logger.warning("[PrioritySettingsDialog] pymongo 미설치 - DB 로드 불가")
                return None
            try:
                client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=2000)
                db = client[_DB_NAME]
                result = db.priority_settings.find_one({"user_id": "default"})
                logger.info("[PrioritySettingsDialog] DB 조회 성공")
                return result
            except Exception as exc:
                logger.warning("[PrioritySettingsDialog] DB 조회 실패: %s", exc)
                return None

        def _save_settings(self) -> None:
            """현재 설정을 MongoDB 에 저장합니다."""
            settings = self._build_settings_dict()
            if not _PYMONGO_AVAILABLE:
                QMessageBox.warning(
                    self, 
                    "저장 실패", 
                    "pymongo 가 설치되지 않았습니다.\n\n"
                    "설치 방법: pip install pymongo"
                )
                return
            try:
                client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=2000)
                db = client[_DB_NAME]
                db.priority_settings.update_one(
                    {"user_id": "default"},
                    {"$set": settings},
                    upsert=True,
                )
                QMessageBox.information(self, "저장 완료", "우선순위 설정이 저장되었습니다.")
                logger.info("[PrioritySettingsDialog] 설정 저장 완료")
            except Exception as exc:
                logger.error("[PrioritySettingsDialog] 저장 실패: %s", exc)
                QMessageBox.critical(
                    self, 
                    "저장 실패", 
                    f"MongoDB 연결 실패\n\n"
                    f"오류: {exc}\n\n"
                    f"확인 사항:\n"
                    f"1. MongoDB 컨테이너 실행 여부 (docker ps)\n"
                    f"2. 연결 정보: {_MONGO_URI}\n"
                    f"3. 인증 정보 확인"
                )

        def _load_settings(self) -> None:
            """MongoDB 에서 설정을 다시 불러와 UI 에 반영합니다."""
            self._init_ui()
            QMessageBox.information(self, "불러오기 완료", "설정을 다시 불러왔습니다.")

        def _calculate_scores(self) -> None:
            """우선순위 점수 계산 요청 (PriorityService 연동)"""
            # 먼저 설정 저장
            settings = self._build_settings_dict()
            
            try:
                # PriorityService를 통한 점수 계산 (향후 구현)
                logger.info("[PrioritySettingsDialog] 점수 계산 요청: %s", settings)
                QMessageBox.information(
                    self, 
                    "계산 시작", 
                    f"우선순위 점수 계산을 시작합니다.\n\n"
                    f"활성 항목: {sum(settings['items'].values())}개\n"
                    f"로직: {settings['logic']}\n"
                    f"우선순위: {', '.join(settings['priority_order'])}"
                )
            except Exception as exc:
                logger.warning("[PrioritySettingsDialog] 점수 계산 실패: %s", exc)
                QMessageBox.warning(
                    self,
                    "계산 실패",
                    f"점수 계산 중 오류가 발생했습니다.\n\n오류: {exc}"
                )

else:
    # Headless fallback
    class PrioritySettingsDialog:  # type: ignore[no-redef]
        """PyQt5 미설치 환경용 더미 다이얼로그"""

        def __init__(self, parent: Any = None) -> None:
            logger.warning("[PrioritySettingsDialog] PyQt5 없음 — 더미 모드")

        def show(self) -> None:
            pass


__all__ = ["PrioritySettingsDialog"]