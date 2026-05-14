#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML/AI 모델 선택 다이얼로그 위젯 (v2.0)

UI 파일: ml_model_selector.ui

기능:
- Gap 예측 모델 선택 (XGBoost / LightGBM / CatBoost / Prophet)
- 적응형 타임프레임 모델 선택
- 이상 탐지 모델 선택
- 설정 저장/불러오기 (MongoDB ml_model_settings 컬렉션)

변경 이력:
- v2.0: 체크박스 해제 시 하위 라디오버튼 비활성화 기능 추가
- v2.0: MongoDB 연결 실패 시에도 UI 동작하도록 개선
- v2.0: 슬라이더 값 변경 시 라벨 업데이트 기능 추가
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PyQt5 임포트 (선택적)
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
    logger.warning("[MLModelSelectorDialog] PyQt5 미설치 — 더미 클래스를 사용합니다.")

# ---------------------------------------------------------------------------
# pymongo 임포트 (선택적)
# ---------------------------------------------------------------------------
try:
    from pymongo import MongoClient
    _PYMONGO_AVAILABLE = True
except ImportError:
    _PYMONGO_AVAILABLE = False
    logger.warning("[MLModelSelectorDialog] pymongo 미설치 — DB 저장 기능이 비활성화됩니다.")

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
_UI_DIR = os.path.dirname(os.path.abspath(__file__))
_UI_FILE = os.path.join(_UI_DIR, "ml_model_selector.ui")

_MONGO_URI = os.getenv("MONGODB_URI", "mongodb://admin:password@localhost:27017")
_DB_NAME = os.getenv("MONGODB_DB", "upbit_trader")

# 라디오버튼 그룹 → (enabled_checkbox, radio_list, db_key)
_MODEL_GROUPS: Dict[str, Dict[str, Any]] = {
    "gap": {
        "enabled": "chkGapEnabled",
        "radios": {
            "radioGapXGBoost": "xgboost",
            "radioGapLightGBM": "lightgbm",
            "radioGapCatBoost": "catboost",
            "radioGapProphet": "prophet",
        },
        "db_key": "gap_model",
        "test_btn": "btnTestGap",
    },
    "adaptive_tf": {
        "enabled": "chkAdaptiveTF",
        "radios": {
            "radioAdaptiveSymbol": "symbol_based",
            "radioAdaptiveVolatility": "volatility_based",
            "radioAdaptiveHybrid": "hybrid",
        },
        "db_key": "adaptive_tf_model",
        "test_btn": None,
    },
    "anomaly": {
        "enabled": "chkAnomalyEnabled",
        "radios": {
            "radioAnomalyAutoencoder": "autoencoder",
            "radioAnomalyIsolationForest": "isolation_forest",
            "radioAnomalyOneClassSVM": "one_class_svm",
        },
        "db_key": "anomaly_model",
        "test_btn": "btnTestAnomaly",
    },
    "drift": {
        "enabled": "chkDriftEnabled",
        "radios": {
            "radioDriftAlibi": "alibi_detect",
            "radioDriftEvidently": "evidently_ai",
        },
        "db_key": "drift_model",
        "test_btn": "btnTestDrift",
    },
}


