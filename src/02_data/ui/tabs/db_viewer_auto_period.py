# -*- coding: utf-8 -*-
"""
DB 데이터 뷰어 — 백필 검증 자동 기간 계산 Mixin

DBViewerAutoPeriodMixin
    - 사용자 요구: "DB데이터 탭에 과거데이터 검증을 각 타임 프레임 선택하면
      수집설정에 선택된 캔들수 만큼 계산해서 기간 설정이 자동화 되도록 해주세요.
      그후 사용자가 선택해서 변경 가능하게 해주구요."
    - 구현 방식
        1) MongoDB `ui_settings.collection_settings.limit_{tf}` 에서 캔들 수 한도 조회
        2) `lookback_days = ceil(candles * tf_minutes / 1440)` (상한 10년)
        3) `edit_verify_start / edit_verify_end` QDateEdit 자동 설정
        4) 사용자 직접 변경은 그대로 허용 (콜백은 TF 변경 시에만 트리거)

이 Mixin 은 DBViewerLogicMixin 와 함께 DBDataViewerTab 에 적용된다.
SRP: 자동 기간 계산만 담당 (UI 위젯 갱신 + Mongo 조회).
"""
from __future__ import annotations

import logging
import math
import os
from typing import Dict

logger = logging.getLogger(__name__)


class DBViewerAutoPeriodMixin:
    """백필 검증 — 타임프레임별 자동 기간 계산"""

    # GapFinder._DEFAULT_COLLECTION_POLICY 와 동일한 보수적 fallback
    # (수집설정이 없거나 MongoDB 미연결 시 사용)
    _VERIFY_DEFAULT_LIMITS: Dict[str, int] = {
        "1m": 150000,
        "3m": 60000,
        "5m": 50000,
        "15m": 30000,
        "30m": 20000,
        "1h": 12000,
        "4h": 5000,
        "1d": 500,
    }

    _VERIFY_TF_MINUTES: Dict[str, int] = {
        "1m": 1,
        "3m": 3,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
    }

    # 너무 먼 과거(>10년)는 의미가 없으므로 상한
    _VERIFY_MAX_LOOKBACK_DAYS: int = 3650

    # ------------------------------------------------------------------
    # 데이터 조회
    # ------------------------------------------------------------------

    def _load_collection_limit_for_tf(self, timeframe: str) -> int:
        """수집설정에서 해당 timeframe 의 캔들 수 한도(limit_{tf})를 읽어온다.

        우선순위:
          1) MongoDB `ui_settings.collection_settings.limit_{tf}`
          2) 클래스 기본값 `_VERIFY_DEFAULT_LIMITS`

        DB 미연결 등 실패 시 기본값을 반환한다 (UI 가 멈추지 않도록 best-effort).
        """
        tf = str(timeframe)
        default = int(self._VERIFY_DEFAULT_LIMITS.get(tf, 0) or 0)
        try:
            from pymongo import MongoClient  # type: ignore

            mongo_uri = os.getenv(
                "MONGO_URI", "mongodb://localhost:27017/upbit_trader"
            )
            client = MongoClient(
                mongo_uri,
                serverSelectionTimeoutMS=2000,
                directConnection=True,
            )
            try:
                db_name = mongo_uri.rstrip("/").rsplit("/", 1)[-1] or "upbit_trader"
                doc = (
                    client[db_name]["ui_settings"].find_one({"user_id": "default"})
                    or {}
                )
                col = doc.get("collection_settings", {}) or {}
                if isinstance(col, dict):
                    key = f"limit_{tf}"
                    raw = col.get(key)
                    if raw is not None:
                        try:
                            v = int(raw)
                            if v > 0:
                                return v
                        except Exception:
                            pass
            finally:
                try:
                    client.close()
                except Exception:
                    pass
        except Exception as exc:
            logger.debug(
                "[DBViewerAutoPeriod] collection_settings 로드 실패(%s): %s",
                tf,
                exc,
            )
        return default

    # ------------------------------------------------------------------
    # 계산
    # ------------------------------------------------------------------

    def _compute_lookback_days_for_tf(self, timeframe: str, candles: int) -> int:
        """캔들 수와 타임프레임 분 단위를 조합해 lookback 일수를 계산한다.

        days = ceil(candles * tf_minutes / 1440)
        상한: _VERIFY_MAX_LOOKBACK_DAYS (10년)
        하한: 1일
        """
        tf_min = int(self._VERIFY_TF_MINUTES.get(str(timeframe), 1) or 1)
        try:
            c = max(1, int(candles))
        except Exception:
            c = 1
        days = int(math.ceil((c * tf_min) / 1440.0))
        return max(1, min(days, self._VERIFY_MAX_LOOKBACK_DAYS))

    # ------------------------------------------------------------------
    # UI 적용
    # ------------------------------------------------------------------

    def _apply_auto_verify_period_for_tf(self, timeframe: str) -> None:
        """선택된 타임프레임 기준으로 시작/종료 QDate 위젯을 자동 설정한다.

        - 종료일 = 오늘
        - 시작일 = 종료일 - lookback_days
        - 사용자가 이후 달력 위젯에서 자유롭게 수정 가능 (단순 setDate 만 호출)
        """
        try:
            from PyQt5.QtCore import QDate  # type: ignore
        except Exception:
            return
        edit_start = getattr(self, "edit_verify_start", None)
        edit_end = getattr(self, "edit_verify_end", None)
        if edit_start is None or edit_end is None:
            return
        try:
            candles = self._load_collection_limit_for_tf(timeframe)
            days = self._compute_lookback_days_for_tf(timeframe, candles)
            today = QDate.currentDate()
            start = today.addDays(-int(days))
            if hasattr(edit_end, "setDate"):
                edit_end.setDate(today)
            if hasattr(edit_start, "setDate"):
                edit_start.setDate(start)
            # 진단용 상태 라벨이 있으면 계산 근거 안내
            lbl = getattr(self, "label_verify_status", None)
            if lbl is not None:
                try:
                    lbl.setText(
                        f"상태: 자동 기간 적용 ({timeframe}, "
                        f"{candles:,}봉 ≈ {days}일)"
                    )
                    lbl.setStyleSheet("font-weight: bold; color: #607D8B;")
                except Exception:
                    pass
            logger.info(
                "[DBViewerAutoPeriod] 자동 기간 적용 tf=%s candles=%d days=%d",
                timeframe,
                candles,
                days,
            )
        except Exception as exc:
            logger.debug(
                "[DBViewerAutoPeriod] _apply_auto_verify_period_for_tf 실패: %s",
                exc,
            )

    def _on_verify_tf_changed(self, timeframe: str) -> None:
        """타임프레임 콤보 변경 시 자동 기간 재계산 슬롯."""
        try:
            tf = (timeframe or "").strip()
            if not tf:
                return
            self._apply_auto_verify_period_for_tf(tf)
        except Exception as exc:
            logger.debug(
                "[DBViewerAutoPeriod] _on_verify_tf_changed 실패: %s", exc
            )
