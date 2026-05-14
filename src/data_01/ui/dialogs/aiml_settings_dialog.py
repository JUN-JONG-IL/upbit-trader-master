# -*- coding: utf-8 -*-
"""AI/ML 제어 상세 다이얼로그 (비모달)

ONNX Runtime 상태, Redis Feature Store 히트율,
ML 기반 Gap 예측, 성능 Baseline 재학습, AI 모드 설정을
비모달 팝업으로 표시합니다. 설정 변경 시 자동 저장됩니다.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer, Qt, pyqtSignal
    from PyQt5.QtWidgets import QDialog
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_UI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aiml_settings_dialog.ui")


if _HAS_QT:
    class AIMLSettingsDialog(QDialog):
        """AI/ML 제어 상세 다이얼로그 (비모달 팝업).

        기존 aiml_tab의 전체 UI를 별도 창으로 표시합니다.
        창을 닫아도 설정은 자동 저장(Debounce 500ms)되어 보존됩니다.
        """

        # 설정 변경 시 emit (요약 레이블 갱신용)
        settings_changed = pyqtSignal(dict)

        def __init__(self, parent=None):
            super().__init__(parent)

            # 비모달 설정 — 메인 창과 동시에 사용 가능
            self.setWindowModality(Qt.NonModal)

            # UI 파일 로드
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[AIMLSettingsDialog] UI 로드 실패: %s", exc)

            self._settings_manager = None

            # Debounce 타이머 (500ms 후 저장)
            self._save_timer = QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.setInterval(500)
            self._save_timer.timeout.connect(self._on_save_timer)

            self._connect_signals()

            # 닫기 버튼
            if hasattr(self, "btn_close"):
                self.btn_close.clicked.connect(self.close)

        # ------------------------------------------------------------------
        # 시그널 연결
        # ------------------------------------------------------------------

        def _connect_signals(self) -> None:
            """UI 시그널 연결"""
            try:
                self.btnViewGaps.clicked.connect(self._on_view_gaps)
                self.btnRetrain.clicked.connect(self._on_retrain)
                self.btnApply.clicked.connect(self._on_apply_mode)
            except AttributeError as exc:
                logger.debug("[AIMLSettingsDialog] 시그널 연결 일부 실패: %s", exc)

            # 설정 변경 시 자동 저장 연결
            for radio_name in ["radioOFF", "radioLIGHT", "radioMAX"]:
                radio = getattr(self, radio_name, None)
                if radio is not None:
                    radio.toggled.connect(self._on_settings_changed)

            cbGap = getattr(self, "cbGapEnabled", None)
            if cbGap is not None:
                cbGap.stateChanged.connect(self._on_settings_changed)

            cbBaseline = getattr(self, "cbBaselineLearning", None)
            if cbBaseline is not None:
                cbBaseline.stateChanged.connect(self._on_settings_changed)

        # ------------------------------------------------------------------
        # 슬롯
        # ------------------------------------------------------------------

        def _on_view_gaps(self) -> None:
            """Gap 예측 결과 보기"""
            logger.info("[AI/ML] Gap 예측 결과 조회")

        def _on_retrain(self) -> None:
            """모델 재학습"""
            logger.info("[AI/ML] 모델 재학습 시작")

        def _on_apply_mode(self) -> None:
            """AI 모드 적용"""
            mode = self._current_mode()
            logger.info("[AI/ML] AI 모드 변경: %s", mode)
            self._on_settings_changed()

        def _on_settings_changed(self) -> None:
            """설정 변경 시 500ms 대기 후 저장 (Debounce) + 시그널 emit"""
            self._save_timer.start(500)
            # 변경 즉시 시그널 emit (요약 레이블 실시간 갱신)
            self.settings_changed.emit(self.collect_current_settings())

        # ------------------------------------------------------------------
        # 설정 저장/복원
        # ------------------------------------------------------------------

        def set_settings_manager(self, manager) -> None:
            """UISettingsManager 주입"""
            self._settings_manager = manager

        def _on_save_timer(self) -> None:
            """Debounce 타이머 만료 시 저장 실행 (✅ 동기 버전, 인자 순서 수정)"""
            if self._settings_manager is None:
                return
            
            settings = self.collect_current_settings()

            try:
                # ✅ 수정: 인자 순서 변경 (settings, user_id)
                # SettingsManager.save_settings(settings: dict, user_id: str = "default")
                self._settings_manager.save_settings(settings, "default")
                logger.info("[AIMLSettingsDialog] ✅ 설정 자동 저장 완료")
            except Exception as exc:
                logger.error("[AIMLSettingsDialog] ❌ 설정 저장 실패: %s", exc, exc_info=True)

        def collect_current_settings(self) -> dict:
            """현재 AI/ML 설정 상태를 dict로 수집합니다."""
            gap_cb = getattr(self, "cbGapEnabled", None)
            gap_enabled = gap_cb.isChecked() if gap_cb is not None else False

            baseline_cb = getattr(self, "cbBaselineLearning", None)
            baseline_enabled = baseline_cb.isChecked() if baseline_cb is not None else False

            return {
                "ai_ml": {
                    "gap_prediction_enabled": gap_enabled,
                    "baseline_learning_enabled": baseline_enabled,
                    "ai_mode": self._current_mode(),
                }
            }

        def restore_settings(self, settings: dict) -> None:
            """MongoDB에서 로드한 AI/ML 설정을 UI에 복원합니다."""
            ai = settings.get("ai_ml", {})
            if not ai:
                return
            try:
                gap_cb = getattr(self, "cbGapEnabled", None)
                if gap_cb is not None:
                    gap_cb.setChecked(bool(ai.get("gap_prediction_enabled", False)))

                baseline_cb = getattr(self, "cbBaselineLearning", None)
                if baseline_cb is not None:
                    baseline_cb.setChecked(bool(ai.get("baseline_learning_enabled", False)))

                ai_mode = ai.get("ai_mode", "OFF")
                mode_map = {
                    "OFF": "radioOFF",
                    "LIGHT": "radioLIGHT",
                    "MAX": "radioMAX",
                }
                radio = getattr(self, mode_map.get(ai_mode, "radioOFF"), None)
                if radio is not None:
                    radio.setChecked(True)

                logger.info("[AIMLSettingsDialog] 설정 복원 완료")
            except Exception as exc:
                logger.debug("[AIMLSettingsDialog] 설정 복원 실패: %s", exc)

        # ------------------------------------------------------------------
        # 상태 갱신 (외부에서 호출)
        # ------------------------------------------------------------------

        def update_onnx_status(self, model: str, status: str, qps: str, latency: str) -> None:
            """ONNX Runtime 상태 레이블 갱신"""
            try:
                if hasattr(self, "labelModelValue"):
                    self.labelModelValue.setText(model)
                if hasattr(self, "labelStatusValue"):
                    self.labelStatusValue.setText(status)
                if hasattr(self, "labelQPSValue"):
                    self.labelQPSValue.setText(qps)
                if hasattr(self, "labelLatencyValue"):
                    self.labelLatencyValue.setText(latency)
            except Exception as exc:
                logger.debug("[AIMLSettingsDialog] ONNX 상태 갱신 실패: %s", exc)

        def update_redis_status(self, cache_keys: str, hit_rate: str) -> None:
            """Redis Feature Store 상태 레이블 갱신"""
            try:
                if hasattr(self, "labelCacheValue"):
                    self.labelCacheValue.setText(cache_keys)
                if hasattr(self, "labelHitRateValue"):
                    self.labelHitRateValue.setText(hit_rate)
            except Exception as exc:
                logger.debug("[AIMLSettingsDialog] Redis 상태 갱신 실패: %s", exc)

        # ------------------------------------------------------------------
        # 내부 유틸
        # ------------------------------------------------------------------

        def _current_mode(self) -> str:
            """현재 선택된 AI 모드 반환"""
            mode = "OFF"
            try:
                if self.radioLIGHT.isChecked():
                    mode = "LIGHT"
                elif self.radioMAX.isChecked():
                    mode = "MAX"
            except AttributeError:
                pass
            return mode

        # ------------------------------------------------------------------
        # 생명 주기
        # ------------------------------------------------------------------

        def closeEvent(self, event) -> None:
            """창 닫기 — 설정은 자동 저장됨"""
            logger.info("[AIMLSettingsDialog] 창 닫힘 — 설정은 자동 저장됨")
            event.accept()

else:
    class AIMLSettingsDialog:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""

        settings_changed = None

        def __init__(self, parent=None):
            pass

        def show(self) -> None:
            pass

        def isVisible(self) -> bool:
            return False

        def activateWindow(self) -> None:
            pass

        def set_settings_manager(self, manager) -> None:
            pass

        def collect_current_settings(self) -> dict:
            return {}

        def restore_settings(self, settings: dict) -> None:
            pass

        def update_onnx_status(self, *args, **kwargs) -> None:
            pass

        def update_redis_status(self, *args, **kwargs) -> None:
            pass

        def _current_mode(self) -> str:
            return "OFF"