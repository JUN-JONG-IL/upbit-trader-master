# -*- coding: utf-8 -*-
"""
Tab 2: 데이터 흐름 제어 로직 (v3.0 - 헬퍼 클래스 분리)

변경사항 v3.0 (2026-04-28):
- ✅ 단계별 갱신 로직을 DataFlowStepUpdater 헬퍼로 분리 (_dataflow_helpers.py)
- ✅ DataFlowTab은 타이머/UI 로드만 담당 (300줄 이하)
- ✅ SRP 준수: 단계별 로직은 DataFlowStepUpdater 위임

변경사항 v2.2 (2026-04-26):
- ✅ update_pipeline_status() 완전 재작성
- ✅ get_pipeline_stats() 호출 통합
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer, Qt
    from PyQt5.QtWidgets import QWidget, QApplication
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

# ============================================================
# 상수
# ============================================================
_COLLECTION_PROGRESS_MAX: int = 1000  # 프로그레스바 최대값 (수집 건수 기준)


# ============================================================
# DataFlowTab 클래스
# ============================================================
if _HAS_QT:
    from ._dataflow_helpers import DataFlowStepUpdater

    class DataFlowTab(QWidget):
        """Tab 2: 데이터 흐름 — uic.loadUi() 기반 자립형 위젯.

        파이프라인 단계별 갱신 로직은 DataFlowStepUpdater에 위임합니다.

        Args:
            parent: 부모 QWidget (None이면 최상위 창)
        """

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            ui_path = os.path.join(os.path.dirname(__file__), "dataflow_tab.ui")
            try:
                uic.loadUi(ui_path, self)
                logger.info("[DataFlowTab] ✅ UI 파일 로드 성공: %s", ui_path)
            except Exception as exc:
                logger.error("[DataFlowTab] ❌ UI 파일 로드 실패: %s", exc, exc_info=True)

            self._step_updater = DataFlowStepUpdater()

            self._timer = QTimer(self)
            self._timer.setInterval(3000)
            self._timer.timeout.connect(self._update_ui)

            # 격리 레이블 클릭 이벤트 설치
            self._setup_isolated_label_click()

        def start_updates(self, interval_ms: int = 3000) -> None:
            """자동 갱신 타이머 시작.

            Args:
                interval_ms: 갱신 간격 (밀리초, 최소 3000)
            """
            self._timer.setInterval(max(3000, int(interval_ms)))
            self._timer.start()
            logger.info("[DataFlowTab] ✅ 자동 갱신 시작 (%d ms)", interval_ms)

        def stop_updates(self) -> None:
            """자동 갱신 타이머 중지."""
            self._timer.stop()
            logger.info("[DataFlowTab] ⏸️ 자동 갱신 중지")

        def _update_ui(self) -> None:
            """주기적 UI 갱신 (타이머 콜백)."""
            try:
                from ..utils import get_pipeline_stats
                stats = get_pipeline_stats()
                self.update_pipeline_status(stats)
            except ImportError:
                logger.debug("[DataFlowTab] get_pipeline_stats 임포트 실패 — 폴백 시도")
                try:
                    self.update_pipeline_status({"staging": 0, "candles": 0, "isolated": 0})
                except Exception as fb_exc:
                    logger.debug("[DataFlowTab] 폴백 update_pipeline_status 실패: %s", fb_exc)
            except Exception as exc:
                logger.debug("[DataFlowTab] _update_ui 실패: %s", exc)

        def _setup_isolated_label_click(self) -> None:
            """격리 레이블에 클릭 이벤트를 설치합니다."""
            lbl = getattr(self, "label_valid_isolated", None)
            if lbl is None:
                return
            try:
                # 커서를 포인터로 변경하여 클릭 가능 표시
                from PyQt5.QtGui import QCursor
                lbl.setCursor(QCursor(Qt.PointingHandCursor))
                lbl.setToolTip("🔍 클릭하면 격리 데이터 상세 분석 창이 열립니다")
                # mousePressEvent 오버라이딩 대신 installEventFilter 사용
                lbl.mousePressEvent = self._on_isolated_label_clicked
            except Exception as exc:
                logger.debug("[DataFlowTab] 격리 레이블 클릭 이벤트 설치 실패: %s", exc)

        def _on_isolated_label_clicked(self, event) -> None:
            """격리 레이블 클릭 시 IsolatedDetailDialog 표시."""
            try:
                from ..dialogs.isolated_detail_dialog import IsolatedDetailDialog
                dlg = IsolatedDetailDialog(self)
                dlg.show()
                dlg.raise_()
            except Exception as exc:
                logger.warning("[DataFlowTab] 격리 상세 다이얼로그 열기 실패: %s", exc)

        def update_pipeline_status(self, stats: dict) -> None:
            """파이프라인 단계별 상태를 갱신합니다.

            DataFlowStepUpdater에 갱신 로직을 위임합니다.

            Args:
                stats: {"staging": int, "candles": int, "isolated": int} 형태의 통계 dict
            """
            self._step_updater.update_all(self, stats)

        # ============================================================
        # 레거시 함수: update_dataflow() (호환성 유지)
        # ============================================================
        def update_dataflow(
            self,
            collect_count: int,
            valid_ok: int,
            pipeline_bg_cache: Dict[str, Any],
            pipeline_bg_lock: Any,
            ui_utils: Any,
        ) -> None:
            """데이터 흐름 탭 UI 갱신 (캐시 우선 사용) — 레거시 호환.

            ⚠️ 주의: 이 함수는 호환성 유지를 위해 남겨둠.
            ✅ 권장: update_pipeline_status() 사용.

            Args:
                collect_count: 수집 건수
                valid_ok: 검증 성공 건수
                pipeline_bg_cache: 백그라운드 캐시 dict
                pipeline_bg_lock: 캐시 락
                ui_utils: UI 유틸리티 모듈
            """
            try:
                try:
                    if hasattr(self, "label_collect_count"):
                        self.label_collect_count.setText(f"수집 건수: {collect_count:,}")
                except Exception as exc:
                    logger.debug("[DataFlowTab] label_collect_count 갱신 실패: %s", exc)

                try:
                    if hasattr(self, "progress_collect"):
                        pct = min(100, int(collect_count * 100 // _COLLECTION_PROGRESS_MAX))
                        self.progress_collect.setValue(pct)
                except Exception as exc:
                    logger.debug("[DataFlowTab] progress_collect 갱신 실패: %s", exc)

                with pipeline_bg_lock:
                    cache = dict(pipeline_bg_cache)

                try:
                    isolated_stats = (
                        cache.get("table_isolated")
                        or ui_utils.get_table_stats("isolated_candles")
                    )
                    isolated_count = isolated_stats.get("row_count", 0)
                    if hasattr(self, "label_valid_ok"):
                        self.label_valid_ok.setText(f"[OK] 정상: {valid_ok:,} 건")
                    if hasattr(self, "label_valid_isolated"):
                        self.label_valid_isolated.setText(f"[격리] {isolated_count:,} 건")
                except Exception as exc:
                    logger.debug("[DataFlowTab] 검증 결과 갱신 실패: %s", exc)

                try:
                    staging_stats = (
                        cache.get("table_staging")
                        or ui_utils.get_table_stats("staging_candles")
                    )
                    gap_stats = (
                        cache.get("table_gap")
                        or ui_utils.get_table_stats("gap_fill_queue")
                    )
                    if hasattr(self, "label_step3_staging"):
                        self.label_step3_staging.setText(
                            f"Staging: {staging_stats.get('row_count', 0):,} 건"
                        )
                    if hasattr(self, "label_step3_gap"):
                        self.label_step3_gap.setText(
                            f"Gap 큐: {gap_stats.get('row_count', 0):,} 건"
                        )
                except Exception as exc:
                    logger.debug("[DataFlowTab] Staging/Gap 갱신 실패: %s", exc)

                try:
                    candles_stats = (
                        cache.get("table_candles")
                        or ui_utils.get_table_stats("candles")
                    )
                    if hasattr(self, "label_timescale_total"):
                        self.label_timescale_total.setText(
                            f"TimescaleDB 총 건수: {candles_stats.get('row_count', 0):,}"
                        )
                except Exception as exc:
                    logger.debug("[DataFlowTab] TimescaleDB 갱신 실패: %s", exc)

                logger.debug("[DataFlowTab] update_dataflow 완료 (레거시)")

            except Exception as exc:
                logger.error("[DataFlowTab] ❌ update_dataflow 전체 실패: %s", exc, exc_info=True)


# ============================================================
# 더미 클래스 (PyQt5 미설치 시)
# ============================================================
else:
    class DataFlowTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스."""

        def __init__(self, parent: Optional[object] = None) -> None:
            logger.warning("[DataFlowTab] PyQt5 미설치 - 더미 클래스 사용")

        def start_updates(self, interval_ms: int = 3000) -> None:
            """자동 갱신 시작 (더미)."""
            pass

        def stop_updates(self) -> None:
            """자동 갱신 중지 (더미)."""
            pass

        def update_dataflow(self, *args: Any, **kwargs: Any) -> None:
            """레거시 갱신 (더미)."""
            pass

        def update_pipeline_status(self, stats: dict) -> None:
            """파이프라인 상태 갱신 (더미)."""
            pass