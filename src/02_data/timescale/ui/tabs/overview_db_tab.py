# -*- coding: utf-8 -*-
"""TimescaleDB DB 개요 탭 — 핵심 메트릭 카드 (QThread Worker 패턴)

역할:
- 버전, DB 크기, 테이블 수, 청크 수, 가동시간 등 핵심 메트릭을 동적 표시
- 30초 자동 갱신 | psycopg2.connect() 는 Worker 내부에서만 실행 (메인스레드 블로킹 없음)
"""
from __future__ import annotations

import os
import logging
from typing import Optional, Dict

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel,
        QGroupBox, QGridLayout, QPushButton, QFrame, QSizePolicy,
    )
    from PyQt5.QtCore import QTimer, pyqtSlot, Qt
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

try:
    from .db_worker import TimescaleWorker
except ImportError:
    from db_worker import TimescaleWorker  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# 핵심 메트릭 쿼리 (단일 행 반환)
_OVERVIEW_QUERY = """
SELECT
    (SELECT extversion FROM pg_extension WHERE extname = 'timescaledb') AS ts_version,
    version()                                                            AS pg_version,
    pg_size_pretty(pg_database_size(current_database()))                AS db_size,
    pg_database_size(current_database())                                AS db_size_bytes,
    (SELECT count(*)::int FROM timescaledb_information.hypertables)     AS hypertable_count,
    (SELECT count(*)::int FROM timescaledb_information.chunks)          AS chunk_count,
    (SELECT count(*)::int FROM pg_stat_user_tables
      WHERE schemaname = 'public')                                       AS table_count,
    (SELECT count(*)::int FROM timescaledb_information.chunks
      WHERE is_compressed)                                               AS compressed_chunks,
    (SELECT count(*)::int FROM timescaledb_information.continuous_aggregates) AS cagg_count,
    (SELECT pg_postmaster_start_time()::text)                           AS start_time,
    (SELECT (now() - pg_postmaster_start_time())::text)                 AS uptime
"""

# DB 크기 임계값
_SIZE_GREEN  = 50  * 1024 ** 3   # 50 GB
_SIZE_YELLOW = 100 * 1024 ** 3   # 100 GB


def _size_color(size_bytes: int) -> str:
    """크기에 따른 색상 반환."""
    if size_bytes < _SIZE_GREEN:
        return "#27AE60"   # 초록
    if size_bytes < _SIZE_YELLOW:
        return "#F39C12"   # 노랑
    return "#E74C3C"        # 빨강


def _safe_get(row, idx: int, default=None):
    """row 튜플/리스트에서 안전하게 idx 번 원소를 반환합니다."""
    try:
        return row[idx]
    except (IndexError, TypeError):
        return default


