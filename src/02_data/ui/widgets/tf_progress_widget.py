# -*- coding: utf-8 -*-
"""
TFProgressWidget — 타임프레임별 안정권 진행률 위젯 (Phase 4)

[책임]
    한 심볼에 대한 여러 타임프레임의 진행률(coverage_pct)과 상태(SAFE/SYNCING/
    STALE/UNKNOWN)을 한눈에 보여준다. 각 행:

        ┌─────┬──────────────────────────────┬───────┐
        │ 1m  │ ████████████████████████░░░░ │ SAFE  │
        │ 5m  │ █████████████░░░░░░░░░░░░░░░ │SYNCING│
        │ 1h  │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ STALE │
        └─────┴──────────────────────────────┴───────┘

[데이터 소스]
    ``MetadataManager.compute_safe_zone_pct(symbol, tf)`` 의 결과 dict.

[강조 표시]
    ``set_selected_timeframes(list)`` 로 전달된 TF 는 굵은 테두리/포인트 컬러로
    강조되며, 미선택 TF 는 옅은 음영으로 비활성 표시된다.

[비파괴]
    - 신규 위젯, 어떤 기존 화면에도 자동 도킹되지 않는다.
    - PyQt5 미설치 환경에서도 import 만 되도록 더미 클래스를 제공한다.

[사용 예]
    >>> w = TFProgressWidget(timeframes=["1m", "5m", "15m", "1h", "4h", "1d"])
    >>> w.set_selected_timeframes(["1m", "5m", "1h"])
    >>> w.update_from_results({
    ...     "1m": {"coverage_pct": 98.0, "status": "SAFE"},
    ...     "5m": {"coverage_pct": 60.0, "status": "SYNCING"},
    ... })
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import (
        QPropertyAnimation,
        Qt,
        pyqtProperty,
        pyqtSlot,
    )
    from PyQt5.QtGui import QColor
    from PyQt5.QtWidgets import (
        QGridLayout,
        QGroupBox,
        QLabel,
        QProgressBar,
        QVBoxLayout,
        QWidget,
    )
    _HAS_QT = True
except ImportError:  # pragma: no cover
    _HAS_QT = False
    logger.debug("[TFProgressWidget] PyQt5 없음 — 더미 클래스 사용")


_DEFAULT_TFS = ["1m", "5m", "15m", "1h", "4h", "1d"]

_STATUS_STYLES: Dict[str, Dict[str, str]] = {
    "SAFE":    {"bg": "#1f8b4c", "fg": "#ffffff", "text": "SAFE"},
    "SYNCING": {"bg": "#f1c40f", "fg": "#000000", "text": "SYNCING"},
    "STALE":   {"bg": "#c0392b", "fg": "#ffffff", "text": "STALE"},
    "UNKNOWN": {"bg": "#7f8c8d", "fg": "#ffffff", "text": "UNKNOWN"},
}


if _HAS_QT:

    class _StatusChip(QLabel):
        """SAFE/SYNCING/STALE 상태 칩 라벨."""

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self.setAlignment(Qt.AlignCenter)
            self.setMinimumWidth(76)
            self.setFixedHeight(20)
            self.set_status("UNKNOWN")

        def set_status(self, status: str) -> None:
            style = _STATUS_STYLES.get(str(status).upper(), _STATUS_STYLES["UNKNOWN"])
            self.setText(style["text"])
            self.setStyleSheet(
                f"background-color: {style['bg']};"
                f" color: {style['fg']};"
                f" border-radius: 8px;"
                f" font-weight: bold;"
                f" padding: 2px 6px;"
            )


    class TFProgressWidget(QWidget):
        """타임프레임별 진행률 + 상태칩 위젯.

        Args:
            timeframes: 표시할 타임프레임 리스트
            title: GroupBox 타이틀 (None 이면 GroupBox 미사용)
            parent: 부모 위젯
        """

        def __init__(
            self,
            timeframes: Optional[List[str]] = None,
            title: Optional[str] = "타임프레임별 안정권 진행률",
            parent: Optional[QWidget] = None,
        ) -> None:
            super().__init__(parent)
            self._tfs: List[str] = list(timeframes or _DEFAULT_TFS)
            self._bars: Dict[str, QProgressBar] = {}
            self._chips: Dict[str, _StatusChip] = {}
            self._labels: Dict[str, QLabel] = {}
            self._anims: Dict[str, QPropertyAnimation] = {}
            self._selected_tfs: set = set(self._tfs)  # 기본: 전부 선택됨
            # 전체 진행률용 (집계 행)
            self._overall_bar: Optional[QProgressBar] = None
            self._overall_chip: Optional[_StatusChip] = None
            self._overall_anim: Optional[QPropertyAnimation] = None
            self._build_ui(title)

        # ------------------------------------------------------------------
        def _build_ui(self, title: Optional[str]) -> None:
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            host: QWidget
            if title:
                gb = QGroupBox(title, self)
                outer.addWidget(gb)
                host = gb
                grid = QGridLayout(gb)
            else:
                host = self
                grid = QGridLayout(self)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(4)

            # 0행: 전체 진행률 (집계)
            self._overall_label = QLabel("전체", host)
            self._overall_label.setMinimumWidth(48)
            self._overall_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            f = self._overall_label.font()
            f.setBold(True)
            self._overall_label.setFont(f)
            self._overall_bar = QProgressBar(host)
            self._overall_bar.setRange(0, 100)
            self._overall_bar.setValue(0)
            self._overall_bar.setFixedHeight(20)
            self._overall_bar.setTextVisible(True)
            self._overall_bar.setFormat("전체 %p%")
            self._overall_bar.setStyleSheet(
                "QProgressBar { border: 1.5px solid #007AFF; border-radius: 4px;"
                " text-align: center; background-color: #F0F8FF; color: #000; font-weight: bold; }"
                " QProgressBar::chunk { background-color: #007AFF; border-radius: 3px; }"
            )
            self._overall_chip = _StatusChip(host)
            grid.addWidget(self._overall_label, 0, 0)
            grid.addWidget(self._overall_bar, 0, 1)
            grid.addWidget(self._overall_chip, 0, 2)

            # 1행 이후: 각 타임프레임
            for row, tf in enumerate(self._tfs, start=1):
                lbl = QLabel(tf, host)
                lbl.setMinimumWidth(48)
                lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                bar = QProgressBar(host)
                bar.setRange(0, 100)
                bar.setValue(0)
                bar.setFixedHeight(18)
                bar.setTextVisible(True)
                bar.setFormat("%p%")
                chip = _StatusChip(host)
                grid.addWidget(lbl, row, 0)
                grid.addWidget(bar, row, 1)
                grid.addWidget(chip, row, 2)
                self._bars[tf] = bar
                self._chips[tf] = chip
                self._labels[tf] = lbl
            # 초기 강조 스타일 적용 (전부 선택 상태)
            self._apply_selection_style()

        # ------------------------------------------------------------------
        @pyqtSlot(dict)
        def update_from_results(self, results: Dict[str, Dict[str, Any]]) -> None:
            """``compute_safe_zone_pct`` 결과 dict 묶음으로 일괄 갱신.

            Args:
                results: ``{timeframe: {"coverage_pct": float, "status": str, ...}}``
            """
            pcts: List[float] = []
            statuses: List[str] = []
            for tf, info in (results or {}).items():
                if tf not in self._bars:
                    continue
                try:
                    pct = float(info.get("coverage_pct", 0.0) or 0.0)
                    pct = max(0.0, min(100.0, pct))
                except (TypeError, ValueError):
                    pct = 0.0
                status = str(info.get("status", "UNKNOWN") or "UNKNOWN").upper()
                self._animate_to(tf, int(round(pct)))
                self._chips[tf].set_status(status)
                # 전체 집계는 '선택된 TF' 만 사용 (수집 설정 기준)
                if tf in self._selected_tfs:
                    pcts.append(pct)
                    statuses.append(status)
            # 전체 집계 갱신 (선택된 TF 평균)
            if pcts:
                avg = sum(pcts) / len(pcts)
                self._animate_overall(int(round(avg)))
                # 종합 상태: STALE 하나라도 있으면 STALE, 모두 SAFE 면 SAFE, 그 외 SYNCING
                if all(s == "SAFE" for s in statuses):
                    overall_status = "SAFE"
                elif any(s == "STALE" for s in statuses):
                    overall_status = "SYNCING" if any(s != "STALE" for s in statuses) else "STALE"
                else:
                    overall_status = "SYNCING"
                if self._overall_chip is not None:
                    self._overall_chip.set_status(overall_status)

        def update_one(self, timeframe: str, coverage_pct: float, status: str) -> None:
            """단일 TF 갱신용 편의 메서드."""
            self.update_from_results({timeframe: {"coverage_pct": coverage_pct, "status": status}})

        # ------------------------------------------------------------------
        def set_selected_timeframes(self, timeframes: Optional[List[str]]) -> None:
            """수집 설정에 체크된 TF 리스트를 전달받아 강조 표시한다.

            Args:
                timeframes: 강조 대상 TF 리스트. None/빈 리스트면 전부 강조.
            """
            if timeframes:
                self._selected_tfs = {str(t) for t in timeframes if t in self._bars}
                if not self._selected_tfs:
                    self._selected_tfs = set(self._tfs)
            else:
                self._selected_tfs = set(self._tfs)
            self._apply_selection_style()

        def _apply_selection_style(self) -> None:
            """선택 상태에 따라 라벨/바 스타일을 적용 (강조 vs 비활성)."""
            for tf in self._tfs:
                lbl = self._labels.get(tf)
                bar = self._bars.get(tf)
                selected = tf in self._selected_tfs
                if lbl is not None:
                    f = lbl.font()
                    f.setBold(bool(selected))
                    lbl.setFont(f)
                    if selected:
                        lbl.setStyleSheet("color: #007AFF;")
                    else:
                        lbl.setStyleSheet("color: #888888;")
                if bar is not None:
                    if selected:
                        bar.setStyleSheet(
                            "QProgressBar { border: 1.5px solid #007AFF; border-radius: 4px;"
                            " text-align: center; background-color: #F5F5F5; color: #000; font-weight: bold; }"
                            " QProgressBar::chunk { background-color: #34C759; border-radius: 3px; }"
                        )
                    else:
                        bar.setStyleSheet(
                            "QProgressBar { border: 1px solid #DDDDDD; border-radius: 4px;"
                            " text-align: center; background-color: #FAFAFA; color: #888; }"
                            " QProgressBar::chunk { background-color: #BBBBBB; border-radius: 3px; }"
                        )

        # ------------------------------------------------------------------
        def _animate_to(self, tf: str, target: int) -> None:
            bar = self._bars.get(tf)
            if bar is None:
                return
            current = bar.value()
            if current == target:
                return
            anim = self._anims.get(tf)
            if anim is None:
                anim = QPropertyAnimation(bar, b"value", self)
                anim.setDuration(300)
                self._anims[tf] = anim
            anim.stop()
            anim.setStartValue(current)
            anim.setEndValue(target)
            anim.start()

        def _animate_overall(self, target: int) -> None:
            bar = self._overall_bar
            if bar is None:
                return
            current = bar.value()
            if current == target:
                return
            anim = self._overall_anim
            if anim is None:
                anim = QPropertyAnimation(bar, b"value", self)
                anim.setDuration(400)
                self._overall_anim = anim
            anim.stop()
            anim.setStartValue(current)
            anim.setEndValue(target)
            anim.start()

        # ------------------------------------------------------------------
        def reset(self) -> None:
            for tf in self._tfs:
                self._bars[tf].setValue(0)
                self._chips[tf].set_status("UNKNOWN")
            if self._overall_bar is not None:
                self._overall_bar.setValue(0)
            if self._overall_chip is not None:
                self._overall_chip.set_status("UNKNOWN")

else:  # pragma: no cover
    class TFProgressWidget:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            self._latest: Dict[str, Dict[str, Any]] = {}

        def update_from_results(self, results: Dict[str, Dict[str, Any]]) -> None:
            self._latest = dict(results or {})

        def update_one(self, timeframe: str, coverage_pct: float, status: str) -> None:
            self._latest[timeframe] = {"coverage_pct": coverage_pct, "status": status}

        def set_selected_timeframes(self, timeframes: Optional[List[str]]) -> None:
            self._selected = list(timeframes or [])

        def reset(self) -> None:
            self._latest = {}


__all__ = ["TFProgressWidget"]
