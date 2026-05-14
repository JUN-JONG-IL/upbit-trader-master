# -*- coding: utf-8 -*-
"""
저장 상태 바 위젯 (storage_status_bar.py)

StorageStatusBar 위젯:
  - storage_status_bar.ui 파일 로드 (uic.loadUi)
  - 주기적으로 candles/staging/isolated 건수 갱신
  - 저장 상태에 따라 색상 코딩: 저장중(녹색)/대기(주황)/오류(빨강)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QWidget
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

# 상태별 색상
_COLOR_SAVING  = "color: #27ae60"   # 저장 중 (녹색)
_COLOR_WAITING = "color: #f39c12"   # 대기 (주황)
_COLOR_ERROR   = "color: #e74c3c"   # 오류 (빨강)

# UI 파일 경로 (이 파일과 동일 폴더)
_UI_PATH = Path(__file__).parent / "storage_status_bar.ui"

if _HAS_QT:
    class StorageStatusBar(QWidget):
        """저장 상태 배너 위젯.

        candle_queries 모듈을 통해 DB 카운트를 주기적으로 조회하고
        lbl_dot / lbl_status 등 레이블을 색상과 함께 갱신합니다.
        """

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            try:
                uic.loadUi(str(_UI_PATH), self)
                logger.debug("[StorageStatusBar] UI 파일 로드 성공: %s", _UI_PATH)
            except Exception as exc:
                logger.warning("[StorageStatusBar] UI 파일 로드 실패: %s — 폴백 UI 구성", exc)
                self._build_fallback_ui()

            self._timer = QTimer(self)
            self._timer.timeout.connect(self._refresh)

        # ------------------------------------------------------------------
        # 타이머 제어
        # ------------------------------------------------------------------

        def start_updates(self, interval_ms: int = 3000) -> None:
            """자동 갱신 타이머를 시작합니다."""
            self._timer.setInterval(max(1000, int(interval_ms)))
            if not self._timer.isActive():
                self._timer.start()
            # 즉시 한 번 갱신
            self._refresh()

        def stop_updates(self) -> None:
            """자동 갱신 타이머를 중지합니다."""
            if self._timer.isActive():
                self._timer.stop()

        # ------------------------------------------------------------------
        # 갱신 로직
        # ------------------------------------------------------------------

        def _refresh(self) -> None:
            """DB 카운트를 조회하고 레이블을 갱신합니다."""
            try:
                from ..utils.candle_queries import query_table_counts, get_save_rate_per_sec
                counts = query_table_counts()
                rate = get_save_rate_per_sec()
            except Exception as exc:
                logger.debug("[StorageStatusBar] 데이터 조회 실패: %s", exc)
                self._set_error_state()
                return

            candles  = counts.get("candles",  0)
            staging  = counts.get("staging",  0)
            isolated = counts.get("isolated", 0)
            last_dt  = counts.get("last_save_time")

            # 상태 판단
            if staging > 0:
                dot_text   = "●"
                status_txt = "저장 중"
                color      = _COLOR_SAVING
            elif candles > 0:
                dot_text   = "●"
                status_txt = "저장 완료"
                color      = _COLOR_WAITING
            else:
                dot_text   = "●"
                status_txt = "저장 대기 중"
                color      = _COLOR_WAITING

            # 최종 저장 시각 포맷
            if last_dt is not None:
                try:
                    last_str = last_dt.strftime("%m-%d %H:%M:%S")
                except Exception:
                    last_str = str(last_dt)
            else:
                last_str = "--"

            self._set_labels(
                dot_text, status_txt, color,
                candles, staging, isolated,
                rate, last_str,
            )

        def _set_labels(
            self,
            dot: str,
            status: str,
            color: str,
            candles: int,
            staging: int,
            isolated: int,
            rate: float,
            last_time: str,
        ) -> None:
            """레이블 값과 색상을 일괄 설정합니다."""
            for attr, text in [
                ("lbl_dot",       dot),
                ("lbl_status",    status),
                ("lbl_candles",   f"Candles: {candles:,}"),
                ("lbl_staging",   f"Staging: {staging:,}"),
                ("lbl_isolated",  f"Isolated: {isolated:,}"),
                ("lbl_rate",      f"저장 속도: {rate:.1f}/초"),
                ("lbl_last_time", f"최종 저장: {last_time}"),
            ]:
                lbl = getattr(self, attr, None)
                if lbl is not None:
                    lbl.setText(text)

            # 색상은 dot과 status에만 적용
            for attr in ("lbl_dot", "lbl_status"):
                lbl = getattr(self, attr, None)
                if lbl is not None:
                    lbl.setStyleSheet(color)

        def _set_error_state(self) -> None:
            """오류 상태로 레이블을 설정합니다."""
            self._set_labels(
                "●", "저장 오류", _COLOR_ERROR,
                0, 0, 0, 0.0, "--",
            )

        # ------------------------------------------------------------------
        # 폴백 UI (uic.loadUi 실패 시)
        # ------------------------------------------------------------------

        def _build_fallback_ui(self) -> None:
            """코드 기반 폴백 UI를 구성합니다."""
            from PyQt5.QtWidgets import QHBoxLayout, QLabel
            layout = QHBoxLayout(self)
            layout.setContentsMargins(4, 2, 4, 2)
            layout.setSpacing(8)
            for attr, text in [
                ("lbl_dot",       "●"),
                ("lbl_status",    "저장 대기 중"),
                ("lbl_candles",   "Candles: --"),
                ("lbl_staging",   "Staging: --"),
                ("lbl_isolated",  "Isolated: --"),
                ("lbl_rate",      "저장 속도: -- /초"),
                ("lbl_last_time", "최종 저장: --"),
            ]:
                lbl = QLabel(text, self)
                setattr(self, attr, lbl)
                layout.addWidget(lbl)
            layout.addStretch()

else:
    class StorageStatusBar:  # type: ignore[no-redef]
        """PyQt5 미설치 시 더미 클래스."""

        def __init__(self, parent=None) -> None:
            pass

        def start_updates(self, interval_ms: int = 3000) -> None:
            pass

        def stop_updates(self) -> None:
            pass
