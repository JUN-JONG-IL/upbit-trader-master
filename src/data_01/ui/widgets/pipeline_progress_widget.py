# -*- coding: utf-8 -*-
"""
파이프라인 Progress Bar 위젯

[책임]
- 3단계 파이프라인 진행률 표시 (수집 → 검증 → DB 저장)
- 각 단계별 QProgressBar + 건수 라벨
- update_progress() 호출로 외부에서 값을 주입
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import (
        QFormLayout,
        QGroupBox,
        QLabel,
        QProgressBar,
        QVBoxLayout,
        QWidget,
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    logger.debug("[PipelineProgressWidget] PyQt5 없음 — 더미 클래스 사용")


if _HAS_QT:
    class PipelineProgressWidget(QWidget):
        """
        파이프라인 3단계 Progress Bar 위젯

        Step 1: 수집  (Redis L1 캐시 건수 / 최대 기준치)
        Step 2: 검증  (정상 건수 / 격리 건수 비율)
        Step 3: 저장  (DB 저장 완료 건수 / 수집 건수 비율)
        """

        # 각 단계의 기준 최대값 (진행률 100% 기준)
        _MAX_COLLECT = 1000
        _MAX_VALID = 1000
        _MAX_SAVE = 1000

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self._build_ui()

        # ------------------------------------------------------------------
        # UI 구성
        # ------------------------------------------------------------------

        def _build_ui(self) -> None:
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)

            box = QGroupBox("📊 파이프라인 진행률")
            form = QFormLayout(box)

            # Step 1: 수집
            self._lbl_collect = QLabel("수집 건수: 0")
            self._pb_collect = QProgressBar()
            self._pb_collect.setRange(0, 100)
            self._pb_collect.setValue(0)
            form.addRow("Step 1 수집:", self._lbl_collect)
            form.addRow("", self._pb_collect)

            # Step 2: 검증
            self._lbl_valid = QLabel("정상: 0  |  격리: 0")
            self._pb_valid = QProgressBar()
            self._pb_valid.setRange(0, 100)
            self._pb_valid.setValue(0)
            form.addRow("Step 2 검증:", self._lbl_valid)
            form.addRow("", self._pb_valid)

            # Step 3: DB 저장
            self._lbl_save = QLabel("DB 저장: 0")
            self._pb_save = QProgressBar()
            self._pb_save.setRange(0, 100)
            self._pb_save.setValue(0)
            form.addRow("Step 3 저장:", self._lbl_save)
            form.addRow("", self._pb_save)

            root.addWidget(box)

        # ------------------------------------------------------------------
        # 공개 API
        # ------------------------------------------------------------------

        def update_progress(
            self,
            collect_count: int = 0,
            valid_ok: int = 0,
            valid_iso: int = 0,
            save_count: int = 0,
        ) -> None:
            """파이프라인 진행률을 갱신합니다.

            Args:
                collect_count: Step 1 수집 건수
                valid_ok: Step 2 정상 검증 건수
                valid_iso: Step 2 격리 건수
                save_count: Step 3 DB 저장 완료 건수
            """
            try:
                # Step 1
                self._lbl_collect.setText(f"수집 건수: {collect_count:,}")
                pct1 = min(100, int(collect_count * 100 // max(self._MAX_COLLECT, 1)))
                self._pb_collect.setValue(pct1)

                # Step 2
                self._lbl_valid.setText(
                    f"정상: {valid_ok:,}  |  격리: {valid_iso:,}"
                )
                total_valid = valid_ok + valid_iso
                pct2 = min(100, int(valid_ok * 100 // max(total_valid, 1))) if total_valid else 0
                self._pb_valid.setValue(pct2)

                # Step 3
                self._lbl_save.setText(f"DB 저장: {save_count:,}")
                pct3 = min(100, int(save_count * 100 // max(self._MAX_SAVE, 1)))
                self._pb_save.setValue(pct3)
            except Exception as exc:
                logger.debug("[PipelineProgressWidget] 갱신 실패: %s", exc)

else:
    class PipelineProgressWidget:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""

        def __init__(self, parent=None) -> None:
            logger.warning("[PipelineProgressWidget] PyQt5 미설치 — 더미 인스턴스 생성")

        def update_progress(self, **kwargs) -> None:
            """더미 메서드"""
