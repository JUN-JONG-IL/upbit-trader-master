#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
고급 모니터링 대시보드 (팝업 다이얼로그)

기능:
- Gap Fill Queue 실시간 진행 현황
- isolated_candles 에러 분석 테이블
- DB 상세 헬스체크 (테이블 통계)
- 1초 주기 자동 갱신 (QTimer)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtWidgets import (
        QDialog,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QTableWidget,
        QTableWidgetItem,
        QGroupBox,
        QPushButton,
        QHeaderView,
        QSplitter,
        QWidget,
    )
    from PyQt5.QtCore import QTimer, Qt
    from PyQt5.QtGui import QColor, QFont
    _HAS_QT = True
except Exception as _qt_exc:
    _HAS_QT = False
    logger.debug("[MonitoringDashboard] PyQt5 미설치: %s", _qt_exc)


class MonitoringDashboard(QDialog if _HAS_QT else object):  # type: ignore[misc]
    """고급 모니터링 대시보드 팝업 다이얼로그.

    1초마다 모든 지표를 자동으로 갱신합니다.
    """

    _REFRESH_INTERVAL_MS = 1_000  # 1초

    def __init__(self, parent=None) -> None:
        if not _HAS_QT:
            logger.warning("[MonitoringDashboard] PyQt5 미설치 - 다이얼로그 생성 불가")
            return

        super().__init__(parent)
        self.setWindowTitle("📊 고급 모니터링 대시보드")
        self.resize(1200, 800)

        self._timer: Optional[QTimer] = None

        # utils 모듈을 초기화 시점에 한 번만 import하여 캐시 (매 갱신마다 import 비용 제거)
        self._ui_utils = None
        try:
            from . import utils as _ui_utils  # type: ignore
            self._ui_utils = _ui_utils
        except Exception as exc:
            logger.debug("[MonitoringDashboard] utils 모듈 로드 실패: %s", exc)

        self._init_ui()
        self._setup_timer()
        self._update_all()

    # ------------------------------------------------------------------
    # UI 초기화
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        """메인 레이아웃 구성"""
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        # 헤더
        header_layout = QHBoxLayout()
        title_lbl = QLabel("📊 고급 모니터링 대시보드")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        self.label_last_updated = QLabel("최종 갱신: --")
        header_layout.addWidget(self.label_last_updated)
        btn_refresh = QPushButton("🔄 새로고침")
        btn_refresh.setMinimumSize(110, 32)
        btn_refresh.clicked.connect(self._update_all)
        header_layout.addWidget(btn_refresh)
        root.addLayout(header_layout)

        # 스플리터 (상단: 요약 지표 / 하단: 상세 테이블)
        splitter = QSplitter(Qt.Vertical)

        # 상단 요약 영역
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        # Gap Fill Queue 요약
        gap_group = QGroupBox("📋 Gap Fill Queue")
        gap_layout = QVBoxLayout(gap_group)
        self.label_gap_queue = QLabel("대기 큐: -- 건")
        self.label_gap_pending = QLabel("대기 중(pending): --")
        self.label_gap_in_progress = QLabel("처리 중(in_progress): --")
        self.label_gap_resolved = QLabel("완료(resolved): --")
        self.label_gap_failed = QLabel("실패(failed): --")
        for lbl in (
            self.label_gap_queue,
            self.label_gap_pending,
            self.label_gap_in_progress,
            self.label_gap_resolved,
            self.label_gap_failed,
        ):
            gap_layout.addWidget(lbl)
        gap_layout.addStretch()
        top_layout.addWidget(gap_group)

        # 테이블 통계 요약
        stats_group = QGroupBox("🗄️ 테이블 통계")
        stats_layout = QVBoxLayout(stats_group)
        self.label_staging_stats = QLabel("staging_candles: -- 건")
        self.label_candles_stats = QLabel("candles: -- 건")
        self.label_isolated_stats = QLabel("isolated_candles: -- 건")
        self.label_gap_queue_stats = QLabel("gap_fill_queue: -- 건")
        for lbl in (
            self.label_staging_stats,
            self.label_candles_stats,
            self.label_isolated_stats,
            self.label_gap_queue_stats,
        ):
            stats_layout.addWidget(lbl)
        stats_layout.addStretch()
        top_layout.addWidget(stats_group)

        splitter.addWidget(top_widget)

        # 하단 상세 테이블 영역
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)

        # isolated_candles 에러 분석 테이블
        errors_group = QGroupBox("🔴 isolated_candles 에러 분석 (최근 100건)")
        errors_layout = QVBoxLayout(errors_group)
        self.label_error_count = QLabel("총 에러: -- 건")
        errors_layout.addWidget(self.label_error_count)
        self.table_errors = QTableWidget()
        self.table_errors.setColumnCount(4)
        self.table_errors.setHorizontalHeaderLabels(["격리 시각", "심볼", "타임프레임", "원인"])
        self.table_errors.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_errors.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_errors.setAlternatingRowColors(True)
        errors_layout.addWidget(self.table_errors)
        bottom_layout.addWidget(errors_group)

        # Gap Fill Queue 상세 테이블
        gap_detail_group = QGroupBox("📋 Gap Fill Queue 상세 (최근 100건)")
        gap_detail_layout = QVBoxLayout(gap_detail_group)
        self.table_gap_details = QTableWidget()
        self.table_gap_details.setColumnCount(6)
        self.table_gap_details.setHorizontalHeaderLabels(
            ["심볼", "타임프레임", "Gap 시작", "Gap 종료", "우선순위", "상태"]
        )
        self.table_gap_details.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_gap_details.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_gap_details.setAlternatingRowColors(True)
        gap_detail_layout.addWidget(self.table_gap_details)
        bottom_layout.addWidget(gap_detail_group)

        splitter.addWidget(bottom_widget)
        splitter.setSizes([250, 550])

        root.addWidget(splitter)

        # 하단 닫기 버튼
        btn_close = QPushButton("닫기")
        btn_close.setMinimumSize(80, 32)
        btn_close.clicked.connect(self.close)
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_layout.addWidget(btn_close)
        root.addLayout(close_layout)

    # ------------------------------------------------------------------
    # 타이머 설정
    # ------------------------------------------------------------------

    def _setup_timer(self) -> None:
        """1초 주기 자동 갱신 타이머 설정"""
        self._timer = QTimer(self)
        self._timer.setInterval(self._REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self._update_all)
        self._timer.start()

    # ------------------------------------------------------------------
    # 갱신 로직
    # ------------------------------------------------------------------

    def _update_all(self) -> None:
        """1초마다 모든 지표 갱신"""
        if self._ui_utils is None:
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if hasattr(self, "label_last_updated"):
            self.label_last_updated.setText(f"최종 갱신: {now_str}")

        self._refresh_gap_summary(self._ui_utils)
        self._refresh_table_stats(self._ui_utils)
        self._refresh_error_table(self._ui_utils)
        self._refresh_gap_table(self._ui_utils)

    def _refresh_gap_summary(self, utils) -> None:
        """Gap Fill Queue 요약 갱신"""
        try:
            connector = utils.get_timescale_connector()
            if connector is None:
                return
            conn = None
            cur = None
            try:
                conn = connector.get_connection(retry=False)
                cur = conn.cursor()
                cur.execute(
                    "SELECT status, COUNT(*) FROM gap_fill_queue GROUP BY status"
                )
                rows = cur.fetchall()
                counts: Dict[str, int] = {r[0]: int(r[1]) for r in rows}
                total = sum(counts.values())
                pending = counts.get("pending", 0)
                in_progress = counts.get("in_progress", 0)
                resolved = counts.get("resolved", 0)
                failed = counts.get("failed", 0)

                self.label_gap_queue.setText(f"총 큐: {total:,} 건")
                self.label_gap_pending.setText(f"대기 중(pending): {pending:,}")
                self.label_gap_in_progress.setText(f"처리 중(in_progress): {in_progress:,}")
                self.label_gap_resolved.setText(f"완료(resolved): {resolved:,}")
                self.label_gap_failed.setText(f"실패(failed): {failed:,}")

                # 색상 강조
                if failed > 0:
                    self.label_gap_failed.setStyleSheet("color: red; font-weight: bold;")
                else:
                    self.label_gap_failed.setStyleSheet("color: green;")
                if in_progress > 0:
                    self.label_gap_in_progress.setStyleSheet("color: orange; font-weight: bold;")
                else:
                    self.label_gap_in_progress.setStyleSheet("")
            except Exception as exc:
                logger.debug("[MonitoringDashboard] Gap 요약 조회 실패: %s", exc)
            finally:
                if cur is not None:
                    try:
                        cur.close()
                    except Exception:
                        pass
                if conn is not None:
                    try:
                        connector.put_connection(conn)
                    except Exception:
                        pass
        except Exception as exc:
            logger.debug("[MonitoringDashboard] Gap 요약 갱신 실패: %s", exc)

    def _refresh_table_stats(self, utils) -> None:
        """테이블 통계 갱신"""
        for table, lbl_attr in (
            ("staging_candles", "label_staging_stats"),
            ("candles", "label_candles_stats"),
            ("isolated_candles", "label_isolated_stats"),
            ("gap_fill_queue", "label_gap_queue_stats"),
        ):
            try:
                stats = utils.get_table_stats(table)
                count = stats.get("row_count", 0)
                size = stats.get("size_human", "--")
                lbl = getattr(self, lbl_attr, None)
                if lbl is not None:
                    lbl.setText(f"{table}: {count:,} 건  ({size})")
            except Exception as exc:
                logger.debug("[MonitoringDashboard] 테이블 통계 실패 %s: %s", table, exc)

    def _refresh_error_table(self, utils) -> None:
        """isolated_candles 에러 분석 테이블 갱신"""
        if not hasattr(self, "table_errors"):
            return
        try:
            connector = utils.get_timescale_connector()
            if connector is None:
                return
            conn = None
            cur = None
            try:
                conn = connector.get_connection(retry=False)
                cur = conn.cursor()
                try:
                    cur.execute(
                        "SELECT isolated_at, symbol, timeframe, reason "
                        "FROM isolated_candles "
                        "ORDER BY isolated_at DESC "
                        "LIMIT 100"
                    )
                    rows = cur.fetchall()
                except Exception:
                    # reason 컬럼이 없는 구버전 스키마 폴백
                    # 신규 스키마: (isolated_at, symbol, timeframe, reason)
                    # 구버전 스키마: (time, symbol, timeframe, isolation_reason)
                    # 두 경우 모두 4번째 열(인덱스 3)이 원인 컬럼으로 테이블에 표시됨
                    try:
                        cur.execute(
                            "SELECT time, symbol, timeframe, isolation_reason "
                            "FROM isolated_candles "
                            "ORDER BY time DESC "
                            "LIMIT 100"
                        )
                        rows = cur.fetchall()
                    except Exception as exc:
                        logger.debug("[MonitoringDashboard] 에러 테이블 조회 실패: %s", exc)
                        return

                self.table_errors.setRowCount(len(rows))
                for i, row in enumerate(rows):
                    for j, val in enumerate(row):
                        item = QTableWidgetItem(str(val or ""))
                        if j == 3 and val:  # 원인 컬럼 강조
                            item.setForeground(QColor(200, 30, 30))
                        self.table_errors.setItem(i, j, item)
                if hasattr(self, "label_error_count"):
                    self.label_error_count.setText(f"총 에러: {len(rows)} 건")
            except Exception as exc:
                logger.error("[MonitoringDashboard] 에러 테이블 갱신 실패: %s", exc)
            finally:
                if cur is not None:
                    try:
                        cur.close()
                    except Exception:
                        pass
                if conn is not None:
                    try:
                        connector.put_connection(conn)
                    except Exception:
                        pass
        except Exception as exc:
            logger.error("[MonitoringDashboard] 에러 테이블 갱신 실패: %s", exc)

    def _refresh_gap_table(self, utils) -> None:
        """Gap Fill Queue 상세 테이블 갱신"""
        if not hasattr(self, "table_gap_details"):
            return
        try:
            gaps = utils.get_gaps()
            self.table_gap_details.setRowCount(len(gaps))
            for i, gap in enumerate(gaps):
                self.table_gap_details.setItem(i, 0, QTableWidgetItem(str(gap.get("symbol", ""))))
                self.table_gap_details.setItem(i, 1, QTableWidgetItem(str(gap.get("timeframe", ""))))
                self.table_gap_details.setItem(i, 2, QTableWidgetItem(str(gap.get("gap_start", ""))))
                self.table_gap_details.setItem(i, 3, QTableWidgetItem(str(gap.get("gap_end", ""))))
                priority = gap.get("priority", 0)
                try:
                    self.table_gap_details.setItem(i, 4, QTableWidgetItem(f"{float(priority):.4f}"))
                except Exception:
                    self.table_gap_details.setItem(i, 4, QTableWidgetItem(str(priority)))
                status = str(gap.get("status", ""))
                status_item = QTableWidgetItem(status)
                if status == "in_progress":
                    status_item.setForeground(QColor(200, 120, 0))
                elif status == "failed":
                    status_item.setForeground(QColor(200, 30, 30))
                elif status == "resolved":
                    status_item.setForeground(QColor(30, 150, 30))
                self.table_gap_details.setItem(i, 5, status_item)
        except Exception as exc:
            logger.error("[MonitoringDashboard] Gap 상세 테이블 갱신 실패: %s", exc)

    # ------------------------------------------------------------------
    # 닫기 시 타이머 정리
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        try:
            if self._timer is not None and self._timer.isActive():
                self._timer.stop()
        except Exception:
            pass
        if _HAS_QT:
            super().closeEvent(event)
