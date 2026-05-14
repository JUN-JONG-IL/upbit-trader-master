# -*- coding: utf-8 -*-
"""수집 설정 상세 다이얼로그 (비모달)

수집 타임프레임, 캔들 수 정책, 압축/보관 정책 등 전체 설정을
비모달 팝업으로 표시합니다. 설정 변경 시 Debounce(500ms) 후 자동 저장됩니다.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Dict

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer, Qt, pyqtSignal
    from PyQt5.QtWidgets import QDialog
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_UI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "collection_settings_dialog.ui")

_TF_KEYS = ("1m", "5m", "15m", "1h", "4h", "1d")
_MINUTES_PER_DAY = 1440
_PERMANENT_RETENTION_DAYS = 36500
_VOLUME_PRESETS: Dict[str, Dict[str, int]] = {
    "light": {
        "limit_1m": 150000,
        "limit_5m": 50000,
        "limit_15m": 30000,
        "limit_1h": 12000,
        "limit_4h": 5000,
        "limit_1d": 500,
    },
    "balance": {
        "limit_1m": 300000,
        "limit_5m": 100000,
        "limit_15m": 50000,
        "limit_1h": 20000,
        "limit_4h": 10000,
        "limit_1d": 1000,
    },
    "heavy": {
        "limit_1m": 1000000,
        "limit_5m": 300000,
        "limit_15m": 150000,
        "limit_1h": 60000,
        "limit_4h": 30000,
        "limit_1d": 3000,
    },
}
_VOLUME_PRESET_ORDER = ("light", "balance", "heavy")

# 프리셋별 타임프레임 활성화 정책 (SSOT)
# 1m은 항상 True (UI에서 비활성화 불가)
_PRESET_TIMEFRAMES = {
    "light": {
        "1m": True, "5m": True, "15m": False,
        "1h": True, "4h": False, "1d": False,
    },
    "balance": {
        "1m": True, "5m": True, "15m": False,
        "1h": True, "4h": False, "1d": True,
    },
    "heavy": {
        "1m": True, "5m": True, "15m": True,
        "1h": True, "4h": True, "1d": True,
    },
}

# 프리셋별 압축/보관 기본 정책
_PRESET_POLICIES = {
    "light":   {"compression_days": 1,  "retention_days": 90},
    "balance": {"compression_days": 7,  "retention_days": 180},
    "heavy":   {"compression_days": 30, "retention_days": 365},
}


if _HAS_QT:
    class CollectionSettingsDialog(QDialog):
        """수집 설정 상세 다이얼로그 (비모달 팝업).

        기존 collection_tab의 전체 설정 UI를 별도 창으로 표시합니다.
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
                logger.warning("[CollectionSettingsDialog] UI 로드 실패: %s", exc)

            self._settings_manager = None

            # Debounce 타이머 (500ms 후 저장)
            self._save_timer = QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.setInterval(500)
            self._save_timer.timeout.connect(self._on_save_timer)

            self._connect_auto_save_signals()
            self._connect_preset_signals()
            self._configure_candle_policy_ui()

            # 닫기 버튼
            if hasattr(self, "btn_close"):
                self.btn_close.clicked.connect(self.close)

        # ------------------------------------------------------------------
        # 시그널 연결
        # ------------------------------------------------------------------

        def _connect_auto_save_signals(self) -> None:
            """타임프레임 체크박스/콤보박스/스핀박스 변경 시 자동 저장 예약"""
            for tf in _TF_KEYS:
                w = getattr(self, f"chk_tf_{tf}", None)
                if w is not None:
                    w.stateChanged.connect(self._on_settings_changed)

            for combo_name in [
                "combo_compression_days",
                "combo_retention_days",
                "combo_volume_preset",
            ]:
                w = getattr(self, combo_name, None)
                if w is not None:
                    w.currentIndexChanged.connect(self._on_settings_changed)

            # 일수 직접 입력 스핀박스 — 변경 시 콤보 동기화 + 자동 저장
            spin_comp = getattr(self, "spin_compression_days", None)
            if spin_comp is not None:
                spin_comp.valueChanged.connect(self._on_compression_spin_changed)
                spin_comp.valueChanged.connect(self._on_settings_changed)

            spin_ret = getattr(self, "spin_retention_days", None)
            if spin_ret is not None:
                spin_ret.valueChanged.connect(self._on_retention_spin_changed)
                spin_ret.valueChanged.connect(self._on_settings_changed)

            # WebSocket 스핀박스 변경 시 자동 저장
            spin = getattr(self, "spin_ws_max_subscribe", None)
            if spin is not None:
                spin.valueChanged.connect(self._on_settings_changed)

            for tf in _TF_KEYS:
                spin_limit = getattr(self, f"spin_limit_{tf}", None)
                if spin_limit is not None:
                    spin_limit.valueChanged.connect(self._on_settings_changed)
                    spin_limit.valueChanged.connect(self._update_volume_days_hint)

            # 적용 버튼 연결
            btn = getattr(self, "btn_apply_ws_limit", None)
            if btn is not None:
                btn.clicked.connect(self._on_apply_ws_limit)

        def _configure_candle_policy_ui(self) -> None:
            """캔들 수 중심 정책 UI로 단순화합니다."""
            group_historical = getattr(self, "groupBox_historical", None)
            if group_historical is not None:
                group_historical.setVisible(False)

            label_role = getattr(self, "label_role_header", None)
            if label_role is not None:
                label_role.setToolTip(
                    "정책 편집은 이 화면(SSOT)에서만 수행합니다.\n"
                    "백필/스케줄러 화면은 실행/스케줄/상태만 관리합니다.\n"
                    "대상 심볼은 스마트 스캐너 + AI/ML 선택 결과를 사용합니다."
                )

            label_comp_hint = getattr(self, "label_compression_hint", None)
            if label_comp_hint is not None:
                label_comp_hint.setText(
                    "ℹ️ 압축은 삭제가 아니며 과거 데이터 조회/분석이 가능합니다. "
                    "삭제는 보관기간 만료 시에만 수행됩니다."
                )

            group_presets = getattr(self, "groupBox_presets", None)
            if group_presets is not None:
                group_presets.setTitle("수집 정책 프리셋 — 타임프레임 · 캔들 수 · 압축 · 보관 일괄 설정")
            self._update_volume_days_hint()
            # 콤보→스핀 초기 동기화
            self._sync_combo_to_spin_compression()
            self._sync_combo_to_spin_retention()

        @staticmethod
        def _minutes_per_tf(tf: str) -> int:
            return {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": _MINUTES_PER_DAY}.get(tf, 1)

        @staticmethod
        def _extract_first_int(value: str, default: int = 0) -> int:
            digits = "".join(ch for ch in (value or "") if ch.isdigit())
            return int(digits) if digits else default

        def _normalize_compression_text(self, value: str) -> str:
            txt = (value or "").strip()
            if not txt:
                return "1일 후 (권장)"
            if "즉시" in txt or txt in ("0", "0 일"):
                return "즉시 (0일)"
            n = self._extract_first_int(txt, 0)
            if n <= 0:
                return txt
            if "주" in txt:
                return f"{n * 7}일 후"
            if "개월" in txt or "달" in txt:
                return f"{n * 30}일 후"
            return f"{n}일 후"

        def _normalize_retention_text(self, value: str) -> str:
            txt = (value or "").strip()
            if not txt:
                return "90일 (3개월, 기본 권장)"
            if "영구" in txt or txt in ("0", "0 일"):
                return "영구 보관 (0일)"
            n = self._extract_first_int(txt, 0)
            if n <= 0:
                return txt
            if "년" in txt:
                return f"{n * 365}일"
            if "개월" in txt or "달" in txt:
                return f"{n * 30}일"
            if "주" in txt:
                return f"{n * 7}일"
            return f"{n}일"

        def _to_days(self, value: str, default_days: int, *, for_compression: bool) -> int:
            txt = (value or "").strip()
            if not txt:
                return default_days
            if "영구" in txt:
                return 0
            if for_compression and ("즉시" in txt or txt in ("0", "0 일")):
                return 0
            # "N일" 패턴을 먼저 매칭: 콤보 텍스트가 "90일 (3개월...)" 처럼 일수+단위가 혼합될 때
            # 첫 번째로 나타나는 "숫자+일" 패턴을 사용해 일 수를 정확히 추출합니다.
            m = re.search(r"(\d+)\s*일", txt)
            if m:
                n = int(m.group(1))
                return 0 if n == 0 else n
            m = re.search(r"(\d+)\s*년", txt)
            if m:
                return int(m.group(1)) * 365
            m = re.search(r"(\d+)\s*개월", txt)
            if m:
                return int(m.group(1)) * 30
            m = re.search(r"(\d+)\s*주", txt)
            if m:
                return int(m.group(1)) * 7
            m = re.search(r"\d+", txt)
            if m:
                return int(m.group())
            return default_days

        # ------------------------------------------------------------------
        # 일수 직접 입력 스핀박스 ↔ 콤보 동기화
        # ------------------------------------------------------------------

        def _on_compression_spin_changed(self, days: int) -> None:
            """spin_compression_days 변경 → combo_compression_days 동기화"""
            combo = getattr(self, "combo_compression_days", None)
            if combo is None:
                return
            combo.blockSignals(True)
            try:
                # 가장 가까운 프리셋 선택 또는 없으면 그냥 인덱스 유지
                day_to_idx = {0: 0, 1: 1, 7: 2, 30: 3}
                if days in day_to_idx:
                    combo.setCurrentIndex(day_to_idx[days])
            finally:
                combo.blockSignals(False)

        def _on_retention_spin_changed(self, days: int) -> None:
            """spin_retention_days 변경 → combo_retention_days 동기화"""
            combo = getattr(self, "combo_retention_days", None)
            if combo is None:
                return
            combo.blockSignals(True)
            try:
                day_to_idx = {30: 0, 90: 1, 180: 2, 365: 3, 0: 4}
                if days in day_to_idx:
                    combo.setCurrentIndex(day_to_idx[days])
            finally:
                combo.blockSignals(False)

        def _sync_combo_to_spin_compression(self) -> None:
            """combo_compression_days → spin_compression_days 초기 동기화"""
            combo = getattr(self, "combo_compression_days", None)
            spin = getattr(self, "spin_compression_days", None)
            if combo is None or spin is None:
                return
            idx_to_days = {0: 0, 1: 1, 2: 7, 3: 30}
            days = idx_to_days.get(combo.currentIndex(), 1)
            spin.blockSignals(True)
            try:
                spin.setValue(days)
            finally:
                spin.blockSignals(False)

        def _sync_combo_to_spin_retention(self) -> None:
            """combo_retention_days → spin_retention_days 초기 동기화"""
            combo = getattr(self, "combo_retention_days", None)
            spin = getattr(self, "spin_retention_days", None)
            if combo is None or spin is None:
                return
            idx_to_days = {0: 30, 1: 90, 2: 180, 3: 365, 4: 0}
            days = idx_to_days.get(combo.currentIndex(), 90)
            spin.blockSignals(True)
            try:
                spin.setValue(days)
            finally:
                spin.blockSignals(False)

        def _update_volume_days_hint(self) -> None:
            label = getattr(self, "label_volume_ssot_hint", None)
            if label is None:
                return
            parts = []
            for tf in _TF_KEYS:
                spin = getattr(self, f"spin_limit_{tf}", None)
                if spin is None:
                    continue
                candles = int(spin.value())
                days = (candles * self._minutes_per_tf(tf)) / float(_MINUTES_PER_DAY)
                parts.append(f"{tf}≈{days:,.1f}일")
            label.setText(
                "캔들 수 기준 자동 환산(설명용): "
                + " / ".join(parts)
                + " | 편집값은 타임프레임별 최대 캔들 수입니다."
            )

        def _restore_combo_text(self, combo, value: str) -> None:
            if combo is None or not value:
                return
            idx = combo.findText(value)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        def _connect_preset_signals(self) -> None:
            """프리셋 버튼 시그널 연결 (라이트/밸런스/헤비/기본값복원)"""
            # 수집 정책 프리셋 (groupBox_presets)
            if hasattr(self, "btn_preset_light"):
                self.btn_preset_light.clicked.connect(self.apply_preset_light)
            if hasattr(self, "btn_preset_balance"):
                self.btn_preset_balance.clicked.connect(self.apply_preset_balance)
            if hasattr(self, "btn_preset_heavy"):
                self.btn_preset_heavy.clicked.connect(self.apply_preset_heavy)
            if hasattr(self, "btn_preset_default"):
                self.btn_preset_default.clicked.connect(self.apply_preset_default)

            # 데이터 용량(캔들 수) 프리셋 버튼 (별도 그룹박스) — 캔들 수 + 타임프레임 동기화
            # 이 버튼들은 groupBox_presets의 라이트/밸런스/헤비와 달리 데이터 용량 한도만 관리하며
            # 내부에서 _apply_volume_preset을 호출해 타임프레임도 함께 동기화합니다.
            for preset_name in ("btn_volume_preset_light", "btn_volume_preset_balance", "btn_volume_preset_heavy"):
                btn = getattr(self, preset_name, None)
                if btn is not None:
                    btn.clicked.connect(self._on_volume_preset_clicked)
            combo_volume = getattr(self, "combo_volume_preset", None)
            if combo_volume is not None:
                combo_volume.currentIndexChanged.connect(self._on_volume_preset_combo_changed)

            # 콤보 변경 → 스핀 동기화
            combo_comp = getattr(self, "combo_compression_days", None)
            if combo_comp is not None:
                combo_comp.currentIndexChanged.connect(self._on_compression_combo_changed)
            combo_ret = getattr(self, "combo_retention_days", None)
            if combo_ret is not None:
                combo_ret.currentIndexChanged.connect(self._on_retention_combo_changed)

        def _on_compression_combo_changed(self, idx: int) -> None:
            """combo_compression_days 변경 → spin_compression_days 동기화"""
            spin = getattr(self, "spin_compression_days", None)
            if spin is None:
                return
            idx_to_days = {0: 0, 1: 1, 2: 7, 3: 30}
            days = idx_to_days.get(idx, 1)
            spin.blockSignals(True)
            try:
                spin.setValue(days)
            finally:
                spin.blockSignals(False)

        def _on_retention_combo_changed(self, idx: int) -> None:
            """combo_retention_days 변경 → spin_retention_days 동기화"""
            spin = getattr(self, "spin_retention_days", None)
            if spin is None:
                return
            idx_to_days = {0: 30, 1: 90, 2: 180, 3: 365, 4: 0}
            days = idx_to_days.get(idx, 90)
            spin.blockSignals(True)
            try:
                spin.setValue(days)
            finally:
                spin.blockSignals(False)

        def _on_volume_preset_clicked(self) -> None:
            sender = self.sender()
            if sender is None:
                return
            preset_map = {
                "btn_volume_preset_light": "light",
                "btn_volume_preset_balance": "balance",
                "btn_volume_preset_heavy": "heavy",
            }
            preset_key = preset_map.get(sender.objectName())
            if preset_key is None:
                return
            self._apply_volume_preset(preset_key)

        def _on_volume_preset_combo_changed(self, idx: int) -> None:
            if not (0 <= idx < len(_VOLUME_PRESET_ORDER)):
                return
            self._apply_volume_preset(_VOLUME_PRESET_ORDER[idx])

        def _apply_volume_preset(self, preset_key: str) -> None:
            """데이터 용량 프리셋 적용 — 타임프레임 + 캔들 수 동기화."""
            limits = _VOLUME_PRESETS.get(preset_key)
            if not limits:
                return

            # 타임프레임 체크 상태 동기화 (SSOT)
            tf_states = _PRESET_TIMEFRAMES.get(preset_key, {})
            for tf in _TF_KEYS:
                chk = getattr(self, f"chk_tf_{tf}", None)
                if chk is not None and not chk.property("readOnly"):
                    enabled = tf_states.get(tf, False)
                    chk.blockSignals(True)
                    try:
                        chk.setChecked(enabled)
                    finally:
                        chk.blockSignals(False)

            # 캔들 수 스핀박스 업데이트
            for tf in _TF_KEYS:
                spin = getattr(self, f"spin_limit_{tf}", None)
                if spin is not None:
                    limit = limits.get(f"limit_{tf}")
                    if limit is not None:
                        spin.setValue(int(limit))

            combo = getattr(self, "combo_volume_preset", None)
            if combo is not None:
                try:
                    idx = _VOLUME_PRESET_ORDER.index(preset_key)
                    combo.blockSignals(True)
                    combo.setCurrentIndex(idx)
                    combo.blockSignals(False)
                except ValueError:
                    combo.setCurrentIndex(0)
            self._on_settings_changed()

        def _on_apply_ws_limit(self) -> None:
            """WebSocket 최대 구독 수 설정 적용 + 1,000 초과 경고"""
            spin = getattr(self, "spin_ws_max_subscribe", None)
            if spin is not None:
                val = spin.value()
                # 1,000 초과 시 권고 경고
                if val > 1000:
                    try:
                        from PyQt5.QtWidgets import QMessageBox
                        reply = QMessageBox.question(
                            self,
                            "대용량 구독 경고",
                            f"WebSocket 구독 종목 수를 {val:,}개로 설정하면\n"
                            "메모리·CPU 사용량이 크게 증가할 수 있습니다.\n\n"
                            "권장 최대값: 1,000개\n\n"
                            "계속 진행하시겠습니까?",
                            QMessageBox.Yes | QMessageBox.No,
                            QMessageBox.No,
                        )
                        if reply != QMessageBox.Yes:
                            return
                    except Exception:
                        pass
            self._on_save_timer()
            # config_loader 캐시 무효화 (런타임 설정 즉시 반영)
            try:
                from ..utils.config_loader import invalidate_cache
                invalidate_cache()
                logger.info("[CollectionSettingsDialog] config_loader 캐시 무효화 완료")
            except Exception as exc:
                logger.debug("[CollectionSettingsDialog] 캐시 무효화 실패: %s", exc)

        # ------------------------------------------------------------------
        # 설정 저장/복원
        # ------------------------------------------------------------------

        def set_settings_manager(self, manager) -> None:
            """UISettingsManager 주입"""
            self._settings_manager = manager

        def _on_settings_changed(self) -> None:
            """설정 변경 시 500ms 대기 후 저장 (Debounce) + 시그널 emit"""
            self._save_timer.start(500)
            # 변경 즉시 시그널 emit (요약 레이블 실시간 갱신)
            self.settings_changed.emit(self.collect_current_settings())

        def _on_save_timer(self) -> None:
            """Debounce 타이머 만료 시 저장 실행 (✅ 동기 버전, 인자 순서 수정)"""
            if self._settings_manager is None:
                return
            
            settings = self.collect_current_settings()

            try:
                # ✅ 수정: 인자 순서 변경 (settings, user_id)
                # SettingsManager.save_settings(settings: dict, user_id: str = "default")
                self._settings_manager.save_settings(settings, "default")
                logger.info("[CollectionSettingsDialog] ✅ 설정 자동 저장 완료")
            except Exception as exc:
                logger.error("[CollectionSettingsDialog] ❌ 설정 저장 실패: %s", exc, exc_info=True)

        def collect_current_settings(self) -> dict:
            """현재 UI 상태를 dict로 수집합니다."""
            tf_map = {
                "chk_tf_1m": "1m",
                "chk_tf_5m": "5m",
                "chk_tf_15m": "15m",
                "chk_tf_1h": "1h",
                "chk_tf_4h": "4h",
                "chk_tf_1d": "1d",
            }
            timeframes = [
                tf for wname, tf in tf_map.items()
                if getattr(self, wname, None) is not None
                and getattr(self, wname).isChecked()
            ]

            # 압축 일수: 스핀박스 우선, 없으면 콤보 파싱
            spin_comp = getattr(self, "spin_compression_days", None)
            if spin_comp is not None:
                compression_days = int(spin_comp.value())
            else:
                combo_comp = getattr(self, "combo_compression_days", None)
                compression_days = self._to_days(
                    combo_comp.currentText() if combo_comp is not None else "",
                    1, for_compression=True,
                )

            # 보관 일수: 스핀박스 우선, 없으면 콤보 파싱
            spin_ret = getattr(self, "spin_retention_days", None)
            if spin_ret is not None:
                retention_days = int(spin_ret.value())
            else:
                combo_ret = getattr(self, "combo_retention_days", None)
                retention_days = self._to_days(
                    combo_ret.currentText() if combo_ret is not None else "",
                    90, for_compression=False,
                )

            combo_volume = getattr(self, "combo_volume_preset", None)
            if combo_volume is not None:
                idx = combo_volume.currentIndex()
                volume_preset = _VOLUME_PRESET_ORDER[idx] if 0 <= idx < len(_VOLUME_PRESET_ORDER) else "light"
            else:
                volume_preset = "light"
            volume_limits = {}
            for tf in _TF_KEYS:
                spin = getattr(self, f"spin_limit_{tf}", None)
                default_limit = _VOLUME_PRESETS["light"][f"limit_{tf}"]
                volume_limits[f"limit_{tf}"] = int(spin.value()) if spin is not None else default_limit

            return {
                "collection_settings": {
                    "timeframes": timeframes,
                    "compression_days": compression_days,
                    "retention_days": retention_days,
                    "volume_preset": volume_preset,
                    **volume_limits,
                    "ws_max_subscribe": (
                        getattr(self, "spin_ws_max_subscribe").value()
                        if getattr(self, "spin_ws_max_subscribe", None) is not None
                        else 300
                    ),
                }
            }

        def restore_settings(self, settings: dict) -> None:
            """MongoDB에서 로드한 설정을 UI에 복원합니다."""
            col = settings.get("collection_settings", {})
            if not col:
                return
            try:
                tf_list = col.get("timeframes", [])
                tf_map = {
                    "chk_tf_1m": "1m",
                    "chk_tf_5m": "5m",
                    "chk_tf_15m": "15m",
                    "chk_tf_1h": "1h",
                    "chk_tf_4h": "4h",
                    "chk_tf_1d": "1d",
                }
                for widget_name, tf in tf_map.items():
                    chk = getattr(self, widget_name, None)
                    if chk is not None:
                        chk.setChecked(tf in tf_list)

                # 압축 일수 복원
                comp_days = col.get("compression_days", 1)
                try:
                    comp_days = int(comp_days)
                except (TypeError, ValueError):
                    comp_days = 1
                spin_comp = getattr(self, "spin_compression_days", None)
                if spin_comp is not None:
                    spin_comp.setValue(comp_days)
                combo_comp = getattr(self, "combo_compression_days", None)
                if combo_comp is not None:
                    # days → 콤보 인덱스 (즉시=0, 1일=1, 7일=2, 30일=3); 프리셋 외 값이면 index 1(1일)로 폴백
                    idx_map = {0: 0, 1: 1, 7: 2, 30: 3}
                    combo_comp.setCurrentIndex(idx_map.get(comp_days, 1))

                # 보관 일수 복원
                ret_days = col.get("retention_days", 90)
                try:
                    ret_days = int(ret_days)
                except (TypeError, ValueError):
                    ret_days = 90
                spin_ret = getattr(self, "spin_retention_days", None)
                if spin_ret is not None:
                    spin_ret.setValue(ret_days)
                combo_ret = getattr(self, "combo_retention_days", None)
                if combo_ret is not None:
                    # days → 콤보 인덱스 (30=0, 90=1, 180=2, 365=3, 0=4); 프리셋 외 값이면 index 1(90일)로 폴백
                    idx_map = {30: 0, 90: 1, 180: 2, 365: 3, 0: 4}
                    combo_ret.setCurrentIndex(idx_map.get(ret_days, 1))

                volume_preset = col.get("volume_preset", "light")
                combo_volume = getattr(self, "combo_volume_preset", None)
                if combo_volume is not None:
                    try:
                        combo_volume.setCurrentIndex(_VOLUME_PRESET_ORDER.index(volume_preset))
                    except ValueError:
                        combo_volume.setCurrentIndex(0)
                for tf in _TF_KEYS:
                    spin = getattr(self, f"spin_limit_{tf}", None)
                    if spin is not None:
                        default_limit = _VOLUME_PRESETS.get(volume_preset, _VOLUME_PRESETS["light"]).get(
                            f"limit_{tf}",
                            _VOLUME_PRESETS["light"][f"limit_{tf}"],
                        )
                        try:
                            spin.setValue(int(col.get(f"limit_{tf}", default_limit)))
                        except (TypeError, ValueError):
                            spin.setValue(int(default_limit))

                # ws_max_subscribe 복원
                ws_max = col.get("ws_max_subscribe", None)
                spin = getattr(self, "spin_ws_max_subscribe", None)
                if spin is not None and ws_max is not None:
                    try:
                        spin.setValue(int(ws_max))
                    except (TypeError, ValueError):
                        pass
                self._update_volume_days_hint()

                logger.info("[CollectionSettingsDialog] 설정 복원 완료")
            except Exception as exc:
                logger.debug("[CollectionSettingsDialog] 설정 복원 실패: %s", exc)

        def get_selected_timeframes(self) -> list:
            """선택된 타임프레임 목록 반환"""
            tfs = []
            tf_map = {
                "chk_tf_1m": "1m",
                "chk_tf_5m": "5m",
                "chk_tf_15m": "15m",
                "chk_tf_1h": "1h",
                "chk_tf_4h": "4h",
                "chk_tf_1d": "1d",
            }
            for widget_name, tf in tf_map.items():
                chk = getattr(self, widget_name, None)
                if chk is not None and chk.isChecked():
                    tfs.append(tf)
            return tfs

        def get_lookback_days(self) -> int:
            """캔들 수 정책 기반 최대 조회 일수(설명용) 반환"""
            max_days = 1
            for tf in _TF_KEYS:
                spin = getattr(self, f"spin_limit_{tf}", None)
                if spin is None:
                    continue
                days = int((int(spin.value()) * self._minutes_per_tf(tf)) / _MINUTES_PER_DAY)
                if days > max_days:
                    max_days = days
            return max_days

        def update_disk_usage(self, ts_gb: float, redis_mb: float, ch_gb: float) -> None:
            """디스크 용량 레이블 갱신"""
            try:
                if hasattr(self, "label_timescale_size"):
                    self.label_timescale_size.setText(f"{ts_gb:.1f} GB")
                if hasattr(self, "label_redis_size"):
                    self.label_redis_size.setText(f"{redis_mb:.0f} MB")
                if hasattr(self, "label_clickhouse_size"):
                    self.label_clickhouse_size.setText(f"{ch_gb:.1f} GB")
            except Exception as exc:
                logger.debug("[CollectionSettingsDialog] 디스크 용량 갱신 실패: %s", exc)

        # ------------------------------------------------------------------
        # 프리셋 핸들러 (라이트/밸런스/헤비/기본값복원)
        # ------------------------------------------------------------------

        def _apply_full_preset(self, preset_key: str) -> None:
            """타임프레임 + 캔들 수 + 압축 + 보관 일수를 한 번에 적용하는 내부 헬퍼."""
            self._apply_volume_preset(preset_key)  # TF + 캔들 수 적용
            policy = _PRESET_POLICIES.get(preset_key, {})
            comp_days = policy.get("compression_days", 1)
            ret_days = policy.get("retention_days", 90)

            # 압축 스핀박스/콤보 (days → 콤보 인덱스: 0=즉시, 1=1일, 7=7일, 30=30일)
            spin_comp = getattr(self, "spin_compression_days", None)
            if spin_comp is not None:
                spin_comp.setValue(comp_days)
            combo_comp = getattr(self, "combo_compression_days", None)
            if combo_comp is not None:
                idx_map = {0: 0, 1: 1, 7: 2, 30: 3}
                combo_comp.setCurrentIndex(idx_map.get(comp_days, 1))

            # 보관 스핀박스/콤보 (days → 콤보 인덱스: 30=0, 90=1, 180=2, 365=3, 0=4)
            spin_ret = getattr(self, "spin_retention_days", None)
            if spin_ret is not None:
                spin_ret.setValue(ret_days)
            combo_ret = getattr(self, "combo_retention_days", None)
            if combo_ret is not None:
                idx_map = {30: 0, 90: 1, 180: 2, 365: 3, 0: 4}
                combo_ret.setCurrentIndex(idx_map.get(ret_days, 1))

        def apply_preset_light(self) -> None:
            """🟢 라이트 프리셋: 1m+5m+1h, 최소 캔들, 1일 후 압축, 90일 보관."""
            try:
                self._apply_full_preset("light")
                logger.info("[CollectionSettingsDialog] 🟢 라이트 프리셋 적용")
            except Exception as exc:
                logger.debug("[CollectionSettingsDialog] 라이트 프리셋 적용 실패: %s", exc)

        def apply_preset_balance(self) -> None:
            """🔵 밸런스 프리셋: 1m+5m+1h+1d, 중간 캔들, 7일 후 압축, 180일 보관."""
            try:
                self._apply_full_preset("balance")
                logger.info("[CollectionSettingsDialog] 🔵 밸런스 프리셋 적용")
            except Exception as exc:
                logger.debug("[CollectionSettingsDialog] 밸런스 프리셋 적용 실패: %s", exc)

        def apply_preset_heavy(self) -> None:
            """🔴 헤비 프리셋: 전체 TF, 최대 캔들, 30일 후 압축, 365일 보관."""
            try:
                self._apply_full_preset("heavy")
                logger.info("[CollectionSettingsDialog] 🔴 헤비 프리셋 적용")
            except Exception as exc:
                logger.debug("[CollectionSettingsDialog] 헤비 프리셋 적용 실패: %s", exc)

        def apply_preset_default(self) -> None:
            """🔄 기본값 복원: 수집 설정 전체를 라이트 기준 기본값으로 복원."""
            try:
                self._apply_full_preset("light")
                # 1m은 항상 체크
                chk_1m = getattr(self, "chk_tf_1m", None)
                if chk_1m is not None:
                    chk_1m.setChecked(True)
                # WS 구독 수 기본값 복원
                spin_ws = getattr(self, "spin_ws_max_subscribe", None)
                if spin_ws is not None:
                    spin_ws.setValue(300)
                logger.info("[CollectionSettingsDialog] 🔄 기본값 복원 완료")
            except Exception as exc:
                logger.debug("[CollectionSettingsDialog] 기본값 복원 실패: %s", exc)

        # 하위 호환: 기존 코드에서 참조하는 이름 유지
        def apply_preset_save_disk(self) -> None:
            """[deprecated] 라이트 프리셋으로 대체됩니다."""
            self.apply_preset_light()

        def apply_preset_indicator_minimum(self) -> None:
            """[deprecated] 라이트 프리셋으로 대체됩니다."""
            self.apply_preset_light()

        def apply_preset_aiml_minimum(self) -> None:
            """[deprecated] 헤비 프리셋으로 대체됩니다."""
            self.apply_preset_heavy()

        # ------------------------------------------------------------------
        # 생명 주기
        # ------------------------------------------------------------------

        def closeEvent(self, event) -> None:
            """창 닫기 — 설정은 자동 저장됨"""
            logger.info("[CollectionSettingsDialog] 창 닫힘 — 설정은 자동 저장됨")
            event.accept()

else:
    class CollectionSettingsDialog:  # type: ignore[no-redef]
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

        def get_selected_timeframes(self) -> list:
            return ["1m", "5m", "1h"]

        def get_lookback_days(self) -> int:
            return 3

        def update_disk_usage(self, *args, **kwargs) -> None:
            pass

        def apply_preset_light(self) -> None:
            pass

        def apply_preset_balance(self) -> None:
            pass

        def apply_preset_heavy(self) -> None:
            pass

        def apply_preset_default(self) -> None:
            pass

        # 하위 호환
        def apply_preset_save_disk(self) -> None:
            pass

        def apply_preset_indicator_minimum(self) -> None:
            pass

        def apply_preset_aiml_minimum(self) -> None:
            pass
