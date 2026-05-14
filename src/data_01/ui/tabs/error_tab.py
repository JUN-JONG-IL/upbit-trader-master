# -*- coding: utf-8 -*-
"""Tab 3: 에러 분석 제어 로직"""
from __future__ import annotations
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QMessageBox
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

from ._mixins import TableCopyMixin

# 에러 이유 표시 최대 글자 수
_MAX_REASON_LENGTH = 50


if _HAS_QT:
    class ErrorTab(TableCopyMixin, QWidget):
        """Tab 3: 에러 분석 — uic.loadUi() 기반 자립형 위젯"""

        def __init__(self, parent=None):
            super().__init__(parent)
            ui_path = os.path.join(os.path.dirname(__file__), "error_tab.ui")
            try:
                uic.loadUi(ui_path, self)
            except Exception as exc:
                logger.warning("[ErrorTab] UI 파일 로드 실패: %s", exc)

            self._setup_table_copy()
            self._timer = QTimer(self)
            self._timer.setInterval(3000)
            self._timer.timeout.connect(self._update_ui)

            # 새로고침 버튼 연결
            if hasattr(self, "btn_refresh_errors"):
                self.btn_refresh_errors.clicked.connect(self.refresh_errors)

            # Tick 재처리 버튼 연결
            if hasattr(self, "btn_reprocess_tick"):
                self.btn_reprocess_tick.clicked.connect(self._reprocess_tick_from_error_tab)

        def start_updates(self, interval_ms: int = 3000) -> None:
            self._timer.setInterval(max(3000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

        def _update_ui(self) -> None:
            """에러 분석 탭 자동 갱신 (3초마다)"""
            self.refresh_errors()


        def refresh_errors(self) -> None:
            """isolated_candles 테이블을 조회하여 에러 탭 UI를 갱신합니다."""
            try:
                from ..utils import get_timescale_connector
                connector = get_timescale_connector()
                if connector is None:
                    if hasattr(self, "label_error_count"):
                        self.label_error_count.setText("⚠ DB 연결 없음")
                    return
                conn = connector.get_connection(retry=False)
                try:
                    with conn.cursor() as cur:
                        try:
                            # 실제 컬럼명: time, isolation_reason, COALESCE for isolated_at (created_at 없음)
                            cur.execute(
                                "SELECT COALESCE(isolated_at, received_at), "
                                "       symbol, timeframe, isolation_reason "
                                "FROM isolated_candles "
                                "ORDER BY COALESCE(isolated_at, received_at) DESC "
                                "LIMIT 100"
                            )
                        except Exception as schema_exc:
                            logger.warning("[ErrorTab] 기본 스키마 쿼리 실패, 대체 쿼리 시도: %s", schema_exc)
                            try:
                                cur.execute(
                                    "SELECT time, symbol, NULL AS timeframe, isolation_reason "
                                    "FROM isolated_candles "
                                    "ORDER BY time DESC LIMIT 100"
                                )
                            except Exception as e2:
                                if hasattr(self, "label_error_count"):
                                    self.label_error_count.setText(f"⚠ 쿼리 실패: {e2}")
                                return
                        rows = cur.fetchall()
                    tbl = getattr(self, "table_errors", None)
                    if tbl is not None:
                        tbl.setRowCount(len(rows))
                        for i, row in enumerate(rows):
                            tbl.setItem(i, 0, QTableWidgetItem(str(row[0] or "")))
                            tbl.setItem(i, 1, QTableWidgetItem(str(row[1] or "")))
                            tbl.setItem(i, 2, QTableWidgetItem(str(row[2] or "")))
                            reason_full = str(row[3] or "")
                            reason_short = (
                                reason_full[:_MAX_REASON_LENGTH] + "..."
                                if len(reason_full) > _MAX_REASON_LENGTH
                                else reason_full
                            )
                            item_reason = QTableWidgetItem(reason_short)
                            item_reason.setToolTip(reason_full)
                            tbl.setItem(i, 3, item_reason)
                        tbl.resizeColumnsToContents()
                    if hasattr(self, "label_error_count"):
                        self.label_error_count.setText(f"총 에러: {len(rows):,} 건 [TimescaleDB → isolated_candles]")
                finally:
                    connector.put_connection(conn)
            except Exception as exc:
                logger.warning("[ErrorTab] 에러 조회 실패: %s", exc)
                if hasattr(self, "label_error_count"):
                    self.label_error_count.setText(f"⚠ 조회 실패: {exc}")

        def _reprocess_tick_from_error_tab(self) -> None:
            """에러 탭에서 Tick 재처리 실행 (isolated_reprocessor 연동)."""
            try:
                from ..dialogs.isolated_reprocessor import (
                    get_tick_isolated_count, reprocess_tick_isolated,
                )
            except Exception as exc:
                QMessageBox.critical(self, "오류", f"재처리 모듈 로드 실패:\n{exc}")
                return

            reprocessable = get_tick_isolated_count()
            if reprocessable == 0:
                QMessageBox.information(self, "알림", "재처리 가능한 tick 격리 데이터가 없습니다.")
                return

            answer = QMessageBox.question(
                self,
                "Tick 재처리 확인",
                f"재처리 가능한 격리 데이터 {reprocessable:,} 건을\n"
                "normalize_tick_to_candle()로 정규화하여\n"
                "staging_candles로 이동하시겠습니까?\n\n"
                "⚠ 이 작업은 되돌릴 수 없습니다.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

            if hasattr(self, "label_error_count"):
                self.label_error_count.setText("[재처리] Tick 재처리 중...")
            try:
                result = reprocess_tick_isolated(batch_size=1000)
                reprocessed = result.get("reprocessed", 0)
                failed = result.get("failed", 0)
                errors = result.get("errors", [])
                msg = f"재처리 완료: 성공 {reprocessed:,} 건, 실패 {failed:,} 건"
                if errors:
                    msg += f"\n오류 내용 (최대 5건):\n" + "\n".join(errors[:5])
                QMessageBox.information(self, "재처리 결과", msg)
                self.refresh_errors()
            except Exception as exc:
                QMessageBox.critical(self, "재처리 오류", str(exc))
                if hasattr(self, "label_error_count"):
                    self.label_error_count.setText(f"⚠ 재처리 실패: {exc}")

        def update_error_tab(self, ui_utils) -> None:
            """에러 분석 탭 갱신 (isolated_candles 최근 100건)"""
            tbl = getattr(self, "table_errors", None)
            if tbl is None:
                return
            try:
                conn = ui_utils.get_timescale_connector()
                if conn is None:
                    return
                try:
                    rows = conn.fetchall(
                        "SELECT isolated_at, symbol, timeframe, reason "
                        "FROM isolated_candles "
                        "ORDER BY isolated_at DESC "
                        "LIMIT 100"
                    )
                except Exception:
                    try:
                        rows = conn.fetchall(
                            "SELECT time, symbol, NULL AS timeframe, isolation_reason "
                            "FROM isolated_candles "
                            "ORDER BY time DESC "
                            "LIMIT 100"
                        )
                    except Exception as e:
                        logger.debug("[ErrorTab] 에러 탭 조회 실패: %s", e)
                        return
                tbl.setRowCount(len(rows))
                for i, row in enumerate(rows):
                    tbl.setItem(i, 0, QTableWidgetItem(str(row[0] or "")))
                    tbl.setItem(i, 1, QTableWidgetItem(str(row[1] or "")))
                    tbl.setItem(i, 2, QTableWidgetItem(str(row[2] or "")))
                    reason_full = str(row[3] or "")
                    reason_short = reason_full[:_MAX_REASON_LENGTH] + "..." if len(reason_full) > _MAX_REASON_LENGTH else reason_full
                    item_reason = QTableWidgetItem(reason_short)
                    item_reason.setToolTip(reason_full)
                    tbl.setItem(i, 3, item_reason)
                tbl.resizeColumnsToContents()
                if hasattr(self, "label_error_count"):
                    self.label_error_count.setText(f"총 에러: {len(rows)} 건")
            except Exception as exc:
                logger.error("[ErrorTab] 에러 탭 갱신 실패: %s", exc)

        def update_error_table(self, connector) -> None:
            """isolated_candles에서 최근 100개 에러를 테이블에 표시합니다."""
            tbl = getattr(self, "table_errors", None)
            if tbl is None:
                return
            try:
                conn = None
                try:
                    conn = connector.get_connection(retry=True)
                    with conn.cursor() as cur:
                        try:
                            cur.execute(
                                "SELECT symbol, time, isolation_reason "
                                "FROM public.isolated_candles "
                                "ORDER BY COALESCE(isolated_at, received_at) DESC "
                                "LIMIT 100"
                            )
                        except Exception:
                            cur.execute(
                                "SELECT symbol, time, isolation_reason "
                                "FROM public.isolated_candles "
                                "ORDER BY time DESC LIMIT 100"
                            )
                        rows = cur.fetchall()
                    tbl.setRowCount(len(rows))
                    for idx, r in enumerate(rows):
                        tbl.setItem(idx, 0, QTableWidgetItem(str(r[0] or "")))
                        tbl.setItem(idx, 1, QTableWidgetItem(str(r[1] or "")))
                        tbl.setItem(idx, 2, QTableWidgetItem(str(r[2] or "")))
                finally:
                    if conn is not None:
                        connector.put_connection(conn)
            except Exception as exc:
                logger.debug("[ErrorTab] 에러 로그 조회 실패: %s", exc)

else:
    class ErrorTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""
        def __init__(self, parent=None):
            pass
        def start_updates(self, interval_ms: int = 3000) -> None:
            pass
        def stop_updates(self) -> None:
            pass
        def update_error_tab(self, ui_utils) -> None:
            pass
        def update_error_table(self, connector) -> None:
            pass
        def refresh_errors(self) -> None:
            pass
        def _reprocess_tick_from_error_tab(self) -> None:
            pass
