# -*- coding: utf-8 -*-
"""Tab 7: 데이터 관리 제어 로직"""
from __future__ import annotations
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 허용된 테이블 목록 (SQL 인젝션 방지용 allowlist)
_ALLOWED_DELETE_TABLES = frozenset({
    "candles",
    "staging_candles",
    "isolated_candles",
    "gap_fill_queue",
})

# 테이블별 타임스탬프 컬럼 매핑 (코드 고정값 — 사용자 입력 없음)
_TABLE_TIME_COL: Dict[str, str] = {
    "candles": "time",
    "staging_candles": "time",
    "isolated_candles": "time",
    "gap_fill_queue": "created_at",
}


def _build_time_range_query(
    table_name: str,
    time_col: str,
    sql_verb: str,
    start_date: str,
    end_date: str,
    symbol: Optional[str],
) -> tuple:
    """time_col 기반 날짜 범위 쿼리와 파라미터를 반환합니다.

    table_name 및 time_col 은 모두 코드 고정값(allowlist/매핑)으로 결정되며
    사용자 입력은 파라미터 바인딩(%s)으로만 전달됩니다.
    """
    if symbol:
        sql = (
            f"{sql_verb} {table_name} "  # noqa: S608
            f"WHERE {time_col} >= %s AND {time_col} < %s AND symbol = %s"
        )
        params = (start_date, end_date, symbol)
    else:
        sql = (
            f"{sql_verb} {table_name} "  # noqa: S608
            f"WHERE {time_col} >= %s AND {time_col} < %s"
        )
        params = (start_date, end_date)
    return sql, params

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QObject, QTimer, pyqtSignal
    from PyQt5.QtWidgets import QWidget, QMessageBox
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if _HAS_QT:
    class DataMgmtTab(QWidget):
        """Tab 7: 데이터 관리"""

        ALLOWED_DELETE_TABLES = _ALLOWED_DELETE_TABLES
        TABLE_TIME_COL = _TABLE_TIME_COL

        def __init__(self, parent=None):
            super().__init__(parent)
            ui_path = os.path.join(os.path.dirname(__file__), "data_mgmt_tab.ui")
            try:
                uic.loadUi(ui_path, self)
            except Exception as exc:
                logger.warning("[DataMgmtTab] UI 파일 로드 실패: %s", exc)
            self._timer = QTimer(self)
            self._timer.setInterval(3000)
            self._timer.timeout.connect(self._update_ui)

        def start_updates(self, interval_ms: int = 3000) -> None:
            self._timer.setInterval(max(3000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

        def _update_ui(self) -> None:
            pass

        def update_data_mgmt_tab(self, pipeline_bg_cache: Dict, pipeline_bg_lock, ui_utils) -> None:
            """Tab 7: 데이터 관리 통계 갱신 (캐시 우선 사용)"""
            try:
                with pipeline_bg_lock:
                    cache = dict(pipeline_bg_cache)
                candles_stats = cache.get("table_candles") or ui_utils.get_table_stats("candles")
                staging_stats = cache.get("table_staging") or ui_utils.get_table_stats("staging_candles")
                isolated_stats = cache.get("table_isolated") or ui_utils.get_table_stats("isolated_candles")
                gap_stats = cache.get("table_gap") or ui_utils.get_table_stats("gap_fill_queue")

                if hasattr(self, "label_dm_candles_count"):
                    self.label_dm_candles_count.setText(
                        f"Candles: {candles_stats.get('row_count', 0):,} 건 "
                        f"({candles_stats.get('size_human', '--')})"
                    )
                if hasattr(self, "label_dm_staging_count"):
                    self.label_dm_staging_count.setText(f"Staging: {staging_stats.get('row_count', 0):,} 건")
                if hasattr(self, "label_dm_isolated_count"):
                    self.label_dm_isolated_count.setText(f"Isolated: {isolated_stats.get('row_count', 0):,} 건")
                if hasattr(self, "label_dm_gap_count"):
                    realtime_gap = cache.get("gap_queue_count")
                    if realtime_gap is None:
                        realtime_gap = ui_utils.get_gap_queue_count_realtime()
                    self.label_dm_gap_count.setText(f"Gap Fill Queue: {realtime_gap:,} 건")
            except Exception as exc:
                logger.debug("[DataMgmtTab] 데이터 관리 탭 갱신 실패: %s", exc)

        def on_delete_preview_clicked(self, ui_utils) -> None:
            """삭제 미리보기 버튼 클릭"""
            try:
                table = getattr(self, "combo_delete_table", None)
                table_name = table.currentText() if table else ""
                if table_name not in self.ALLOWED_DELETE_TABLES:
                    QMessageBox.warning(self, "오류", f"허용되지 않은 테이블: {table_name}")
                    return

                start_date = self.date_delete_start.date().toString("yyyy-MM-dd") if hasattr(self, "date_delete_start") else ""
                end_date = self.date_delete_end.date().toString("yyyy-MM-dd") if hasattr(self, "date_delete_end") else ""
                symbol = self.edit_delete_symbol.text().strip() if hasattr(self, "edit_delete_symbol") else ""

                conn = ui_utils.get_timescale_connector()
                if conn is None:
                    QMessageBox.warning(self, "오류", "DB 연결 실패")
                    return

                # table_name: _ALLOWED_DELETE_TABLES 로 검증된 고정 식별자
                # time_col: _TABLE_TIME_COL 매핑에서 코드 고정값으로 결정 (사용자 입력 없음)
                time_col = self.TABLE_TIME_COL.get(table_name, "time")
                count = 0
                try:
                    sql, params = _build_time_range_query(
                        table_name, time_col, "SELECT COUNT(*) FROM", start_date, end_date, symbol
                    )
                    rows = conn.fetchall(sql, params)
                    count = int(rows[0][0]) if rows and rows[0][0] is not None else 0
                except Exception as col_exc:
                    logger.debug("[DataMgmtTab] 미리보기 1차 조회 실패, time 컬럼으로 재시도: %s", col_exc)
                    try:
                        sql, params = _build_time_range_query(
                            table_name, "time", "SELECT COUNT(*) FROM", start_date, end_date, symbol
                        )
                        rows = conn.fetchall(sql, params)
                        count = int(rows[0][0]) if rows and rows[0][0] is not None else 0
                    except Exception as exc2:
                        QMessageBox.critical(self, "오류", f"미리보기 조회 실패:\n{exc2}")
                        return

                size_rows = conn.fetchall(
                    "SELECT pg_size_pretty(pg_total_relation_size(%s))",
                    (table_name,),
                )
                size_str = str(size_rows[0][0]) if size_rows and size_rows[0][0] else "--"

                if hasattr(self, "label_delete_preview"):
                    self.label_delete_preview.setText(
                        f"[OK] 삭제 대상: {count:,} 건\n"
                        f"📦 테이블 크기: {size_str}"
                    )
            except Exception as exc:
                logger.error("[DataMgmtTab] 삭제 미리보기 실패: %s", exc)
                QMessageBox.critical(self, "오류", f"미리보기 실패:\n{exc}")

        def on_delete_execute_clicked(self, ui_utils) -> None:
            """삭제 실행 버튼 클릭"""
            try:
                table = getattr(self, "combo_delete_table", None)
                table_name = table.currentText() if table else ""
                if table_name not in self.ALLOWED_DELETE_TABLES:
                    QMessageBox.warning(self, "오류", f"허용되지 않은 테이블: {table_name}")
                    return

                reply = QMessageBox.question(
                    self, "삭제 확인",
                    f"테이블 [{table_name}] 데이터를 정말 삭제하시겠습니까?\n"
                    "이 작업은 되돌릴 수 없습니다!",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return

                start_date = self.date_delete_start.date().toString("yyyy-MM-dd") if hasattr(self, "date_delete_start") else ""
                end_date = self.date_delete_end.date().toString("yyyy-MM-dd") if hasattr(self, "date_delete_end") else ""
                symbol = self.edit_delete_symbol.text().strip() if hasattr(self, "edit_delete_symbol") else ""

                conn = ui_utils.get_timescale_connector()
                if conn is None:
                    QMessageBox.warning(self, "오류", "DB 연결 실패")
                    return

                # table_name: _ALLOWED_DELETE_TABLES 로 검증된 고정 식별자
                # time_col: _TABLE_TIME_COL 매핑에서 코드 고정값으로 결정 (사용자 입력 없음)
                time_col = self.TABLE_TIME_COL.get(table_name, "time")
                try:
                    sql, params = _build_time_range_query(
                        table_name, time_col, "DELETE FROM", start_date, end_date, symbol
                    )
                    conn.execute(sql, params)
                except Exception as col_exc:
                    logger.debug("[DataMgmtTab] 삭제 1차 시도 실패, time 컬럼으로 재시도: %s", col_exc)
                    sql, params = _build_time_range_query(
                        table_name, "time", "DELETE FROM", start_date, end_date, symbol
                    )
                    conn.execute(sql, params)

                logger.info(
                    "[DataMgmtTab] 데이터 삭제 완료: table=%s start=%s end=%s symbol=%s",
                    table_name, start_date, end_date, symbol or "(전체)",
                )
                QMessageBox.information(self, "완료", "삭제 완료!")
                if hasattr(self, "label_delete_preview"):
                    self.label_delete_preview.setText("미리보기 버튼을 클릭하세요.")
            except Exception as exc:
                logger.error("[DataMgmtTab] 삭제 실행 실패: %s", exc)
                QMessageBox.critical(self, "오류", f"삭제 실패:\n{exc}")

else:
    class DataMgmtTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""
        ALLOWED_DELETE_TABLES = _ALLOWED_DELETE_TABLES
        TABLE_TIME_COL = _TABLE_TIME_COL

        def __init__(self, parent=None):
            pass
        def start_updates(self, interval_ms: int = 3000) -> None:
            pass
        def stop_updates(self) -> None:
            pass
