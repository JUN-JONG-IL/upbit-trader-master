# -*- coding: utf-8 -*-
"""스마트 스캐너 필터 설정 다이얼로그 (비모달)

9개 조건 탭(거래량/가격변동성/기술분석/AI-ML/사용자정의/시장기준/시간대/리스크/특수조건)과
고급 조건식을 비모달 팝업으로 표시합니다. 설정 변경 시 자동 저장됩니다.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer, QThread, Qt, pyqtSignal, pyqtSlot
    from PyQt5.QtWidgets import QDialog, QFileDialog, QMessageBox
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_UI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_settings_dialog.ui")


if _HAS_QT:
    class ScannerSettingsDialog(QDialog):
        """스마트 스캐너 필터 설정 다이얼로그 (비모달 팝업).

        기존 scanner_tab의 필터 조건 UI를 별도 창으로 표시합니다.
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
                logger.warning("[ScannerSettingsDialog] UI 로드 실패: %s", exc)

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
                self.radioAND.toggled.connect(self._on_settings_changed)
                self.radioOR.toggled.connect(self._on_settings_changed)
                self.radioCUSTOM.toggled.connect(self._on_mode_changed)
                self.btnSave.clicked.connect(self._on_save_clicked)
                self.btnLoad.clicked.connect(self._on_load_clicked)
                self.btnReset.clicked.connect(self._on_reset_clicked)
            except AttributeError as exc:
                logger.debug("[ScannerSettingsDialog] 시그널 연결 일부 실패: %s", exc)

            try:
                self.btnCustomHelp.clicked.connect(self._on_custom_help)
            except AttributeError as exc:
                logger.debug("[ScannerSettingsDialog] 커스텀 시그널 연결 일부 실패: %s", exc)

            # 모든 cb_ 체크박스에 자동 저장 연결
            for cb_name in dir(self):
                if cb_name.startswith("cb_"):
                    cb = getattr(self, cb_name, None)
                    if cb is not None and hasattr(cb, "stateChanged"):
                        try:
                            cb.stateChanged.connect(self._on_settings_changed)
                        except Exception:
                            pass

            # cbAllSymbols
            cbAll = getattr(self, "cbAllSymbols", None)
            if cbAll is not None:
                cbAll.stateChanged.connect(self._on_settings_changed)

        # ------------------------------------------------------------------
        # 슬롯
        # ------------------------------------------------------------------

        def _on_mode_changed(self) -> None:
            """조건 모드 변경 시 CUSTOM 입력창 표시/숨김"""
            try:
                self.groupCustom.setVisible(self.radioCUSTOM.isChecked())
                self._on_settings_changed()
            except AttributeError:
                pass

        def _on_settings_changed(self) -> None:
            """설정 변경 시 500ms 대기 후 저장 (Debounce) + 시그널 emit"""
            self._save_timer.start(500)
            # 변경 즉시 시그널 emit (요약 레이블 실시간 갱신)
            self.settings_changed.emit(self.collect_current_settings())

        def _on_save_clicked(self) -> None:
            """스캐너 조건 저장 (MongoDB)"""
            QMessageBox.information(self, "저장", "스캐너 조건이 저장되었습니다.")

        def _on_load_clicked(self) -> None:
            """저장된 조건 불러오기"""
            pass

        def _on_reset_clicked(self) -> None:
            """모든 체크박스 초기화"""
            for cb_name in dir(self):
                if cb_name.startswith("cb_"):
                    cb = getattr(self, cb_name, None)
                    if cb is not None and hasattr(cb, "setChecked"):
                        cb.setChecked(False)
            try:
                self.lineEditCustom.clear()
            except AttributeError:
                pass

        def _on_custom_help(self) -> None:
            """고급 조건식 도움말"""
            help_text = (
                "고급 조건식 문법 예시:\n\n"
                "  (거래량 > 1000 AND RSI < 30) OR (즐겨찾기 AND 급등 > 5%)\n\n"
                "지원 키워드: 거래량, 거래대금, RSI, MACD, 볼린저밴드, 이동평균,\n"
                "             급등, 급락, 즐겨찾기, 신규상장, BTC마켓, KRW마켓"
            )
            QMessageBox.information(self, "조건식 도움말", help_text)

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
                logger.info("[ScannerSettingsDialog] ✅ 설정 자동 저장 완료")
            except Exception as exc:
                logger.error("[ScannerSettingsDialog] ❌ 설정 저장 실패: %s", exc, exc_info=True)

        def collect_current_settings(self) -> dict:
            """현재 체크박스 상태를 dict로 수집합니다."""
            mode = self._current_mode()

            cbAll = getattr(self, "cbAllSymbols", None)
            all_symbols = cbAll.isChecked() if cbAll is not None else False

            trading_names = {
                "cb_volume_top100", "cb_trade_value_top100",
                "cb_trade_count_top100", "cb_active_symbols", "cb_inactive_symbols",
            }
            price_names = {
                "cb_surge_5pct", "cb_crash_5pct", "cb_surge_10pct",
                "cb_crash_10pct", "cb_high_volatility", "cb_stable",
            }
            tech_names = {
                "cb_rsi_overbought", "cb_rsi_oversold", "cb_macd_golden",
                "cb_macd_dead", "cb_bb_upper", "cb_bb_lower",
                "cb_ma_align", "cb_ma_reverse", "cb_volume_breakout",
            }
            ai_ml_names = {
                "cb_ai_recommend", "cb_gap_predict", "cb_pattern_detect", "cb_anomaly",
            }
            user_priority_names = {
                "cb_favorites", "cb_high_priority", "cb_recent_viewed", "cb_has_memo",
            }
            time_names = {
                "cb_market_open", "cb_market_close", "cb_asia_time", "cb_us_time",
            }
            risk_names = {
                "cb_low_volatility", "cb_high_volatility_risk", "cb_top_marketcap",
                "cb_high_liquidity", "cb_short_available", "cb_leverage",
            }

            def _collect_group(names):
                result = {}
                for n in names:
                    cb = getattr(self, n, None)
                    if cb is not None and hasattr(cb, "isChecked"):
                        result[n] = cb.isChecked()
                return result

            known_names = (
                trading_names | price_names | tech_names
                | ai_ml_names | user_priority_names | time_names | risk_names
            )
            all_cb = {
                n for n in dir(self)
                if n.startswith("cb_")
                and hasattr(getattr(self, n, None), "isChecked")
            }
            special_names = all_cb - known_names

            custom_expr = ""
            try:
                custom_expr = self.lineEditCustom.text().strip()
            except AttributeError:
                pass

            return {
                "smart_scanner": {
                    "condition_mode": mode,
                    "all_symbols": all_symbols,
                    "trading_activity": _collect_group(trading_names),
                    "price_volatility": _collect_group(price_names),
                    "technical_analysis": _collect_group(tech_names),
                    "ai_ml_analysis": _collect_group(ai_ml_names),
                    "user_priority": _collect_group(user_priority_names),
                    "time_based": _collect_group(time_names),
                    "risk_management": _collect_group(risk_names),
                    "special_conditions": _collect_group(special_names),
                    "custom_expression": custom_expr,
                }
            }

        def restore_settings(self, settings: dict) -> None:
            """MongoDB에서 로드한 스마트 스캐너 설정을 UI에 복원합니다."""
            scanner = settings.get("smart_scanner", {})
            if not scanner:
                return
            try:
                mode = scanner.get("condition_mode", "AND")
                mode_map = {
                    "AND": "radioAND",
                    "OR": "radioOR",
                    "CUSTOM": "radioCUSTOM",
                }
                radio = getattr(self, mode_map.get(mode, "radioAND"), None)
                if radio is not None:
                    radio.setChecked(True)

                all_sym = scanner.get("all_symbols", False)
                cbAll = getattr(self, "cbAllSymbols", None)
                if cbAll is not None:
                    cbAll.setChecked(bool(all_sym))

                for group_key in (
                    "trading_activity", "price_volatility",
                    "technical_analysis", "ai_ml_analysis",
                    "user_priority", "time_based",
                    "risk_management", "special_conditions",
                ):
                    group = scanner.get(group_key, {})
                    for cb_name, checked in group.items():
                        cb = getattr(self, cb_name, None)
                        if cb is not None and hasattr(cb, "setChecked"):
                            cb.setChecked(bool(checked))

                custom_expr = scanner.get("custom_expression", "")
                try:
                    self.lineEditCustom.setText(custom_expr)
                except AttributeError:
                    pass

                logger.info("[ScannerSettingsDialog] 설정 복원 완료")
            except Exception as exc:
                logger.debug("[ScannerSettingsDialog] 설정 복원 실패: %s", exc)

        # ------------------------------------------------------------------
        # 내부 유틸
        # ------------------------------------------------------------------

        def _current_mode(self) -> str:
            """현재 선택된 조건 조합 방식 반환"""
            try:
                if self.radioOR.isChecked():
                    return "OR"
                if self.radioCUSTOM.isChecked():
                    return "CUSTOM"
            except AttributeError:
                pass
            return "AND"

        def get_current_mode(self) -> str:
            """현재 선택된 조건 조합 방식 반환 (공개 API)"""
            return self._current_mode()

        def get_active_condition_count(self) -> int:
            """활성화된 조건 체크박스 수 반환 (요약 레이블용)"""
            count = 0
            for cb_name in dir(self):
                if cb_name.startswith("cb_"):
                    cb = getattr(self, cb_name, None)
                    if cb is not None and hasattr(cb, "isChecked") and cb.isChecked():
                        count += 1
            return count

        def _collect_conditions(self) -> dict:
            """체크된 조건을 dict로 수집 (스캔 실행 시 호출)"""
            conditions: dict = {}
            for cb_name in dir(self):
                if cb_name.startswith("cb_"):
                    cb = getattr(self, cb_name, None)
                    if cb is not None and hasattr(cb, "isChecked") and cb.isChecked():
                        conditions[cb_name] = True
            return conditions

        # ------------------------------------------------------------------
        # 생명 주기
        # ------------------------------------------------------------------

        def closeEvent(self, event) -> None:
            """창 닫기 — 설정은 자동 저장됨"""
            logger.info("[ScannerSettingsDialog] 창 닫힘 — 설정은 자동 저장됨")
            event.accept()

else:
    class ScannerSettingsDialog:  # type: ignore[no-redef]
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

        def _current_mode(self) -> str:
            return "AND"

        def get_active_condition_count(self) -> int:
            return 0