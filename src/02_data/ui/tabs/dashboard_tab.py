# -*- coding: utf-8 -*-
"""Tab 1: 실시간 대시보드 제어 로직"""
from __future__ import annotations
import logging
import os

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer, Qt, QObject, QEvent
    from PyQt5.QtGui import QColor, QCursor
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QApplication
    _HAS_QT = True
    # 서비스 실패 행 배경색 (#FFE0E0)
    _FAILED_SERVICE_BG_COLOR = QColor(255, 224, 224)
except ImportError:
    _HAS_QT = False
    _FAILED_SERVICE_BG_COLOR = None  # type: ignore[assignment]

from ._mixins import TableCopyMixin

if _HAS_QT:
    class _LabelClickFilter(QObject):
        """QLabel 클릭 이벤트를 처리하는 이벤트 필터."""

        def __init__(self, callback, parent=None):
            super().__init__(parent)
            self._callback = callback

        def eventFilter(self, obj, event: QEvent) -> bool:
            if event.type() == QEvent.MouseButtonPress:
                self._callback()
                return True
            return False

    class DashboardTab(TableCopyMixin, QWidget):
        """Tab 1: 실시간 대시보드 — uic.loadUi() 기반 자립형 위젯"""

        def __init__(self, parent=None):
            super().__init__(parent)
            ui_path = os.path.join(os.path.dirname(__file__), "dashboard_tab.ui")
            try:
                uic.loadUi(ui_path, self)
            except Exception as exc:
                logger.warning("[DashboardTab] UI 파일 로드 실패, 빈 위젯으로 폴백: %s", exc)

            self._setup_table_copy()
            self._timer = QTimer(self)
            self._timer.setInterval(3000)
            self._timer.timeout.connect(self._update_ui)

            # label_isolated_count 클릭 → IsolatedDetailDialog 팝업 (이벤트 필터 방식)
            lbl = getattr(self, "label_isolated_count", None)
            if lbl is not None:
                lbl.setCursor(QCursor(Qt.PointingHandCursor))
                self._isolated_click_filter = _LabelClickFilter(
                    self._on_isolated_label_clicked, lbl
                )
                lbl.installEventFilter(self._isolated_click_filter)

        # ── 기존 기능 ──────────────────────────────────────────────────

        def start_updates(self, interval_ms: int = 3000) -> None:
            """자동 갱신 시작"""
            self._timer.setInterval(max(3000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            """자동 갱신 중지"""
            self._timer.stop()

        def _update_ui(self) -> None:
            """3초마다 대시보드 UI 갱신 — 수집 설정·Pipeline·Cache 상태를 통합 표시"""
            try:
                self._refresh_collection_status()
            except Exception as exc:
                logger.debug("[DashboardTab] _refresh_collection_status 실패: %s", exc)
            try:
                self._refresh_pipeline_status()
            except Exception as exc:
                logger.debug("[DashboardTab] _refresh_pipeline_status 실패: %s", exc)

        def _refresh_collection_status(self) -> None:
            """수집 설정 상태 레이블 갱신 (적용값·실제동작값·제한값)."""
            try:
                from ..utils.config_loader import get_ws_max_subscribe, get_symbol_query_limit
                ws_max = get_ws_max_subscribe()
                sym_limit = get_symbol_query_limit()
                from ..utils.constants import MAX_SUBSCRIBE_LIMIT
                lbl = getattr(self, "label_ws_qps", None)
                if lbl is not None:
                    lbl.setText(
                        f"WebSocket 구독 설정: {ws_max:,}개 / 최대 {MAX_SUBSCRIBE_LIMIT:,}개"
                    )
            except Exception as exc:
                logger.debug("[DashboardTab] 수집 설정 상태 갱신 실패: %s", exc)

        def _refresh_pipeline_status(self) -> None:
            """Pipeline 상태 (Staging/Candles/Isolated/Gap) 레이블 갱신."""
            try:
                from ..utils.candle_queries import query_table_counts
                counts = query_table_counts()
                staging = counts.get("staging", 0)
                candles = counts.get("candles", 0)
                isolated = counts.get("isolated", 0)
                gap_count = counts.get("gap_queue", 0)
                last_save = counts.get("last_save_time")
                if last_save is not None:
                    from datetime import datetime
                    ts = (
                        last_save.strftime("%m-%d %H:%M:%S")
                        if isinstance(last_save, datetime)
                        else str(last_save)
                    )
                else:
                    ts = "--"
                self.update_pipeline_labels(
                    staging=staging,
                    candles=candles,
                    isolated=isolated,
                    gap_count=gap_count,
                )
                lbl_recv = getattr(self, "label_last_recv", None)
                if lbl_recv is not None:
                    lbl_recv.setText(f"[TimescaleDB] 마지막 저장: {ts}")
            except Exception as exc:
                logger.debug("[DashboardTab] Pipeline 상태 갱신 실패: %s", exc)

        def _on_isolated_label_clicked(self) -> None:
            """격리 건수 레이블 클릭 시 IsolatedDetailDialog 팝업 오픈."""
            try:
                from ..dialogs.isolated_detail_dialog import IsolatedDetailDialog
                dlg = IsolatedDetailDialog(self)
                dlg.show()
            except Exception as exc:
                logger.warning("[DashboardTab] IsolatedDetailDialog 오픈 실패: %s", exc)


        def update_service_table(self, services, check_fn_map) -> None:
            """서비스 연결 상태 테이블 갱신 (table_services 위젯)"""
            table = getattr(self, "table_services", None)
            if table is None:
                return
            try:
                table.setRowCount(len(services))
                for i, (name, host, impl, svc_key) in enumerate(services):
                    check_fn = check_fn_map.get(svc_key, lambda: False)
                    try:
                        ok = check_fn()
                    except Exception:
                        ok = False

                    name_item = QTableWidgetItem(name)
                    status_item = QTableWidgetItem("[OK]" if ok else "[오류]")
                    host_item = QTableWidgetItem(host)
                    impl_item = QTableWidgetItem(impl if ok else "--")

                    if ok:
                        status_item.setForeground(QColor(34, 197, 94))
                    else:
                        status_item.setForeground(QColor(239, 68, 68))
                        # 실패 행 배경색 강조
                        if _FAILED_SERVICE_BG_COLOR is not None:
                            for item in (name_item, status_item, host_item, impl_item):
                                item.setBackground(_FAILED_SERVICE_BG_COLOR)

                    table.setItem(i, 0, name_item)
                    table.setItem(i, 1, status_item)
                    table.setItem(i, 2, host_item)
                    table.setItem(i, 3, impl_item)
            except Exception as exc:
                logger.error("[DashboardTab] 서비스 테이블 갱신 실패: %s", exc)

        def update_metrics(
            self,
            ws_qps: int = 0,
            pipeline_qps: int = 0,
            staging_count: int = 0,
            last_recv: str = "--",
        ) -> None:
            """핵심 지표 레이블 갱신"""
            try:
                if hasattr(self, "label_ws_qps"):
                    self.label_ws_qps.setText(f"WebSocket 수신: {ws_qps}건/초")
                if hasattr(self, "label_pipeline_qps"):
                    self.label_pipeline_qps.setText(f"Pipeline 처리: {pipeline_qps}건/초")
                if hasattr(self, "label_realtime_staging_count"):
                    self.label_realtime_staging_count.setText(
                        f"Staging → Candles: {staging_count:,} 건"
                    )
                if hasattr(self, "label_last_recv"):
                    self.label_last_recv.setText(f"마지막 수신: {last_recv}")
            except Exception as exc:
                logger.debug("[DashboardTab] 지표 갱신 실패: %s", exc)

        def update_pipeline_labels(
            self,
            staging: int = 0,
            candles: int = 0,
            isolated: int = 0,
            gap_count: int = 0,
            isolated_recent: int = 0,
        ) -> None:
            """파이프라인 상태 레이블 갱신"""
            try:
                if hasattr(self, "label_staging_count"):
                    self.label_staging_count.setText(f"Staging: {staging:,} 건")
                if hasattr(self, "label_candles_count"):
                    self.label_candles_count.setText(f"Candles: {candles:,} 건")
                if hasattr(self, "label_isolated_count"):
                    if isolated_recent > 0:
                        self.label_isolated_count.setText(
                            f"[격리] Isolated: 최근 {isolated_recent:,}건 (누적 {isolated:,}건)"
                        )
                    elif isolated > 0:
                        self.label_isolated_count.setText(
                            f"[주의] Isolated: 최근 {isolated_recent:,}건 (누적 {isolated:,}건)"
                        )
                    else:
                        self.label_isolated_count.setText("[OK] Isolated: 0 건")
                if hasattr(self, "label_gap_count"):
                    self.label_gap_count.setText(f"대기 건수: {gap_count:,} 건")
            except Exception as exc:
                logger.debug("[DashboardTab] 파이프라인 레이블 갱신 실패: %s", exc)

        def update_cache_labels(
            self,
            l1_count: int = 0,
            pubsub_channels: int = 0,
            last_update: str = "--",
        ) -> None:
            """캐시 상태 및 최종 갱신 시각 레이블 갱신.

            Args:
                l1_count: Redis L1 캐시 항목 수
                pubsub_channels: Redis Pub/Sub 채널 수
                last_update: 최종 갱신 시각 문자열 (HH:MM:SS)
            """
            try:
                if hasattr(self, "label_l1_cache"):
                    self.label_l1_cache.setText(f"L1 캐시: {l1_count:,} 항목")
                if hasattr(self, "label_pubsub"):
                    self.label_pubsub.setText(f"Pub/Sub 채널: {pubsub_channels}")
                if hasattr(self, "label_last_update"):
                    self.label_last_update.setText(f"⏱️ 최종 갱신: {last_update}")
            except Exception as exc:
                logger.debug("[DashboardTab] 캐시 레이블 갱신 실패: %s", exc)


else:
    class DashboardTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""
        def __init__(self, parent=None):
            pass
        def start_updates(self, interval_ms: int = 3000) -> None:
            pass
        def stop_updates(self) -> None:
            pass
        def update_service_table(self, services, check_fn_map) -> None:
            pass
        def update_metrics(self, **kwargs) -> None:
            pass
        def update_pipeline_labels(self, **kwargs) -> None:
            pass
        def update_cache_labels(self, **kwargs) -> None:
            pass
        def _on_isolated_label_clicked(self) -> None:
            pass
