# -*- coding: utf-8 -*-
"""
DB 뷰어 UI 갱신 Mixin (db_viewer_ui_updaters.py)

DBViewerUIUpdatersMixin:
  - 하단 요약 레이블 갱신
  - 저장 상태 배너 갱신 (색상 포함)
  - 숫자/시각 포매팅 헬퍼
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import QWidget
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

# 상태별 색상
_COLOR_SAVING   = "color: #27ae60"  # 초록 (저장 중)
_COLOR_COMPLETE = "color: #2980b9"  # 파랑 (저장 완료/대기)
_COLOR_WAITING  = "color: #f39c12"  # 주황 (대기/미연결)
_COLOR_ERROR    = "color: #e74c3c"  # 빨강

if _HAS_QT:
    class DBViewerUIUpdatersMixin:
        """DB 데이터 뷰어 UI 갱신 전담 Mixin.

        DBDataViewerTab 과 함께 사용합니다.
        self 는 QWidget 인스턴스여야 합니다.
        """

        # ------------------------------------------------------------------
        # 하단 요약
        # ------------------------------------------------------------------

        def update_summary(
            self,
            queried: int,
            candles: int,
            staging: int,
            isolated: int,
        ) -> None:
            """하단 요약 레이블을 갱신합니다.

            Args:
                queried: 이번 조회 건수
                candles: candles 테이블 총 건수 (-1 이면 N/A)
                staging: staging_candles 총 건수 (-1 이면 N/A)
                isolated: isolated_candles 총 건수 (-1 이면 N/A)
            """
            lbl = getattr(self, "label_summary", None)
            if lbl is None:
                return
            lbl.setText(
                f"총 조회: {queried:,}건  |  "
                f"Candles: {self._fmt_num(candles)}건  |  "
                f"Staging: {self._fmt_num(staging)}건  |  "
                f"Isolated: {self._fmt_num(isolated)}건"
            )

        # ------------------------------------------------------------------
        # 저장 상태 배너
        # ------------------------------------------------------------------

        def update_status_banner(
            self,
            candles: int,
            staging: int,
            isolated: int,
            rate: float = 0.0,
            last_save_time: Optional[datetime] = None,
        ) -> None:
            """저장 상태 배너 레이블을 갱신합니다.

            Args:
                candles: candles 테이블 총 건수
                staging: staging_candles 총 건수
                isolated: isolated_candles 총 건수
                rate: 저장 속도 (건/초)
                last_save_time: 최종 저장 시각
            """
            # 상태 판단
            if staging > 0:
                status_text = "저장 중"
                color = _COLOR_SAVING
            elif candles > 0:
                status_text = "저장 완료"
                color = _COLOR_COMPLETE
            else:
                status_text = "저장 대기 중"
                color = _COLOR_WAITING

            last_str = self._fmt_time(last_save_time) if last_save_time else "-"

            for attr, text in [
                ("label_status_text",    f"저장 상태: {status_text}"),
                ("label_candles_total",  f"Candles: {candles:,}"),
                ("label_staging_total",  f"Staging: {staging:,}"),
                ("label_isolated_total", f"Isolated: {isolated:,}"),
                ("label_save_rate",      f"저장 속도: {rate:.1f}/초"),
                ("label_last_save_time", f"최종 저장: {last_str}"),
            ]:
                lbl = getattr(self, attr, None)
                if lbl is not None:
                    lbl.setText(text)

            # 점 색상
            dot_lbl = getattr(self, "label_status_indicator", None)
            if dot_lbl is not None:
                dot_lbl.setStyleSheet(color)

        # ------------------------------------------------------------------
        # 조회 시간 표시
        # ------------------------------------------------------------------

        def update_query_time(self, elapsed_sec: float) -> None:
            """조회 소요 시간을 표시합니다."""
            lbl = getattr(self, "label_query_time", None)
            if lbl is not None:
                lbl.setText(f"조회 시간: {elapsed_sec:.2f}초")

        # ------------------------------------------------------------------
        # 포매팅 헬퍼
        # ------------------------------------------------------------------

        @staticmethod
        def _fmt_num(v: Any) -> str:
            """숫자를 포매팅합니다 (소수점 단위 가격 지원).

            Args:
                v: 숫자값 또는 None (-1 이면 N/A)

            Returns:
                포매팅된 문자열.
                1 이상 정수 → 천단위 구분자 (예: 1,234,567).
                1 이상 소수 → 소수점 8자리까지 trailing zero 제거.
                1 미만 소수(SHIB 등) → 소수점 10자리까지 trailing zero 제거.
                0 → "0", None → "N/A".
            """
            if v is None:
                return "N/A"
            try:
                fv = float(v)
                if fv < 0:
                    return "N/A"
                # 정수이면서 1 이상 → 천단위 구분
                if fv >= 1 and fv == int(fv):
                    return f"{int(fv):,}"
                # 1 이상이지만 소수점 있음
                if fv >= 1:
                    return f"{fv:,.8f}".rstrip("0").rstrip(".")
                # 정확히 0
                if fv == 0:
                    return "0"
                # 1 미만 소수 (SHIB 등) — 소수점 10자리까지 표시 후 trailing zero 제거
                return f"{fv:.10f}".rstrip("0").rstrip(".")
            except (TypeError, ValueError):
                return str(v)

        @staticmethod
        def _fmt_time(dt: Any) -> str:
            """datetime 을 'MM-DD HH:MM:SS' 형식으로 포매팅합니다.

            Args:
                dt: datetime 객체 또는 None

            Returns:
                포매팅된 시각 문자열
            """
            if dt is None:
                return "-"
            try:
                if isinstance(dt, datetime):
                    return dt.strftime("%m-%d %H:%M:%S")
                return str(dt)
            except Exception:
                return str(dt)

else:
    class DBViewerUIUpdatersMixin:  # type: ignore[no-redef]
        """PyQt5 미설치 시 더미 Mixin."""

        def update_summary(self, *args: Any, **kwargs: Any) -> None:
            pass

        def update_status_banner(self, *args: Any, **kwargs: Any) -> None:
            pass

        def update_query_time(self, elapsed_sec: float) -> None:
            pass

        @staticmethod
        def _fmt_num(v: Any) -> str:
            return str(v) if v is not None else "N/A"

        @staticmethod
        def _fmt_time(dt: Any) -> str:
            return str(dt) if dt is not None else "-"