if _HAS_QT:
    class OverviewDbTab(QWidget):
        """DB 개요 탭.

        TimescaleDB 핵심 메트릭(버전·DB크기·테이블 수·청크 수·가동시간)을
        30초마다 자동으로 갱신하여 카드 형식으로 표시합니다.
        psycopg2.connect() 는 TimescaleWorker(QThread) 내부에서만 실행됩니다.
        """

        def __init__(self, conn_params: Optional[Dict] = None, parent=None):
            super().__init__(parent)
            self._conn_params: Dict = conn_params or {}
            self._worker: Optional[TimescaleWorker] = None
            self._build_ui()

            # 자동 갱신 타이머 (30초)
            self._timer = QTimer(self)
            self._timer.setInterval(30_000)
            self._timer.timeout.connect(self._update)

        # ------------------------------------------------------------------
        # UI 구성
        # ------------------------------------------------------------------

        def _build_ui(self) -> None:
            """메트릭 카드 레이아웃을 동적으로 생성합니다."""
            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(10)

            # 상단 배너
            banner = QFrame()
            banner.setStyleSheet(
                "QFrame { background-color: #EBF5FB; border-left: 4px solid #2563EB;"
                " border-radius: 3px; }"
            )
            bl = QVBoxLayout(banner)
            bl.setContentsMargins(12, 8, 12, 8)
            lbl_banner = QLabel(
                "📊 DB 개요 — TimescaleDB (Warm Tier) 핵심 메트릭  |  "
                "포트: 58529  |  DB: upbit_trader  |  보관: 3개월  |  30초 갱신"
            )
            lbl_banner.setStyleSheet("color: #1A5276; font-size: 8pt; font-weight: bold;")
            lbl_banner.setWordWrap(True)
            bl.addWidget(lbl_banner)
            layout.addWidget(banner)

            # 메트릭 카드 그룹
            metrics_group = QGroupBox("핵심 메트릭")
            metrics_group.setStyleSheet(
                "QGroupBox { border: 1px solid #BDC3C7; border-radius: 5px;"
                " margin-top: 8px; padding-top: 8px; background: #F8F9FA; }"
                "QGroupBox::title { subcontrol-origin: margin; padding: 0 6px;"
                " color: #2C3E50; font-weight: bold; }"
            )
            grid = QGridLayout(metrics_group)
            grid.setSpacing(8)

            # 메트릭 위젯 참조 저장 {attr_name: QLabel}
            self._metric_labels: Dict[str, QLabel] = {}

            metric_defs = [
                ("lbl_ts_version",   "TimescaleDB 버전", "조회 중..."),
                ("lbl_pg_version",   "PostgreSQL 버전",  "조회 중..."),
                ("lbl_db_size",      "DB 크기",          "조회 중..."),
                ("lbl_table_count",  "전체 테이블 수",   "조회 중..."),
                ("lbl_hyper_count",  "Hypertable 수",    "조회 중..."),
                ("lbl_chunk_count",  "전체 청크 수",     "조회 중..."),
                ("lbl_comp_chunks",  "압축된 청크 수",   "조회 중..."),
                ("lbl_cagg_count",   "연속 집계(CAGG) 수", "조회 중..."),
                ("lbl_uptime",       "DB 가동시간",       "조회 중..."),
                ("lbl_start_time",   "시작 시각",         "조회 중..."),
            ]

            for idx, (attr, title, default) in enumerate(metric_defs):
                row, col = divmod(idx, 2)
                card = self._make_card(title, default)
                # 값 레이블 저장
                self._metric_labels[attr] = card.findChild(QLabel, "val_label")
                grid.addWidget(card, row, col)

            layout.addWidget(metrics_group)

            # 갱신 버튼 + 상태 표시
            btn_row = QHBoxLayout()
            self._lbl_status = QLabel("상태: 대기 중")
            self._lbl_status.setStyleSheet("color: #7F8C8D; font-size: 8pt;")
            btn_row.addWidget(self._lbl_status)
            btn_row.addStretch()
            btn_refresh = QPushButton("🔄 즉시 갱신")
            btn_refresh.setStyleSheet(
                "QPushButton { background-color: #2980B9; color: white;"
                " border-radius: 4px; padding: 5px 14px; font-weight: bold; }"
                "QPushButton:hover { background-color: #21618C; }"
            )
            btn_refresh.clicked.connect(self._update)
            btn_row.addWidget(btn_refresh)
            layout.addLayout(btn_row)

            layout.addStretch()

        def _make_card(self, title: str, default_value: str) -> QFrame:
            """단일 메트릭 카드 위젯을 생성합니다."""
            card = QFrame()
            card.setStyleSheet(
                "QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0;"
                " border-radius: 6px; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 8)
            card_layout.setSpacing(2)

            lbl_title = QLabel(title)
            lbl_title.setStyleSheet("color: #64748B; font-size: 8pt;")

            lbl_val = QLabel(default_value)
            lbl_val.setObjectName("val_label")
            lbl_val.setStyleSheet("color: #1E293B; font-size: 11pt; font-weight: bold;")
            lbl_val.setWordWrap(True)

            card_layout.addWidget(lbl_title)
            card_layout.addWidget(lbl_val)
            return card

        # ------------------------------------------------------------------
        # 갱신 로직 (Worker 패턴)
        # ------------------------------------------------------------------

        def _update(self) -> None:
            """Worker가 실행 중이면 건너뜁니다. 아니면 새 Worker를 시작합니다."""
            # 이미 실행중인 Worker가 있으면 그대로 유지(중복 실행 방지)
            if self._worker:
                # 정리되지 않은 Worker가 남아있지만 실행 중이 아닐 경우, 안전하게 분리하고 해제
                if self._worker.isRunning():
                    return
                else:
                    try:
                        # 이전 시그널 연결 분리
                        self._worker.finished.disconnect(self._on_data_ready)
                        self._worker.error.disconnect(self._on_error)
                    except Exception:
                        pass
                    self._worker = None

            self._lbl_status.setText("상태: 조회 중...")
            self._worker = TimescaleWorker(self._conn_params, _OVERVIEW_QUERY)
            # 시그널 등록 — 완료 시 UI 갱신
            self._worker.finished.connect(self._on_data_ready)
            self._worker.error.connect(self._on_error)
            # start() 실패 가능성 대비 try/except
            try:
                self._worker.start()
            except Exception as exc:
                logger.debug("[OverviewDbTab] Worker 시작 실패: %s", exc)
                # 시그널/참조 정리
                try:
                    self._worker.finished.disconnect(self._on_data_ready)
                    self._worker.error.disconnect(self._on_error)
                except Exception:
                    pass
                self._worker = None
                self._on_error(str(exc))

        @pyqtSlot(object)
        def _on_data_ready(self, rows) -> None:
            """Worker 완료 시 메인스레드에서 UI를 갱신합니다."""
            try:
                from datetime import datetime
                if not rows:
                    self._lbl_status.setText("상태: 데이터 없음")
                    return
                row = rows[0]

                # row 컬럼 순서: ts_version, pg_version, db_size, db_size_bytes,
                #                hypertable_count, chunk_count, table_count,
                #                compressed_chunks, cagg_count, start_time, uptime
                ts_ver     = _safe_get(row, 0)
                pg_ver     = _safe_get(row, 1)
                db_size    = _safe_get(row, 2)
                db_size_bytes = _safe_get(row, 3)
                hyper_cnt  = _safe_get(row, 4)
                chunk_cnt  = _safe_get(row, 5)
                table_cnt  = _safe_get(row, 6)
                comp_chunks = _safe_get(row, 7)
                cagg_cnt   = _safe_get(row, 8)
                start_time = _safe_get(row, 9)
                uptime     = _safe_get(row, 10)

                def _set(attr: str, text: str, color: str = "#1E293B") -> None:
                    lbl = self._metric_labels.get(attr)
                    if lbl:
                        lbl.setText(str(text) if text is not None else "-")
                        lbl.setStyleSheet(
                            f"color: {color}; font-size: 11pt; font-weight: bold;"
                        )

                _set("lbl_ts_version",  f"v{ts_ver}" if ts_ver else "미설치")
                pg_parts = str(pg_ver or "").split(" ")
                pg_short = pg_parts[1] if len(pg_parts) > 1 else str(pg_ver or "-")
                _set("lbl_pg_version",  f"PostgreSQL {pg_short}")
                db_bytes = int(db_size_bytes or 0)
                _set("lbl_db_size",     str(db_size or "-"), _size_color(db_bytes))
                _set("lbl_table_count", f"{table_cnt or 0} 개")
                _set("lbl_hyper_count", f"{hyper_cnt or 0} 개")
                _set("lbl_chunk_count", f"{chunk_cnt or 0} 개")
                _set("lbl_comp_chunks", f"{comp_chunks or 0} 개")
                _set("lbl_cagg_count",  f"{cagg_cnt or 0} 개")
                uptime_str = str(uptime or "-").split(".")[0]
                _set("lbl_uptime",      uptime_str)
                start_str = str(start_time or "-")[:19]
                _set("lbl_start_time",  start_str)

                now = datetime.now().strftime("%H:%M:%S")
                self._lbl_status.setText(f"상태: 정상  |  마지막 갱신: {now}")
                self._lbl_status.setStyleSheet("color: #27AE60; font-size: 8pt;")
            finally:
                # Worker 참조/시그널 정리 — 메모리/시그널 누수 방지
                try:
                    if self._worker:
                        try:
                            self._worker.finished.disconnect(self._on_data_ready)
                            self._worker.error.disconnect(self._on_error)
                        except Exception:
                            pass
                        self._worker = None
                except Exception:
                    pass

        @pyqtSlot(str)
        def _on_error(self, msg: str) -> None:
            """Worker 오류 시 메인스레드에서 상태를 표시합니다."""
            try:
                self._lbl_status.setText("🔴 연결 실패 — docker ps | grep timescale 로 확인")
                self._lbl_status.setStyleSheet("color: #E74C3C; font-size: 8pt;")
                for attr in self._metric_labels:
                    lbl = self._metric_labels.get(attr)
                    if lbl:
                        lbl.setText("-")
                        lbl.setStyleSheet("color: #95A5A6; font-size: 11pt; font-weight: bold;")
                logger.debug("[OverviewDbTab] Worker 오류: %s", msg)
            finally:
                # Worker 참조/시그널 정리
                try:
                    if self._worker:
                        try:
                            self._worker.finished.disconnect(self._on_data_ready)
                            self._worker.error.disconnect(self._on_error)
                        except Exception:
                            pass
                        self._worker = None
                except Exception:
                    pass

        # ------------------------------------------------------------------
        # 생명 주기
        # ------------------------------------------------------------------

        def start_updates(self, interval_ms: int = 30_000) -> None:
            """자동 갱신 시작. 즉시 첫 갱신도 실행합니다."""
            self._timer.setInterval(max(5_000, int(interval_ms)))
            if not self._timer.isActive():
                self._timer.start()
            self._update()

        def stop_updates(self) -> None:
            """자동 갱신 중지."""
            self._timer.stop()

        def closeEvent(self, event) -> None:
            """위젯 닫힘 시 타이머와 Worker를 정리합니다."""
            self._timer.stop()
            if self._worker:
                try:
                    # 안전하게 시그널 분리 및 종료 시도
                    try:
                        self._worker.finished.disconnect(self._on_data_ready)
                        self._worker.error.disconnect(self._on_error)
                    except Exception:
                        pass
                    if self._worker.isRunning():
                        self._worker.quit()
                        self._worker.wait(2000)
                except Exception:
                    pass
                finally:
                    self._worker = None
            super().closeEvent(event)

else:
    class OverviewDbTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 폴백 스텁."""
        def __init__(self, conn_params=None, parent=None): pass
        def start_updates(self, interval_ms: int = 30_000) -> None: pass
        def stop_updates(self) -> None: pass