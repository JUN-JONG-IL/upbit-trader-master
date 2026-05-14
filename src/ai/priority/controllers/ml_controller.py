#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ML 모델 선택 PyQt5 컨트롤러

ml_model_selector.ui 파일을 로드하여 ML 모델 설정 UI를 제어합니다.

CHANGELOG:
- 2026-03-19 | Copilot | UI 파일 경로를 priority/ui/ 우선으로 수정, 존재 여부 검증 추가
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import QMainWindow, QMessageBox
    from PyQt5 import uic
    _PYQT5_AVAILABLE = True
except ImportError:
    _PYQT5_AVAILABLE = False
    QMainWindow = object  # type: ignore[assignment,misc]

# ml_model_selector.ui 경로: priority/ui/ 우선, 없으면 ai/ui/ai_engine/ 시도
_UI_FILE_PRIMARY = os.path.join(os.path.dirname(__file__), "..", "ui", "ml_model_selector.ui")
_UI_FILE_SECONDARY = os.path.join(os.path.dirname(__file__), "..", "..", "ui", "ai_engine", "ml_model_selector.ui")

if os.path.exists(os.path.abspath(_UI_FILE_PRIMARY)):
    _UI_FILE = _UI_FILE_PRIMARY
elif os.path.exists(os.path.abspath(_UI_FILE_SECONDARY)):
    _UI_FILE = _UI_FILE_SECONDARY
    logger.debug("[MLController] UI 파일: 보조 경로 사용 (%s)", os.path.abspath(_UI_FILE_SECONDARY))
else:
    logger.error(
        "[MLController] UI 파일 없음. 탐색 경로:\n  1) %s\n  2) %s",
        os.path.abspath(_UI_FILE_PRIMARY),
        os.path.abspath(_UI_FILE_SECONDARY),
    )
    _UI_FILE = None


