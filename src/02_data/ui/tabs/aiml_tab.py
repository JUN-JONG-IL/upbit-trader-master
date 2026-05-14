# -*- coding: utf-8 -*-
"""Tab: AI/ML 제어 — 요약 뷰 + 비모달 상세 설정 팝업

ONNX Runtime 상태, Redis Feature Store, Gap 예측, 성능 Baseline, AI 모드 설정은
비모달 팝업(AIMLSettingsDialog)으로 분리되었습니다.
이 탭은 현재 AI/ML 상태의 요약만 표시합니다.
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QWidget
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_UI_PATH = os.path.join(os.path.dirname(__file__), "aiml_tab.ui")


if _HAS_QT:
    class AIMLTab(QWidget):
        """AI/ML 제어 탭 (요약 뷰).

        상세 설정은 AIMLSettingsDialog(비모달)에서 관리합니다.
        이 탭은 현재 ONNX/Redis/모드 상태 요약만 표시합니다.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[AIMLTab] UI 로드 실패: %s", exc)

            # 실시간 갱신 타이머 (3초)
            self._timer = QTimer(self)
            self._timer.setInterval(3000)
            self._timer.timeout.connect(self._update_status)

            self._settings_manager = None

            # 상세 설정 다이얼로그 인스턴스 (지연 생성)
            self._detail_dialog = None

            # "상세 설정 열기" 버튼 연결
            if hasattr(self, "btn_open_aiml_detail"):
                self.btn_open_aiml_detail.clicked.connect(self._open_detail_dialog)

        # ------------------------------------------------------------------
        # 다이얼로그 관련
        # ------------------------------------------------------------------

        def _get_or_create_dialog(self):
            """상세 설정 다이얼로그를 반환합니다 (없으면 생성)."""
            if self._detail_dialog is None:
                try:
                    from ..dialogs.aiml_settings_dialog import AIMLSettingsDialog
                    self._detail_dialog = AIMLSettingsDialog(self)
                    self._detail_dialog.settings_changed.connect(self._on_detail_settings_changed)
                except Exception as exc:
                    logger.error("[AIMLTab] 다이얼로그 생성 실패: %s", exc)
            return self._detail_dialog

        def _open_detail_dialog(self) -> None:
            """상세 설정 다이얼로그 열기 (비모달)."""
            dlg = self._get_or_create_dialog()
            if dlg is None:
                return
            if dlg.isVisible():
                dlg.activateWindow()
                return
            dlg.show()

        def _on_detail_settings_changed(self, settings: dict) -> None:
            """다이얼로그 설정 변경 시 요약 레이블 갱신."""
            ai = settings.get("ai_ml", {})
            try:
                mode = ai.get("ai_mode", "OFF")
                if hasattr(self, "label_summary_mode"):
                    self.label_summary_mode.setText(f"AI 모드: {mode}")

                gap_enabled = ai.get("gap_prediction_enabled", False)
                if hasattr(self, "label_summary_gap"):
                    gap_text = "활성화" if gap_enabled else "비활성화"
                    self.label_summary_gap.setText(f"Gap 예측: {gap_text}")
            except Exception as exc:
                logger.debug("[AIMLTab] 요약 레이블 갱신 실패: %s", exc)

        # ------------------------------------------------------------------
        # 상태 갱신
        # ------------------------------------------------------------------

        def _update_status(self) -> None:
            """ONNX Runtime, Redis Feature Store, AI 제어 상태 갱신"""
            try:
                # Redis 상태 확인
                from ..utils.db_connectors import get_redis_connector
                redis_client = get_redis_connector()
                redis_ok = redis_client is not None

                if hasattr(self, "label_redis_status"):
                    self.label_redis_status.setText("[OK] Redis: 연결됨" if redis_ok else "[오류] Redis: 미연결")

                # Redis에서 Feature Store 키 수 조회
                if redis_ok and hasattr(self, "label_feature_count"):
                    try:
                        count = redis_client.dbsize()
                        self.label_feature_count.setText(f"Feature 키: {count:,}개 [Redis]")
                    except Exception:
                        pass

                # ONNX Runtime 상태
                onnx_status = "미설치"
                try:
                    import onnxruntime  # type: ignore
                    onnx_status = f"v{onnxruntime.__version__} (활성)"
                except ImportError:
                    onnx_status = "미설치"

                if hasattr(self, "label_onnx_status"):
                    self.label_onnx_status.setText(f"ONNX Runtime: {onnx_status}")

                # MLflow 상태
                if hasattr(self, "label_mlflow_status"):
                    try:
                        import requests  # type: ignore
                        r = requests.get("http://127.0.0.1:5000/health", timeout=1)
                        mlflow_ok = r.status_code == 200
                    except Exception:
                        mlflow_ok = False
                    self.label_mlflow_status.setText(
                        "[OK] MLflow: 연결됨" if mlflow_ok else "[오류] MLflow: 미연결"
                    )

                # AI 모드 상태 (다이얼로그 설정 기반)
                if hasattr(self, "label_summary_mode"):
                    dlg = self._detail_dialog
                    if dlg is not None and hasattr(dlg, "collect_current_settings"):
                        try:
                            ai_settings = dlg.collect_current_settings().get("ai_ml", {})
                            mode = ai_settings.get("ai_mode", "OFF")
                            gap_pred = "ON" if ai_settings.get("gap_prediction_enabled", False) else "OFF"
                            last_run = ai_settings.get("last_run_at", "--")
                            self.label_summary_mode.setText(
                                f"AI 모드: {mode} | Gap 예측: {gap_pred} | 마지막 실행: {last_run}"
                            )
                        except Exception:
                            pass

            except Exception as exc:
                logger.debug("[AIMLTab] 상태 갱신 실패: %s", exc)

        # ------------------------------------------------------------------
        # 설정 저장/복원 (공개 API — status_widget.py에서 호출)
        # ------------------------------------------------------------------

        def set_settings_manager(self, manager) -> None:
            """UISettingsManager 주입 → 다이얼로그에 전달"""
            self._settings_manager = manager
            dlg = self._get_or_create_dialog()
            if dlg is not None and hasattr(dlg, "set_settings_manager"):
                dlg.set_settings_manager(manager)

        def restore_settings(self, settings: dict) -> None:
            """MongoDB에서 로드한 AI/ML 설정을 다이얼로그에 복원합니다."""
            dlg = self._get_or_create_dialog()
            if dlg is not None and hasattr(dlg, "restore_settings"):
                dlg.restore_settings(settings)
                # 요약 레이블도 갱신
                self._on_detail_settings_changed(settings)

        def collect_current_settings(self) -> dict:
            """현재 AI/ML 설정을 다이얼로그에서 수집합니다."""
            dlg = self._get_or_create_dialog()
            if dlg is not None and hasattr(dlg, "collect_current_settings"):
                return dlg.collect_current_settings()
            return {}

        def on_settings_changed(self) -> None:
            """설정 변경 알림 (하위 호환 유지)"""
            pass

        # ------------------------------------------------------------------
        # 생명 주기
        # ------------------------------------------------------------------

        def start_updates(self, interval_ms: int = 3000) -> None:
            self._timer.setInterval(max(1000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

else:
    class AIMLTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""

        def __init__(self, parent=None):
            logger.warning("[AIMLTab] PyQt5 미설치 — 더미 클래스 사용")

        def start_updates(self, interval_ms: int = 3000) -> None:
            pass

        def stop_updates(self) -> None:
            pass

        def set_settings_manager(self, manager) -> None:
            pass

        def restore_settings(self, settings: dict) -> None:
            pass

        def collect_current_settings(self) -> dict:
            return {}

        def on_settings_changed(self) -> None:
            pass
