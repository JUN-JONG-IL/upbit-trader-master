#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""종목 메타데이터 탭 모듈"""

import math
import os
import logging
from datetime import datetime

try:
    from PyQt5.QtWidgets import (
        QWidget, QTableWidgetItem, QHeaderView, QMessageBox
    )
    from PyQt5.QtCore import Qt
    from PyQt5 import uic
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger(__name__)

_UI_PATH = os.path.join(os.path.dirname(__file__), "metadata_tab.ui")

# 우선순위 설정 테스트용 샘플 데이터
_TEST_SYMBOLS = [
    {"symbol": "KRW-BTC", "volume": 50_000_000_000, "is_favorite": True},
    {"symbol": "KRW-ETH", "volume": 20_000_000_000, "is_favorite": False},
    {"symbol": "KRW-XRP", "volume": 5_000_000_000, "is_favorite": True},
]


class MetadataTab(QWidget if _HAS_QT else object):
    """종목 메타데이터 탭.

    MongoDB에 저장된 종목(심볼) 메타데이터를 검색하고
    테이블로 표시합니다. 우선순위 설정 기능도 포함합니다.
    """

    def __init__(self, parent=None, mongo_client=None, conn_params=None):
        """초기화.

        Args:
            parent: 부모 위젯.
            mongo_client: MongoDB 클라이언트 인스턴스 (선택).
        """
        if not _HAS_QT:
            return
        super().__init__(parent)
        self._mongo_client = mongo_client
        self._conn_params = conn_params or {}
        self._setup_ui()

    def _setup_ui(self):
        """UI 파일 로드, 버튼 시그널 연결, 테이블 초기 설정."""
        uic.loadUi(_UI_PATH, self)

        # 메타데이터 검색 시그널
        self.btn_search.clicked.connect(self._search_metadata)
        self.edit_search.returnPressed.connect(self._search_metadata)
        header = self.table_metadata.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for col in range(2, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        # 우선순위 설정 시그널
        self.btnSavePriority.clicked.connect(self._save_priority)
        self.btnResetPriority.clicked.connect(self._reset_priority)
        self.btnTestPriority.clicked.connect(self._test_priority)
        self.sliderVolumeWeight.valueChanged.connect(self._update_formula_preview)

        # 수동 점수 테이블 초기 행 (BTC, ETH 기본값)
        self._init_manual_scores_table()
        # 공식 미리보기 초기화
        self._update_formula_preview(self.sliderVolumeWeight.value())

    def _init_manual_scores_table(self):
        """수동 점수 테이블 기본 데이터 설정."""
        default_rows = [
            ("KRW-BTC", "10", "주력"),
            ("KRW-ETH", "9", "주력"),
        ]
        self.tableManualScores.setRowCount(len(default_rows))
        for i, (symbol, score, reason) in enumerate(default_rows):
            self.tableManualScores.setItem(i, 0, QTableWidgetItem(symbol))
            self.tableManualScores.setItem(i, 1, QTableWidgetItem(score))
            self.tableManualScores.setItem(i, 2, QTableWidgetItem(reason))

    def set_mongo_client(self, client):
        """MongoDB 클라이언트를 교체합니다.

        Args:
            client: 새 MongoDB 클라이언트.
        """
        self._mongo_client = client

    # ── 메타데이터 검색 ──────────────────────────────────────────────────

    def _search_metadata(self):
        """검색어를 바탕으로 종목 메타데이터를 조회합니다.

        edit_search 위젯의 텍스트를 심볼 또는 이름 필드에서 검색하고
        결과를 table_metadata에 표시합니다.
        """
        keyword = self.edit_search.text().strip()
        if self._mongo_client is None:
            logger.warning("MongoDB 클라이언트가 설정되지 않았습니다.")
            return
        try:
            db = self._mongo_client.get_default_database()
            collection = db["symbol_metadata"]
            query = {}
            if keyword:
                query = {
                    "$or": [
                        {"symbol": {"$regex": keyword, "$options": "i"}},
                        {"name": {"$regex": keyword, "$options": "i"}},
                    ]
                }
            cursor = collection.find(query).limit(10_000)
            self.table_metadata.setRowCount(0)
            for doc in cursor:
                row = self.table_metadata.rowCount()
                self.table_metadata.insertRow(row)
                symbol = str(doc.get("symbol", ""))
                name = str(doc.get("name", ""))
                market = str(doc.get("market", ""))
                status = str(doc.get("status", ""))
                updated_at = str(doc.get("updated_at", ""))
                self.table_metadata.setItem(row, 0, QTableWidgetItem(symbol))
                self.table_metadata.setItem(row, 1, QTableWidgetItem(name))
                self.table_metadata.setItem(row, 2, QTableWidgetItem(market))
                self.table_metadata.setItem(row, 3, QTableWidgetItem(status))
                self.table_metadata.setItem(row, 4, QTableWidgetItem(updated_at))
        except Exception as exc:
            logger.warning("메타데이터 검색 실패: %s", exc)

    # ── 우선순위 설정 ────────────────────────────────────────────────────

    def _get_priority_config(self) -> dict:
        """현재 UI 상태에서 우선순위 설정 딕셔너리를 생성합니다."""
        return {
            "volume_weight": (
                self.sliderVolumeWeight.value()
                if self.chkVolumeWeight.isChecked()
                else 0
            ),
            "favorite_bonus": 2 if self.chkFavoritePriority.isChecked() else 0,
            "manual_scores": self._get_manual_scores(),
            "condition_type": "AND" if self.radioAnd.isChecked() else "OR",
            "custom_condition": self.txtCustomCondition.text().strip(),
        }

    def _get_manual_scores(self) -> dict:
        """수동 점수 테이블에서 {심볼: 점수} 딕셔너리를 반환합니다."""
        scores = {}
        for row in range(self.tableManualScores.rowCount()):
            symbol_item = self.tableManualScores.item(row, 0)
            score_item = self.tableManualScores.item(row, 1)
            if symbol_item and score_item:
                try:
                    scores[symbol_item.text().strip()] = float(
                        score_item.text().strip()
                    )
                except ValueError:
                    pass
        return scores

    def _get_manual_score(self, symbol: str) -> float:
        """특정 심볼의 수동 점수를 반환합니다 (없으면 0)."""
        if not self.chkManualScore.isChecked():
            return 0.0
        return self._get_manual_scores().get(symbol, 0.0)

    def _save_priority(self):
        """우선순위 설정을 MongoDB priority_settings 컬렉션에 저장합니다."""
        config = self._get_priority_config()
        if self._mongo_client is None:
            QMessageBox.warning(
                self, "저장 실패", "MongoDB 클라이언트가 연결되지 않았습니다."
            )
            return
        try:
            db = self._mongo_client.get_default_database()
            collection = db["priority_settings"]
            config["updated_at"] = datetime.now().isoformat()
            collection.replace_one({}, config, upsert=True)
            QMessageBox.information(
                self, "저장 완료", "우선순위 설정이 저장되었습니다."
            )
        except Exception as exc:
            logger.error("우선순위 설정 저장 실패: %s", exc)
            QMessageBox.critical(
                self, "저장 실패", f"저장 중 오류가 발생했습니다:\n{exc}"
            )

    def _reset_priority(self):
        """우선순위 설정을 기본값으로 초기화합니다."""
        self.chkVolumeWeight.setChecked(True)
        self.sliderVolumeWeight.setValue(5)
        self.chkFavoritePriority.setChecked(False)
        self.chkManualScore.setChecked(False)
        self.radioAnd.setChecked(True)
        self.txtCustomCondition.clear()
        self._init_manual_scores_table()
        self._update_formula_preview(5)

    def _test_priority(self):
        """샘플 데이터로 우선순위 점수 계산을 시뮬레이션합니다."""
        results = []
        for data in _TEST_SYMBOLS:
            score = self._calculate_score(data)
            results.append(f"{data['symbol']}: {score:.2f}점")
        QMessageBox.information(self, "테스트 결과", "\n".join(results))

    def _calculate_score(self, data: dict) -> float:
        """우선순위 점수를 계산합니다.

        공식: score = log10(volume) × weight + favorite_bonus + manual_score
        (AND 조건: 합산, OR 조건: 최댓값)

        Args:
            data: 'symbol', 'volume', 'is_favorite' 키를 가진 딕셔너리.

        Returns:
            계산된 우선순위 점수 (float).
        """
        # 거래량 가중치 점수
        volume_score = 0.0
        if self.chkVolumeWeight.isChecked():
            weight = self.sliderVolumeWeight.value()
            volume_score = math.log10(data.get("volume", 1)) * weight

        # 즐겨찾기 보너스
        favorite_bonus = 0.0
        if self.chkFavoritePriority.isChecked() and data.get("is_favorite"):
            favorite_bonus = 2.0

        # 수동 점수
        manual_score = self._get_manual_score(data.get("symbol", ""))

        # AND/OR 조건에 따라 최종 점수 결정
        if self.radioAnd.isChecked():
            # AND: 모든 점수 합산
            total = volume_score + favorite_bonus + manual_score
        else:
            # OR: 가장 높은 점수 선택
            total = max(volume_score, favorite_bonus, manual_score)

        return total

    def _update_formula_preview(self, weight: int):
        """슬라이더 값 변경 시 점수 계산식 미리보기를 갱신합니다.

        Args:
            weight: 거래량 가중치 (1~10).
        """
        self.lblVolumeWeightValue.setText(f"거래량 가중치: {weight}")
        formula = (
            f"💡 점수 계산식: score = log10(volume) × {weight}"
            f" + favorite_bonus + manual_score"
        )
        self.lblFormulaPreview.setText(formula)

    def closeEvent(self, event):
        """위젯 닫힘 이벤트 처리."""
        super().closeEvent(event)
