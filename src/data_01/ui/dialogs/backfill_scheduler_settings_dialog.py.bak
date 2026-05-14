# -*- coding: utf-8 -*-
"""백필 / 스케줄러 설정 다이얼로그 (비모달)

스케줄러 자동실행·주기·즉시실행·동시실행 정책과 현재 상태를 관리합니다.
백필 실행 정책(타임프레임/캔들 수/심볼 소스)은 수집 설정(상세) SSOT를 사용합니다.

설정은 MongoDB ui_settings 컬렉션(user_id=default)에 저장되며,
MongoDB가 없을 경우 JSON 파일(~/.upbit_trader/bf_scheduler_settings.json)로 폴백됩니다.

저장 키:
  backfill_scheduler.backfill.timeframes       - list[str] (SSOT: collection_settings.timeframes 미러링)
  backfill_scheduler.backfill.symbol_source    - "smart_scanner_aiml"
  backfill_scheduler.backfill.symbol_range     - "selected" (고정)
  backfill_scheduler.backfill.limit_1m         - int 캔들 수 (SSOT 미러링)
  backfill_scheduler.backfill.limit_5m         - int 캔들 수 (SSOT 미러링)
  backfill_scheduler.backfill.limit_15m        - int 캔들 수 (SSOT 미러링)
  backfill_scheduler.backfill.limit_1h         - int 캔들 수 (SSOT 미러링)
  backfill_scheduler.backfill.limit_4h         - int 캔들 수 (SSOT 미러링)
  backfill_scheduler.backfill.limit_1d         - int 캔들 수 (SSOT 미러링)
  backfill_scheduler.scheduler.auto_run        - bool
  backfill_scheduler.scheduler.interval_preset - "1m" | "5m" | "10m" | "30m" | "60m"
  backfill_scheduler.scheduler.custom_interval - int 분 (호환용, interval_preset 동일값 저장)
  backfill_scheduler.scheduler.auto_start      - bool
  backfill_scheduler.scheduler.kickoff_on_enable - bool (기본 True)
  backfill_scheduler.scheduler.concurrent_policy - "skip" | "rerun"
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_JSON_FALLBACK_PATH = os.path.join(
    os.path.expanduser("~"), ".upbit_trader", "bf_scheduler_settings.json"
)

# ──────────────────────────────────────────────
# 데이터 용량 프리셋 (타임프레임별 최대 캔들 수)
# ──────────────────────────────────────────────
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

# ──────────────────────────────────────────────
# 기본값 (앱 초기 상태 또는 기본값 복원 시 사용)
# ──────────────────────────────────────────────
_DEFAULTS: Dict[str, Any] = {
    "backfill": {
        "timeframes": ["1m", "5m", "1h"],
        "symbol_source": "smart_scanner_aiml",
        "symbol_range": "selected",
        # 타임프레임별 최대 캔들 수 (라이트 프리셋 기본값)
        # 라이트: 저사양/저용량에서도 기본 지표(RSI/MACD/BB) 운용 가능한 최소 구성
        "limit_1m": 150000,
        "limit_5m": 50000,
        "limit_15m": 30000,
        "limit_1h": 12000,
        "limit_4h": 5000,
        "limit_1d": 500,
    },
    "scheduler": {
        "auto_run": False,
        "interval_preset": "5m",
        "custom_interval": 5,
        "auto_start": False,
        "kickoff_on_enable": True,
        "concurrent_policy": "skip",
    },
    # ⚡ 성능(고급) — 백필 처리 속도 SSOT (UI 다이얼로그에서만 수정)
    # 동일 값을 src/14_orchestrator/backfill/performance_settings.py 가 읽어
    # AutoBackfill / AutoBackfillManager / RestCandleCollector / AsyncRateLimiter
    # 에 일괄 주입한다. 하드코딩 제거 목적.
    "performance": {
        "max_concurrency": 12,        # 1~32, 동시 처리 Gap 수 (asyncio.Semaphore)
        "max_gaps_per_cycle": 200,    # 50~2000, 사이클당 최대 Gap 수
        "max_pages_per_gap": 100,     # 10~500, Gap당 REST 페이지 순회 한도
        # ── REST 수집기 / 글로벌 Rate Limiter (Upbit 안전마진 포함) ──
        "rest_max_concurrent": 8,     # 1~32, RestCandleCollector 동시 태스크 수
        "rest_rate_per_second": 9,    # 1~10, 초당 한도 (Upbit 10 - 안전마진)
        "rest_rate_per_minute": 550,  # 10~600, 분당 한도 (Upbit 600 - 안전마진)
    },
}

_INTERVAL_PRESET_TO_MINUTES: Dict[str, int] = {
    "1m": 1, "5m": 5, "10m": 10, "30m": 30, "60m": 60,
}
_INTERVAL_PRESET_IDX: Dict[str, int] = {
    "1m": 0, "5m": 1, "10m": 2, "30m": 3, "60m": 4,
}
_IDX_TO_INTERVAL_PRESET: Dict[int, str] = {v: k for k, v in _INTERVAL_PRESET_IDX.items()}


def _parse_interval_minutes(text: str, default: int = 5) -> int:
    """'5분', '5m', '5' 등 입력값을 분 단위 정수로 파싱합니다."""
    try:
        s = str(text or "").strip().lower()
        m = re.search(r"\d+", s)
        if m:
            return max(1, int(m.group(0)))
    except Exception:
        pass
    return max(1, int(default))

# 데이터 용량 프리셋 버튼명 → preset 키 매핑
_VOLUME_PRESET_BUTTON_MAP: Dict[str, str] = {
    "btn_volume_preset_light": "light",
    "btn_volume_preset_balance": "balance",
    "btn_volume_preset_heavy": "heavy",
}
_TF_KEYS = ("1m", "5m", "15m", "1h", "4h", "1d")
_VOLUME_PRESET_ORDER = ("light", "balance", "heavy")

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QDate, Qt, QTimer, pyqtSignal
    from PyQt5.QtWidgets import QComboBox, QDialog, QLabel, QSpinBox

    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_UI_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "backfill_scheduler_settings_dialog.ui",
)


def _today_qdate():
    """오늘 날짜를 QDate로 반환."""
    from PyQt5.QtCore import QDate
    return QDate.currentDate()


def _days_ago_qdate(days: int):
    """오늘 기준 N일 전 QDate."""
    from PyQt5.QtCore import QDate
    return QDate.currentDate().addDays(-days)


def _classify_error_reason(reason: str) -> str:
    """AutoBackfill 오류 사유를 분류합니다.

    Returns
    -------
    str
        오류 분류 문자열: 설정 누락 | DB 연결 실패 | 심볼 비어있음 | 워커 시작 실패 | 예외
    """
    if not reason:
        return "없음"
    r = reason.lower()
    if any(k in r for k in ("not_initialized", "초기화", "설정 누락", "config")):
        return "설정 누락"
    if any(k in r for k in ("db", "database", "connection", "연결", "timescale", "mongo", "redis")):
        return "DB 연결 실패"
    if any(k in r for k in ("symbol", "심볼", "종목", "empty", "비어")):
        return "심볼 비어있음"
    if any(k in r for k in ("thread", "worker", "스레드", "워커", "start failed", "시작 실패")):
        return "워커 시작 실패"
    return "예외"


if _HAS_QT:
    class BackfillSchedulerSettingsDialog(QDialog):
        """백필/스케줄러 설정 비모달 다이얼로그.

        Parameters
        ----------
        parent : QWidget, optional
        mongo_client : pymongo.MongoClient, optional
            None이면 JSON 파일 폴백 저장 사용.
        auto_controller : AutoController, optional
            설정 적용 시 컨트롤러에 interval/auto_run 등을 전파합니다.
        """

        # 설정 저장 완료 시그널 (외부 연동용)
        settings_saved = pyqtSignal(dict)

        def __init__(self, parent=None, mongo_client=None, auto_controller=None):
            super().__init__(parent)
            self.setWindowModality(Qt.NonModal)

            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[BFSettingsDlg] UI 파일 로드 실패: %s", exc)

            self._mongo_client = mongo_client
            self._auto_controller = auto_controller

            # 상태 폴링 타이머 (5초)
            self._status_timer = QTimer(self)
            self._status_timer.setInterval(5000)
            self._status_timer.timeout.connect(self._refresh_status_labels)

            self._connect_signals()
            self._ensure_custom_interval_input()
            self._configure_interval_input()
            self._load_and_apply_settings()
            self._configure_scheduler_only_ui()
            self._refresh_status_labels()
            self._status_timer.start()

        # ──────────────────────────────────────────────
        # 시그널 연결
        # ──────────────────────────────────────────────
        def _connect_signals(self) -> None:
            # 저장 / 기본값 / 닫기
            if hasattr(self, "btn_save"):
                self.btn_save.clicked.connect(self._on_save)
            if hasattr(self, "btn_reset_defaults"):
                self.btn_reset_defaults.clicked.connect(self._on_reset_defaults)
            if hasattr(self, "btn_close"):
                self.btn_close.clicked.connect(self.close)

        def _configure_interval_input(self) -> None:
            """스케줄러 주기를 콤보 선택 + 직접 입력 모두 지원하도록 설정합니다."""
            combo = getattr(self, "combo_interval", None)
            if combo is None:
                return
            combo.setEditable(True)
            combo.setInsertPolicy(QComboBox.NoInsert)
            combo.setToolTip(
                "예: 1분, 5분, 10분, 30분, 60분 또는 직접 입력(예: 2, 7, 45)"
            )
            spin = getattr(self, "spin_custom_interval", None)
            if spin is not None:
                combo.currentTextChanged.connect(
                    lambda text: spin.setValue(_parse_interval_minutes(text, spin.value()))
                )
                spin.valueChanged.connect(lambda value: combo.setEditText(f"{int(value)}분"))

        def _ensure_custom_interval_input(self) -> None:
            """UI 파일에 없는 경우에도 사용자가 직접 분 단위를 입력할 수 있는 필드를 추가합니다."""
            if getattr(self, "spin_custom_interval", None) is not None:
                return
            combo = getattr(self, "combo_interval", None)
            if combo is None:
                return
            layout = combo.parentWidget().layout() if combo.parentWidget() else None
            if layout is None:
                return
            label = QLabel("직접 입력(분):", self)
            spin = QSpinBox(self)
            spin.setObjectName("spin_custom_interval")
            spin.setRange(1, 1440)
            spin.setValue(5)
            spin.setMinimumWidth(80)
            spin.setToolTip("자동 실행 간격을 분 단위로 직접 입력합니다. 예: 2, 7, 45")
            # 마지막 stretch/spacer 앞에 라벨+입력칸을 넣어 기존 행 정렬을 유지합니다.
            insert_at = max(0, layout.count() - 1)
            layout.insertWidget(insert_at, label)
            layout.insertWidget(insert_at + 1, spin)
            self.spin_custom_interval = spin
        def _configure_scheduler_only_ui(self) -> None:
            """백필 창을 스케줄러/상태 전용으로 구성합니다."""
            role = getattr(self, "label_role_header", None)
            if role is not None:
                role.setText(
                    "【 백필 / 스케줄러 실행 창 】 자동 실행·주기·상태만 설정합니다.\n"
                    "※ 백필 실행 정책(수집 타임프레임/TF별 최대 캔들 수/압축·삭제/심볼 소스)은 "
                    "'수집 설정(상세)' SSOT를 따릅니다."
                )
                role.setToolTip(
                    "이 창에서는 실행/스케줄/상태만 관리합니다.\n"
                    "대상 심볼은 '스마트 스캐너 + AI/ML 선택 결과'를 고정 사용합니다.\n"
                    "수집 타임프레임/캔들 수 편집은 '수집 설정(상세)'에서만 가능합니다."
                )

            for group_name in ("groupBox_backfill", "groupBox_data_preset"):
                group = getattr(self, group_name, None)
                if group is not None:
                    group.setVisible(False)

        # ──────────────────────────────────────────────
        # 프리셋 버튼 핸들러
        # ──────────────────────────────────────────────
        def _on_preset_clicked(self) -> None:
            sender = self.sender()
            if sender is None:
                return
            name = sender.objectName()

            # 모든 프리셋 버튼 해제 후 해당 버튼만 체크
            for n in ("btn_preset_7d", "btn_preset_30d", "btn_preset_90d", "btn_preset_custom"):
                btn = getattr(self, n, None)
                if btn is not None:
                    btn.setChecked(btn.objectName() == name)

            days_map = {"btn_preset_7d": 7, "btn_preset_30d": 30, "btn_preset_90d": 90}
            days = days_map.get(name)

            date_start = getattr(self, "date_start", None)
            date_end = getattr(self, "date_end", None)
            if date_start is not None and date_end is not None:
                if days is not None:
                    date_start.setDate(_days_ago_qdate(days))
                    date_end.setDate(_today_qdate())
                # 사용자 지정이면 날짜 편집 가능 상태 유지 (이미 활성화됨)
                date_start.setEnabled(True)
                date_end.setEnabled(True)

        # ──────────────────────────────────────────────
        # 데이터 용량 프리셋 핸들러
        # ──────────────────────────────────────────────
        def _on_volume_preset_clicked(self) -> None:
            """데이터 용량 프리셋 버튼 클릭 — 각 타임프레임 스핀박스 자동 채움."""
            sender = self.sender()
            if sender is None:
                return
            name = sender.objectName()
            preset_key = _VOLUME_PRESET_BUTTON_MAP.get(name)
            if preset_key is None:
                return
            preset_values = _VOLUME_PRESETS.get(preset_key, {})
            # 기존 값과 비교해 바뀌는 스핀박스 목록 수집
            changed = []
            for tf_key in ("1m", "5m", "15m", "1h", "4h", "1d"):
                spin = getattr(self, f"spin_limit_{tf_key}", None)
                new_val = preset_values.get(f"limit_{tf_key}")
                if spin is not None and new_val is not None and spin.value() != new_val:
                    changed.append(tf_key)
            self._apply_volume_limits(preset_values)
            self._flash_preset_changed(changed, preset_key)
            logger.info("[BFSettingsDlg] 데이터 용량 프리셋 적용: %s (변경: %s)", preset_key, changed)

        def _flash_preset_changed(self, changed_tfs: list, preset_key: str) -> None:
            """프리셋 적용 시 변경된 스핀박스를 잠깐 노란 배경으로 강조합니다."""
            try:
                from PyQt5.QtCore import QTimer as _QT
                _PRESET_NAMES = {"light": "🟢 라이트", "balance": "🔵 밸런스", "heavy": "🔴 헤비"}
                preset_label = getattr(self, "label_volume_guide", None)
                if preset_label is not None:
                    tf_str = ", ".join(changed_tfs) if changed_tfs else "없음"
                    preset_label.setText(
                        f"✅ {_PRESET_NAMES.get(preset_key, preset_key)} 프리셋 적용됨. "
                        f"변경된 타임프레임: {tf_str}\n"
                        "💡 프리셋 선택 후 각 값을 직접 수정할 수 있습니다."
                    )
                    preset_label.setStyleSheet("color: #1B5E20; font-size: 9pt;")
                    _QT.singleShot(4000, self._restore_volume_guide_label)
                # 변경된 스핀박스를 잠깐 강조
                for tf_key in changed_tfs:
                    spin = getattr(self, f"spin_limit_{tf_key}", None)
                    if spin is not None:
                        spin.setStyleSheet("background-color: #FFF9C4;")
                        _QT.singleShot(3000, lambda s=spin: self._restore_spin_style(s))
            except Exception as exc:
                logger.debug("[BFSettingsDlg] 프리셋 강조 실패: %s", exc)

        def _restore_volume_guide_label(self) -> None:
            """볼륨 프리셋 안내 레이블을 원래 스타일로 복원합니다."""
            try:
                preset_label = getattr(self, "label_volume_guide", None)
                if preset_label is not None:
                    preset_label.setText(
                        "💡 수집 설정(상세)에서 저장된 타임프레임별 최대 캔들 수를 읽기 전용으로 표시합니다. "
                        "값이 클수록 디스크 사용량과 초기 수집 시간이 증가합니다."
                    )
                    preset_label.setStyleSheet("color: #555; font-size: 9pt;")
            except Exception:
                pass

        @staticmethod
        def _restore_spin_style(spin) -> None:
            """스핀박스 스타일을 원래대로 복원합니다."""
            try:
                spin.setStyleSheet("")
            except Exception:
                pass

        def _apply_volume_limits(self, limits: Dict[str, int]) -> None:
            """타임프레임별 최대 캔들 수 스핀박스에 값을 적용합니다."""
            for tf_key in _TF_KEYS:
                spin = getattr(self, f"spin_limit_{tf_key}", None)
                if spin is not None:
                    val = limits.get(f"limit_{tf_key}")
                    if val is not None:
                        spin.setValue(int(val))

        def _on_volume_preset_combo_changed(self, idx: int) -> None:
            if not (0 <= idx < len(_VOLUME_PRESET_ORDER)):
                return
            self._apply_volume_limits(_VOLUME_PRESETS[_VOLUME_PRESET_ORDER[idx]])

        def _load_collection_policy(self) -> Dict[str, Any]:
            """SSOT: collection_settings에서 타임프레임/캔들 한도 정책을 로드."""
            try:
                if self._mongo_client is not None:
                    db = self._mongo_client["upbit_trader"]
                    doc = db.ui_settings.find_one({"user_id": "default"}) or {}
                    if isinstance(doc.get("collection_settings"), dict):
                        return doc.get("collection_settings", {})
            except Exception as exc:
                logger.debug("[BFSettingsDlg] collection_settings MongoDB 로드 실패: %s", exc)
            return {}

        def _resolve_policy_from_ssot(self, bf: Dict[str, Any]) -> Dict[str, Any]:
            col = self._load_collection_policy()
            active_tfs = col.get("timeframes", [])
            if not isinstance(active_tfs, list) or not active_tfs:
                active_tfs = bf.get("timeframes", ["1m", "5m", "1h"])
            resolved = {"timeframes": list(active_tfs)}
            preset = col.get("volume_preset", "light")
            if preset not in _VOLUME_PRESETS:
                preset = "light"
            resolved["volume_preset"] = preset
            for tf_key in _TF_KEYS:
                default_limit = _VOLUME_PRESETS[preset].get(f"limit_{tf_key}", _VOLUME_PRESETS["light"][f"limit_{tf_key}"])
                resolved[f"limit_{tf_key}"] = int(col.get(f"limit_{tf_key}", bf.get(f"limit_{tf_key}", default_limit)))
            return resolved

        def _apply_read_only_policy_summary(self, bf: Dict[str, Any]) -> None:
            policy = self._resolve_policy_from_ssot(bf)
            active_tfs = set(policy.get("timeframes", []))
            for tf in _TF_KEYS:
                chk = getattr(self, f"chk_bf_tf_{tf}", None)
                if chk is not None:
                    chk.setChecked(tf in active_tfs)
                    chk.setEnabled(False)
            for tf_key in _TF_KEYS:
                spin = getattr(self, f"spin_limit_{tf_key}", None)
                if spin is not None:
                    spin.setValue(int(policy[f"limit_{tf_key}"]))
                    spin.setEnabled(False)
            for btn_name in _VOLUME_PRESET_BUTTON_MAP:
                btn = getattr(self, btn_name, None)
                if btn is not None:
                    btn.setEnabled(False)
            combo = getattr(self, "combo_volume_preset", None)
            if combo is not None:
                try:
                    combo.setCurrentIndex(_VOLUME_PRESET_ORDER.index(policy["volume_preset"]))
                except ValueError:
                    combo.setCurrentIndex(0)
                combo.setEnabled(False)
            label_tf_note = getattr(self, "label_tf_note", None)
            if label_tf_note is not None:
                label_tf_note.setText(
                    "※ 백필 타임프레임/타임프레임별 최대 캔들 수는 '수집 설정(상세)'에서만 편집합니다. "
                    "이 창은 실행 시 적용될 정책을 읽기 전용으로 보여줍니다."
                )

        # ──────────────────────────────────────────────
        # 저장
        # ──────────────────────────────────────────────
        def _on_save(self) -> None:
            settings = self.collect_settings()
            self._persist_settings(settings)
            self._apply_to_controller(settings)
            # 백필 성능 SSOT 캐시 무효화 → 다음 사이클에서 즉시 새 값 사용
            # (14_orchestrator 패키지명이 숫자 시작이라 일반 import 불가 → 파일 기반 동적 로드)
            try:
                import importlib.util
                import pathlib
                import sys as _sys
                _here = pathlib.Path(__file__).resolve()
                _src_root = _here.parents[3]  # src/
                _ps_path = _src_root / "14_orchestrator" / "backfill" / "performance_settings.py"
                _mod_name = "_perf_settings_dlg_invalidate"
                _mod = _sys.modules.get(_mod_name)
                if _mod is None and _ps_path.exists():
                    _spec = importlib.util.spec_from_file_location(_mod_name, str(_ps_path))
                    if _spec and _spec.loader:
                        _mod = importlib.util.module_from_spec(_spec)
                        _sys.modules[_mod_name] = _mod
                        _spec.loader.exec_module(_mod)
                if _mod is not None and hasattr(_mod, "invalidate_cache"):
                    _mod.invalidate_cache()
            except Exception as _exc:
                logger.debug("[BFSettingsDlg] 성능 캐시 무효화 실패: %s", _exc)
            self.settings_saved.emit(settings)
            logger.info("[BFSettingsDlg] 설정 저장 완료 (성능 섹션 포함)")

        def _on_reset_defaults(self) -> None:
            import copy
            self._apply_settings_to_ui(copy.deepcopy(_DEFAULTS))

        # ──────────────────────────────────────────────
        # UI → dict 수집
        # ──────────────────────────────────────────────
        def collect_settings(self) -> Dict[str, Any]:
            """현재 UI 상태를 dict로 수집합니다."""
            bf: Dict[str, Any] = {}
            sched: Dict[str, Any] = {}

            # ── 타임프레임/캔들 한도 (SSOT: 수집 설정 상세)
            policy = self._resolve_policy_from_ssot(bf)
            bf["timeframes"] = list(policy.get("timeframes", ["1m", "5m", "1h"]))
            bf["symbol_source"] = "smart_scanner_aiml"
            bf["symbol_range"] = "selected"

            # ── 타임프레임별 최대 캔들 수 (SSOT 반영 결과 저장)
            for tf_key in _TF_KEYS:
                bf[f"limit_{tf_key}"] = int(policy.get(f"limit_{tf_key}", _DEFAULTS["backfill"].get(f"limit_{tf_key}", 0)))

            # ── 스케줄러
            chk_auto = getattr(self, "chk_auto_run", None)
            sched["auto_run"] = bool(chk_auto.isChecked()) if chk_auto else False

            combo_int = getattr(self, "combo_interval", None)
            spin_custom = getattr(self, "spin_custom_interval", None)
            if spin_custom is not None:
                mins = int(spin_custom.value())
            elif combo_int is not None:
                mins = _parse_interval_minutes(combo_int.currentText(), default=5)
            else:
                mins = 5
            preset = f"{mins}m" if mins in _INTERVAL_PRESET_TO_MINUTES.values() else "custom"
            sched["interval_preset"] = preset
            sched["custom_interval"] = int(mins)

            chk_start = getattr(self, "chk_auto_start_on_launch", None)
            sched["auto_start"] = bool(chk_start.isChecked()) if chk_start else False

            chk_kick = getattr(self, "chk_kickoff_on_enable", None)
            sched["kickoff_on_enable"] = bool(chk_kick.isChecked()) if chk_kick else True

            combo_cp = getattr(self, "combo_concurrent_policy", None)
            cp_idx = combo_cp.currentIndex() if combo_cp else 0
            sched["concurrent_policy"] = "rerun" if cp_idx == 1 else "skip"

            # ── ⚡ 성능(고급): 하드코딩되었던 백필 튜닝 파라미터를 UI에서 수집
            perf: Dict[str, Any] = {}
            spin_conc = getattr(self, "spin_perf_max_concurrency", None)
            if spin_conc is not None:
                perf["max_concurrency"] = max(1, min(32, int(spin_conc.value())))
            else:
                perf["max_concurrency"] = _DEFAULTS["performance"]["max_concurrency"]
            spin_gpc = getattr(self, "spin_perf_max_gaps_per_cycle", None)
            if spin_gpc is not None:
                perf["max_gaps_per_cycle"] = max(50, min(2000, int(spin_gpc.value())))
            else:
                perf["max_gaps_per_cycle"] = _DEFAULTS["performance"]["max_gaps_per_cycle"]
            spin_mpg = getattr(self, "spin_perf_max_pages_per_gap", None)
            if spin_mpg is not None:
                perf["max_pages_per_gap"] = max(10, min(500, int(spin_mpg.value())))
            else:
                perf["max_pages_per_gap"] = _DEFAULTS["performance"]["max_pages_per_gap"]

            # ── REST 수집기 / Rate Limiter SSOT (UI 위젯이 없으면 기본값 유지) ──
            spin_rmc = getattr(self, "spin_perf_rest_max_concurrent", None)
            if spin_rmc is not None:
                perf["rest_max_concurrent"] = max(1, min(32, int(spin_rmc.value())))
            else:
                perf["rest_max_concurrent"] = _DEFAULTS["performance"]["rest_max_concurrent"]
            spin_rps = getattr(self, "spin_perf_rest_rate_per_second", None)
            if spin_rps is not None:
                perf["rest_rate_per_second"] = max(1, min(10, int(spin_rps.value())))
            else:
                perf["rest_rate_per_second"] = _DEFAULTS["performance"]["rest_rate_per_second"]
            spin_rpm = getattr(self, "spin_perf_rest_rate_per_minute", None)
            if spin_rpm is not None:
                perf["rest_rate_per_minute"] = max(10, min(600, int(spin_rpm.value())))
            else:
                perf["rest_rate_per_minute"] = _DEFAULTS["performance"]["rest_rate_per_minute"]

            return {"backfill": bf, "scheduler": sched, "performance": perf}

        # ──────────────────────────────────────────────
        # dict → UI 적용
        # ──────────────────────────────────────────────
        def _apply_settings_to_ui(self, settings: Dict[str, Any]) -> None:
            bf = settings.get("backfill", {})
            sched = settings.get("scheduler", {})

            # ── 타임프레임
            active_tfs = set(bf.get("timeframes", ["1m", "5m", "1h"]))
            for tf in ("1m", "5m", "15m", "1h", "4h", "1d"):
                chk = getattr(self, f"chk_bf_tf_{tf}", None)
                if chk is not None:
                    chk.setChecked(tf in active_tfs)

            # ── 타임프레임별 최대 캔들 수
            for tf_key in ("1m", "5m", "15m", "1h", "4h", "1d"):
                spin = getattr(self, f"spin_limit_{tf_key}", None)
                if spin is not None:
                    default_val = _DEFAULTS["backfill"].get(f"limit_{tf_key}", 0)
                    spin.setValue(int(bf.get(f"limit_{tf_key}", default_val)))

            # ── 스케줄러
            chk_auto = getattr(self, "chk_auto_run", None)
            if chk_auto is not None:
                chk_auto.setChecked(bool(sched.get("auto_run", False)))

            combo_int = getattr(self, "combo_interval", None)
            if combo_int is not None:
                ip = sched.get("interval_preset", "5m")
                custom_minutes = int(sched.get("custom_interval", _INTERVAL_PRESET_TO_MINUTES.get(ip, 5)))
                if ip in _INTERVAL_PRESET_IDX:
                    combo_int.setCurrentIndex(_INTERVAL_PRESET_IDX.get(ip, 1))
                    combo_int.setEditText(f"{_INTERVAL_PRESET_TO_MINUTES.get(ip, 5)}분")
                else:
                    combo_int.setCurrentIndex(-1)
                    combo_int.setEditText(f"{max(1, custom_minutes)}분")
            spin_custom = getattr(self, "spin_custom_interval", None)
            if spin_custom is not None:
                spin_custom.setValue(max(1, custom_minutes))

            chk_start = getattr(self, "chk_auto_start_on_launch", None)
            if chk_start is not None:
                chk_start.setChecked(bool(sched.get("auto_start", False)))

            chk_kick = getattr(self, "chk_kickoff_on_enable", None)
            if chk_kick is not None:
                chk_kick.setChecked(bool(sched.get("kickoff_on_enable", True)))

            combo_cp = getattr(self, "combo_concurrent_policy", None)
            if combo_cp is not None:
                combo_cp.setCurrentIndex(1 if sched.get("concurrent_policy", "skip") == "rerun" else 0)

            # ── ⚡ 성능(고급): 저장된 값을 UI 스핀박스에 반영
            perf = settings.get("performance", {}) or {}
            perf_defaults = _DEFAULTS.get("performance", {})
            spin_conc = getattr(self, "spin_perf_max_concurrency", None)
            if spin_conc is not None:
                spin_conc.setValue(int(perf.get("max_concurrency", perf_defaults.get("max_concurrency", 12))))
            spin_gpc = getattr(self, "spin_perf_max_gaps_per_cycle", None)
            if spin_gpc is not None:
                spin_gpc.setValue(int(perf.get("max_gaps_per_cycle", perf_defaults.get("max_gaps_per_cycle", 200))))
            spin_mpg = getattr(self, "spin_perf_max_pages_per_gap", None)
            if spin_mpg is not None:
                spin_mpg.setValue(int(perf.get("max_pages_per_gap", perf_defaults.get("max_pages_per_gap", 100))))

            # ── REST 수집기 / Rate Limiter UI 반영 (위젯 미존재 시 무시)
            spin_rmc = getattr(self, "spin_perf_rest_max_concurrent", None)
            if spin_rmc is not None:
                spin_rmc.setValue(int(perf.get("rest_max_concurrent", perf_defaults.get("rest_max_concurrent", 8))))
            spin_rps = getattr(self, "spin_perf_rest_rate_per_second", None)
            if spin_rps is not None:
                spin_rps.setValue(int(perf.get("rest_rate_per_second", perf_defaults.get("rest_rate_per_second", 9))))
            spin_rpm = getattr(self, "spin_perf_rest_rate_per_minute", None)
            if spin_rpm is not None:
                spin_rpm.setValue(int(perf.get("rest_rate_per_minute", perf_defaults.get("rest_rate_per_minute", 550))))

            self._apply_read_only_policy_summary(bf)

        # ──────────────────────────────────────────────
        # 설정 로드 및 적용
        # ──────────────────────────────────────────────
        def _load_and_apply_settings(self) -> None:
            import copy
            saved = self._load_settings()
            merged = copy.deepcopy(_DEFAULTS)
            if saved:
                for section in ("backfill", "scheduler", "performance"):
                    if section in saved and isinstance(saved[section], dict):
                        merged.setdefault(section, {}).update(saved[section])
            self._apply_settings_to_ui(merged)

        # ──────────────────────────────────────────────
        # 영속 저장 (MongoDB → JSON 폴백)
        # ──────────────────────────────────────────────
        def _persist_settings(self, settings: Dict[str, Any]) -> None:
            def _save() -> None:
                if self._mongo_client is not None:
                    self._save_to_mongo(settings)
                else:
                    self._save_to_json(settings)
            threading.Thread(target=_save, daemon=True).start()

        def _save_to_mongo(self, settings: Dict[str, Any]) -> None:
            try:
                db = self._mongo_client["upbit_trader"]
                db.ui_settings.update_one(
                    {"user_id": "default"},
                    {
                        "$set": {
                            "backfill_scheduler": {
                                **settings,
                                "updated_at": datetime.now(timezone.utc),
                            },
                            "auto_backfill.auto_enabled": bool(settings.get("scheduler", {}).get("auto_run", False)),
                            "auto_backfill.interval_seconds": int(
                                (
                                    _INTERVAL_PRESET_TO_MINUTES.get(
                                        settings.get("scheduler", {}).get("interval_preset", "5m"),
                                        int(settings.get("scheduler", {}).get("custom_interval", 5)),
                                    )
                                ) * 60
                            ),
                            "auto_backfill.updated_at": datetime.now(timezone.utc),
                        }
                    },
                    upsert=True,
                )
                logger.debug("[BFSettingsDlg] MongoDB 저장 완료")
            except Exception as exc:
                logger.warning("[BFSettingsDlg] MongoDB 저장 실패, JSON 폴백: %s", exc)
                self._save_to_json(settings)

        def _save_to_json(self, settings: Dict[str, Any]) -> None:
            try:
                os.makedirs(os.path.dirname(_JSON_FALLBACK_PATH), exist_ok=True)
                payload = {**settings, "updated_at": datetime.now().isoformat()}
                with open(_JSON_FALLBACK_PATH, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                logger.debug("[BFSettingsDlg] JSON 저장 완료: %s", _JSON_FALLBACK_PATH)
            except Exception as exc:
                logger.warning("[BFSettingsDlg] JSON 저장 실패: %s", exc)

        # ──────────────────────────────────────────────
        # 설정 로드 (MongoDB → JSON 폴백)
        # ──────────────────────────────────────────────
        def _load_settings(self) -> Optional[Dict[str, Any]]:
            if self._mongo_client is not None:
                doc = self._load_from_mongo()
                if doc is not None:
                    return doc
            return self._load_from_json()

        def _load_from_mongo(self) -> Optional[Dict[str, Any]]:
            try:
                db = self._mongo_client["upbit_trader"]
                doc = db.ui_settings.find_one({"user_id": "default"})
                if doc:
                    return doc.get("backfill_scheduler")
                return None
            except Exception as exc:
                logger.debug("[BFSettingsDlg] MongoDB 로드 실패: %s", exc)
                return None

        def _load_from_json(self) -> Optional[Dict[str, Any]]:
            try:
                if os.path.exists(_JSON_FALLBACK_PATH):
                    with open(_JSON_FALLBACK_PATH, "r", encoding="utf-8") as f:
                        return json.load(f)
            except Exception as exc:
                logger.debug("[BFSettingsDlg] JSON 로드 실패: %s", exc)
            return None

        # ──────────────────────────────────────────────
        # AutoController에 설정 전파
        # ──────────────────────────────────────────────
        def _apply_to_controller(self, settings: Dict[str, Any]) -> None:
            ctrl = self._auto_controller
            if ctrl is None:
                return
            sched = settings.get("scheduler", {})
            auto_run = bool(sched.get("auto_run", False))
            ip = sched.get("interval_preset", "5m")
            interval_minutes = _INTERVAL_PRESET_TO_MINUTES.get(ip, int(sched.get("custom_interval", 5)))
            interval_seconds = interval_minutes * 60

            try:
                if auto_run:
                    # start_background_detection handles kickoff + periodic scheduling.
                    # When kickoff_on_enable is False, we still call it — the kickoff
                    # is immediate but lightweight (non-blocking). This avoids direct
                    # access to private controller attributes.
                    ctrl.start_background_detection(
                        interval_seconds,
                        kickoff=bool(sched.get("kickoff_on_enable", True)),
                    )
                else:
                    ctrl.stop_background_detection()
            except Exception as exc:
                logger.warning("[BFSettingsDlg] AutoController 전파 실패: %s", exc)

        # ──────────────────────────────────────────────
        # 상태 레이블 갱신
        # ──────────────────────────────────────────────
        def _refresh_status_labels(self) -> None:
            ctrl = self._auto_controller
            engine_text = "초기화 전"
            engine_color = "#9E9E9E"
            sched_text = "비활성"
            sched_color = "#9E9E9E"
            last_run_text = "마지막 실행: --"
            next_run_text = "다음 실행 예정: --"

            if ctrl is not None:
                try:
                    status = ctrl.get_status()
                    automatic = bool(status.get("automatic", False))
                    interval_sec = int(status.get("interval_seconds", 300))
                    last_run_time_str = str(status.get("last_run_time", ""))
                    last_run_ok = bool(status.get("last_run_ok", False))

                    # Derive engine state from public get_status() first,
                    # then fall back to semi-public mgr attributes (same pattern as collection_tab.py)
                    queue_len = int(status.get("queue_length", 0))
                    mgr = getattr(ctrl, "_mgr", None)
                    if mgr is not None:
                        running = getattr(mgr, "_running", False)
                        waiting = getattr(mgr, "_waiting", False)
                        if running:
                            engine_text = "탐지/실행 중"
                            engine_color = "#2196F3"
                        elif waiting:
                            engine_text = "심볼 대기 중"
                            engine_color = "#FF9800"
                        else:
                            result = getattr(mgr, "last_start_result", None)
                            if result is not None:
                                from ..tabs.collection_tab import _RESULT_KO
                                code = getattr(result, "value", str(result))
                                engine_text = _RESULT_KO.get(code, code)
                                engine_color = "#4CAF50" if code == "STARTED" else (
                                    "#F44336" if "FAIL" in code else "#9E9E9E"
                                )
                    elif queue_len > 0:
                        engine_text = "처리 대기 중"
                        engine_color = "#FF9800"

                    if automatic:
                        sched_text = f"활성 ({interval_sec // 60}분 주기)"
                        sched_color = "#4CAF50"
                    else:
                        sched_text = "비활성 (수동)"
                        sched_color = "#9E9E9E"

                    if last_run_time_str:
                        try:
                            dt = datetime.fromisoformat(last_run_time_str)
                            ts = dt.strftime("%m-%d %H:%M:%S")
                        except Exception:
                            ts = last_run_time_str[:19]
                        ok_str = "성공" if last_run_ok else "실패"
                        last_run_text = f"마지막 실행: {ts} [{ok_str}]"

                    if automatic:
                        next_run_text = f"다음 실행 예정: {interval_sec}초 주기 자동"
                except Exception as exc:
                    logger.debug("[BFSettingsDlg] 상태 조회 실패: %s", exc)

            lbl_eng = getattr(self, "label_engine_status", None)
            if lbl_eng is not None:
                lbl_eng.setText(engine_text)
                lbl_eng.setStyleSheet(f"color: {engine_color}; font-weight: bold;")

            lbl_sched = getattr(self, "label_scheduler_status", None)
            if lbl_sched is not None:
                lbl_sched.setText(sched_text)
                lbl_sched.setStyleSheet(f"color: {sched_color}; font-weight: bold;")

            lbl_last = getattr(self, "label_last_run_time", None)
            if lbl_last is not None:
                lbl_last.setText(last_run_text)

            lbl_next = getattr(self, "label_next_run_time", None)
            if lbl_next is not None:
                lbl_next.setText(next_run_text)

            # ── 오류 사유 표시 (분류 포함)
            error_reason = ""
            if ctrl is not None:
                mgr = getattr(ctrl, "_mgr", None)
                if mgr is not None:
                    error_reason = getattr(mgr, "last_error_reason", "")
            lbl_error = getattr(self, "label_last_error", None)
            if lbl_error is not None:
                if error_reason:
                    category = _classify_error_reason(error_reason)
                    lbl_error.setText(f"오류 사유 [{category}]: {error_reason}")
                    lbl_error.setStyleSheet("color: #D32F2F;")
                    lbl_error.setToolTip(
                        f"분류: {category}\n원인: {error_reason}\n\n"
                        "해결 방법:\n"
                        "  설정 누락 → 저장 버튼 클릭 후 자동 실행 ON\n"
                        "  DB 연결 실패 → DB 서비스 상태 확인\n"
                        "  심볼 비어있음 → 스캐너/AI-ML 탭에서 심볼 선택\n"
                        "  워커 시작 실패 → 앱 재시작"
                    )
                else:
                    lbl_error.setText("오류 사유: 없음 (정상)")
                    lbl_error.setStyleSheet("color: #757575;")
                    lbl_error.setToolTip("")

        # ──────────────────────────────────────────────
        # 공개 API
        # ──────────────────────────────────────────────
        def set_auto_controller(self, ctrl) -> None:
            """AutoController를 나중에 주입합니다."""
            self._auto_controller = ctrl

        def set_mongo_client(self, mongo_client) -> None:
            """MongoDB 클라이언트를 나중에 주입합니다."""
            self._mongo_client = mongo_client

        def get_interval_seconds(self) -> int:
            """현재 설정된 스케줄러 주기(초)를 반환합니다."""
            settings = self.collect_settings()
            sched = settings.get("scheduler", {})
            ip = sched.get("interval_preset", "5m")
            return _INTERVAL_PRESET_TO_MINUTES.get(ip, int(sched.get("custom_interval", 5))) * 60

        def closeEvent(self, event) -> None:
            self._status_timer.stop()
            super().closeEvent(event)

else:
    class BackfillSchedulerSettingsDialog:  # type: ignore[no-redef]
        """PyQt5 미설치 시 더미 클래스"""

        def __init__(self, parent=None, mongo_client=None, auto_controller=None):
            pass

        def set_auto_controller(self, ctrl) -> None:
            pass

        def set_mongo_client(self, mongo_client) -> None:
            pass

        def show(self) -> None:
            pass

        def isVisible(self) -> bool:
            return False

        def activateWindow(self) -> None:
            pass