if _PYQT5_AVAILABLE:
    class MLModelSelectorDialog(QMainWindow):
        """AI/ML 모델 선택 다이얼로그

        ml_model_selector.ui 를 로드하여 각 태스크별 모델을 선택하고
        MongoDB ml_model_settings 컬렉션에 저장합니다.
        
        v2.0: 체크박스 해제 시 하위 라디오버튼 비활성화
        """

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)

            if os.path.exists(_UI_FILE):
                uic.loadUi(_UI_FILE, self)
            else:
                logger.warning("[MLModelSelectorDialog] UI 파일 없음: %s", _UI_FILE)
                self.resize(720, 780)
                self.setWindowTitle("AI/ML 모델 선택")

            self._init_ui()
            self._connect_signals()
            self._update_radio_states()  # 초기 상태 설정

        # ------------------------------------------------------------------
        # 초기화
        # ------------------------------------------------------------------

        def _init_ui(self) -> None:
            """DB 에서 기존 설정을 불러와 UI 에 반영합니다."""
            settings = self._load_from_db()
            
            if settings:
                for group_key, cfg in _MODEL_GROUPS.items():
                    # enabled 체크박스
                    if cfg["enabled"]:
                        chk = getattr(self, cfg["enabled"], None)
                        if chk:
                            chk.setChecked(settings.get(f"{group_key}_enabled", True))

                    # 선택된 모델 라디오버튼
                    selected_model = settings.get(cfg["db_key"], "")
                    for radio_name, model_key in cfg["radios"].items():
                        radio = getattr(self, radio_name, None)
                        if radio and model_key == selected_model:
                            radio.setChecked(True)

                # 슬라이더 값 복원
                anomaly_threshold = settings.get("anomaly_threshold", 95)
                slider = getattr(self, "sliderAnomalyThreshold", None)
                if slider:
                    slider.setValue(anomaly_threshold)
                    self._update_anomaly_threshold_label(anomaly_threshold)

                drift_interval = settings.get("drift_interval", 3600)
                slider = getattr(self, "sliderDriftInterval", None)
                if slider:
                    slider.setValue(drift_interval)
                    self._update_drift_interval_label(drift_interval)

        def _connect_signals(self) -> None:
            """버튼/체크박스 시그널 연결"""
            # 저장 / 불러오기
            btn_save = getattr(self, "btnSave", None)
            btn_load = getattr(self, "btnLoad", None)
            if btn_save:
                btn_save.clicked.connect(self._save_settings)
            if btn_load:
                btn_load.clicked.connect(self._load_settings)

            # 각 그룹의 체크박스와 테스트 버튼 연결
            for group_key, cfg in _MODEL_GROUPS.items():
                # 체크박스 상태 변경 시 라디오버튼 활성화/비활성화
                if cfg["enabled"]:
                    chk = getattr(self, cfg["enabled"], None)
                    if chk:
                        chk.stateChanged.connect(self._update_radio_states)

                # 테스트 버튼
                if cfg["test_btn"]:
                    btn = getattr(self, cfg["test_btn"], None)
                    if btn:
                        btn.clicked.connect(
                            lambda _checked=False, gk=group_key: self._test_model(gk)
                        )

            # 슬라이더 연결
            slider = getattr(self, "sliderAnomalyThreshold", None)
            if slider:
                slider.valueChanged.connect(self._update_anomaly_threshold_label)

            slider = getattr(self, "sliderDriftInterval", None)
            if slider:
                slider.valueChanged.connect(self._update_drift_interval_label)

        # ------------------------------------------------------------------
        # 체크박스 상태에 따른 라디오버튼 활성화/비활성화
        # ------------------------------------------------------------------

        def _update_radio_states(self) -> None:
            """체크박스 상태에 따라 하위 라디오버튼을 활성화/비활성화합니다."""
            for group_key, cfg in _MODEL_GROUPS.items():
                if cfg["enabled"]:
                    chk = getattr(self, cfg["enabled"], None)
                    if chk is None:
                        continue
                    
                    enabled = chk.isChecked()
                    
                    # 라디오버튼 활성화/비활성화
                    for radio_name in cfg["radios"].keys():
                        radio = getattr(self, radio_name, None)
                        if radio:
                            radio.setEnabled(enabled)
                    
                    # 테스트 버튼 활성화/비활성화
                    if cfg["test_btn"]:
                        btn = getattr(self, cfg["test_btn"], None)
                        if btn:
                            btn.setEnabled(enabled)

        # ------------------------------------------------------------------
        # 슬라이더 라벨 업데이트
        # ------------------------------------------------------------------

        def _update_anomaly_threshold_label(self, value: int) -> None:
            """이상치 감지 임계값 슬라이더 라벨 업데이트"""
            lbl = getattr(self, "lblAnomalyThreshold", None)
            if lbl:
                lbl.setText(f"임계값: {value/100:.2f} ({value}%)")

        def _update_drift_interval_label(self, value: int) -> None:
            """Drift 체크 간격 슬라이더 라벨 업데이트"""
            lbl = getattr(self, "lblDriftInterval", None)
            if lbl:
                minutes = value // 60
                hours = minutes // 60
                if hours > 0:
                    lbl.setText(f"체크 간격: {value}초 ({hours}시간 {minutes % 60}분)")
                else:
                    lbl.setText(f"체크 간격: {value}초 ({minutes}분)")

        # ------------------------------------------------------------------
        # 설정 읽기
        # ------------------------------------------------------------------

        def _get_selected_model(self, group_key: str) -> str:
            """지정된 그룹에서 선택된 라디오버튼의 모델 키를 반환합니다."""
            cfg = _MODEL_GROUPS.get(group_key, {})
            for radio_name, model_key in cfg.get("radios", {}).items():
                radio = getattr(self, radio_name, None)
                if radio and radio.isChecked():
                    return model_key
            return ""

        def _build_settings_dict(self) -> Dict[str, Any]:
            """현재 UI 상태에서 설정 딕셔너리를 생성합니다."""
            doc: Dict[str, Any] = {
                "user_id": "default",
                "updated_at": datetime.now(tz=timezone.utc),
            }
            
            for group_key, cfg in _MODEL_GROUPS.items():
                if cfg["enabled"]:
                    chk = getattr(self, cfg["enabled"], None)
                    doc[f"{group_key}_enabled"] = bool(
                        chk.isChecked() if chk else True
                    )
                doc[cfg["db_key"]] = self._get_selected_model(group_key)

            # 슬라이더 값 저장
            slider = getattr(self, "sliderAnomalyThreshold", None)
            if slider:
                doc["anomaly_threshold"] = slider.value()

            slider = getattr(self, "sliderDriftInterval", None)
            if slider:
                doc["drift_interval"] = slider.value()

            return doc

        # ------------------------------------------------------------------
        # DB 연동
        # ------------------------------------------------------------------

        def _load_from_db(self) -> Optional[Dict[str, Any]]:
            if not _PYMONGO_AVAILABLE:
                logger.warning("[MLModelSelectorDialog] pymongo 미설치 - DB 로드 불가")
                return None
            try:
                client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=2000)
                result = client[_DB_NAME].ml_model_settings.find_one({"user_id": "default"})
                logger.info("[MLModelSelectorDialog] DB 조회 성공")
                return result
            except Exception as exc:
                logger.warning("[MLModelSelectorDialog] DB 조회 실패: %s", exc)
                return None

        def _save_settings(self) -> None:
            doc = self._build_settings_dict()
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
                client[_DB_NAME].ml_model_settings.update_one(
                    {"user_id": "default"}, {"$set": doc}, upsert=True
                )
                QMessageBox.information(self, "저장 완료", "모델 설정이 저장되었습니다.")
                logger.info("[MLModelSelectorDialog] 설정 저장 완료: %s", doc)
            except Exception as exc:
                logger.error("[MLModelSelectorDialog] 저장 실패: %s", exc)
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
            self._init_ui()
            self._update_radio_states()
            QMessageBox.information(self, "불러오기 완료", "설정을 다시 불러왔습니다.")

        def _test_model(self, group_key: str) -> None:
            """선택된 모델 연결 테스트 (플레이스홀더)"""
            cfg = _MODEL_GROUPS.get(group_key, {})
            
            # 체크박스 확인
            if cfg.get("enabled"):
                chk = getattr(self, cfg["enabled"], None)
                if chk and not chk.isChecked():
                    QMessageBox.warning(
                        self,
                        "테스트 불가",
                        f"{group_key} 모델이 비활성화되어 있습니다.\n\n"
                        f"먼저 활성화 체크박스를 선택해주세요."
                    )
                    return
            
            model = self._get_selected_model(group_key)
            if not model:
                QMessageBox.warning(
                    self,
                    "모델 미선택",
                    "테스트할 모델을 선택해주세요."
                )
                return
            
            QMessageBox.information(
                self,
                "모델 테스트",
                f"[{group_key}] {model} 모델 테스트를 시작합니다.\n\n"
                f"(향후 실제 모델 테스트 로직이 추가됩니다)"
            )

else:
    class MLModelSelectorDialog:  # type: ignore[no-redef]
        """PyQt5 미설치 환경용 더미 다이얼로그"""

        def __init__(self, parent: Any = None) -> None:
            logger.warning("[MLModelSelectorDialog] PyQt5 없음 — 더미 모드")

        def show(self) -> None:
            pass


__all__ = ["MLModelSelectorDialog"]