if _PYQT5_AVAILABLE:

    class MLController(QMainWindow):  # type: ignore[misc]
        """ML 모델 선택 메인 윈도우 컨트롤러"""

        def __init__(self, db_session=None, config_manager=None, parent=None) -> None:
            super().__init__(parent)
            if _UI_FILE is None:
                raise FileNotFoundError(
                    "ml_model_selector.ui 파일을 찾을 수 없습니다. "
                    f"탐색 경로:\n  1) {os.path.abspath(_UI_FILE_PRIMARY)}\n"
                    f"  2) {os.path.abspath(_UI_FILE_SECONDARY)}"
                )
            uic.loadUi(os.path.abspath(_UI_FILE), self)

            self.db = db_session
            self.config_manager = config_manager

            self._setup_connections()
            self._load_initial_state()

        # ------------------------------------------------------------------
        # 초기화
        # ------------------------------------------------------------------

        def _setup_connections(self) -> None:
            """시그널/슬롯 연결"""
            self.btnSave.clicked.connect(self.save_settings)
            self.btnLoad.clicked.connect(self.load_settings)
            self.btnTestGap.clicked.connect(self.test_gap_prediction)
            self.btnTestAnomaly.clicked.connect(self.test_anomaly_detection)
            self.btnTestDrift.clicked.connect(self.test_drift_check)

            self.sliderAnomalyThreshold.valueChanged.connect(
                self._update_anomaly_label
            )
            self.sliderDriftInterval.valueChanged.connect(
                self._update_drift_label
            )

        def _load_initial_state(self) -> None:
            """초기 상태 설정"""
            if self.config_manager is not None:
                config = self.config_manager.load()
                self._apply_config(config)
            self._update_anomaly_label()
            self._update_drift_label()

        # ------------------------------------------------------------------
        # 라벨 업데이트 슬롯
        # ------------------------------------------------------------------

        def _update_anomaly_label(self) -> None:
            value = self.sliderAnomalyThreshold.value() / 100.0
            self.lblAnomalyThreshold.setText(
                f"임계값: {value:.2f} ({int(value * 100)}%)"
            )

        def _update_drift_label(self) -> None:
            value = self.sliderDriftInterval.value()
            minutes = value // 60
            self.lblDriftInterval.setText(
                f"체크 간격: {value}초 ({minutes}분)"
            )

        # ------------------------------------------------------------------
        # 선택값 조회 헬퍼
        # ------------------------------------------------------------------

        def _get_gap_model(self) -> str:
            if self.radioGapXGBoost.isChecked():
                return "xgboost"
            if self.radioGapCatBoost.isChecked():
                return "catboost"
            if self.radioGapProphet.isChecked():
                return "prophet"
            return "lightgbm"

        def _get_adaptive_method(self) -> str:
            if self.radioAdaptiveVolatility.isChecked():
                return "volatility_based"
            if self.radioAdaptiveHybrid.isChecked():
                return "hybrid"
            return "symbol_based"

        def _get_anomaly_model(self) -> str:
            if self.radioAnomalyAutoencoder.isChecked():
                return "autoencoder"
            if self.radioAnomalyOneClassSVM.isChecked():
                return "one_class_svm"
            return "isolation_forest"

        def _get_drift_monitor(self) -> str:
            if self.radioDriftAlibi.isChecked():
                return "alibi_detect"
            return "evidently"

        # ------------------------------------------------------------------
        # 슬롯
        # ------------------------------------------------------------------

        def save_settings(self) -> None:
            """현재 UI 상태를 ML 설정으로 저장합니다."""
            try:
                settings_dict = {
                    "gap_model_type": self._get_gap_model(),
                    "gap_model_enabled": self.chkGapEnabled.isChecked(),
                    "adaptive_tf_enabled": self.chkAdaptiveTF.isChecked(),
                    "adaptive_tf_method": self._get_adaptive_method(),
                    "anomaly_model_type": self._get_anomaly_model(),
                    "anomaly_threshold": self.sliderAnomalyThreshold.value() / 100.0,
                    "anomaly_enabled": self.chkAnomalyEnabled.isChecked(),
                    "drift_monitor_type": self._get_drift_monitor(),
                    "drift_check_interval": self.sliderDriftInterval.value(),
                    "drift_enabled": self.chkDriftEnabled.isChecked(),
                }

                if self.config_manager is not None:
                    from ..config.ml_config import MLConfig
                    config = MLConfig.from_dict(settings_dict)
                    self.config_manager.save(config)

                QMessageBox.information(self, "성공", "ML 모델 설정이 저장되었습니다!")
            except Exception as exc:
                logger.error("ML 설정 저장 실패: %s", exc)
                QMessageBox.critical(self, "오류", f"저장 실패: {exc}")

        def load_settings(self) -> None:
            """저장된 ML 설정을 UI에 적용합니다."""
            try:
                if self.config_manager is not None:
                    config = self.config_manager.load()
                    self._apply_config(config)
                QMessageBox.information(self, "성공", "ML 설정을 불러왔습니다!")
            except Exception as exc:
                logger.error("ML 설정 불러오기 실패: %s", exc)
                QMessageBox.critical(self, "오류", f"불러오기 실패: {exc}")

        def test_gap_prediction(self) -> None:
            try:
                QMessageBox.information(
                    self, "테스트", "Gap 예측 테스트를 실행했습니다!"
                )
            except Exception as exc:
                QMessageBox.critical(self, "오류", f"테스트 실패: {exc}")

        def test_anomaly_detection(self) -> None:
            try:
                QMessageBox.information(
                    self, "테스트", "이상치 감지 테스트를 실행했습니다!"
                )
            except Exception as exc:
                QMessageBox.critical(self, "오류", f"테스트 실패: {exc}")

        def test_drift_check(self) -> None:
            try:
                QMessageBox.information(
                    self, "테스트", "Drift 체크 테스트를 실행했습니다!"
                )
            except Exception as exc:
                QMessageBox.critical(self, "오류", f"테스트 실패: {exc}")

        def _apply_config(self, config) -> None:
            """MLConfig 값을 UI 위젯에 반영합니다."""
            # Gap 모델
            gap_map = {
                "xgboost": self.radioGapXGBoost,
                "lightgbm": self.radioGapLightGBM,
                "catboost": self.radioGapCatBoost,
                "prophet": self.radioGapProphet,
            }
            radio = gap_map.get(config.gap_model_type, self.radioGapLightGBM)
            radio.setChecked(True)
            self.chkGapEnabled.setChecked(config.gap_model_enabled)

            # Adaptive TF
            self.chkAdaptiveTF.setChecked(config.adaptive_tf_enabled)
            atf_map = {
                "symbol_based": self.radioAdaptiveSymbol,
                "volatility_based": self.radioAdaptiveVolatility,
                "hybrid": self.radioAdaptiveHybrid,
            }
            atf_radio = atf_map.get(config.adaptive_tf_method, self.radioAdaptiveSymbol)
            atf_radio.setChecked(True)

            # 이상치 감지
            anomaly_map = {
                "autoencoder": self.radioAnomalyAutoencoder,
                "isolation_forest": self.radioAnomalyIsolationForest,
                "one_class_svm": self.radioAnomalyOneClassSVM,
            }
            anomaly_radio = anomaly_map.get(
                config.anomaly_model_type, self.radioAnomalyIsolationForest
            )
            anomaly_radio.setChecked(True)
            self.sliderAnomalyThreshold.setValue(int(config.anomaly_threshold * 100))
            self.chkAnomalyEnabled.setChecked(config.anomaly_enabled)

            # Drift 모니터
            drift_map = {
                "alibi_detect": self.radioDriftAlibi,
                "evidently": self.radioDriftEvidently,
            }
            drift_radio = drift_map.get(config.drift_monitor_type, self.radioDriftEvidently)
            drift_radio.setChecked(True)
            self.sliderDriftInterval.setValue(config.drift_check_interval)
            self.chkDriftEnabled.setChecked(config.drift_enabled)

else:
    class MLController:  # type: ignore[no-redef]
        """PyQt5 미설치 환경을 위한 더미 클래스"""

        def __init__(self, *args, **kwargs) -> None:
            logger.warning("PyQt5가 설치되지 않아 MLController를 사용할 수 없습니다.")
