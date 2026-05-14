# -*- coding: utf-8 -*-
"""
격리 데이터 상세 분석 다이얼로그 (isolated_detail_dialog.py)

TimescaleDB의 isolated_candles 테이블에서 격리 사유별 통계와
상세 레코드를 조회하여 표시합니다.

기능:
- 격리 사유별 통계 (OHLCV_INVALID, TIMESTAMP_DUPLICATE, PRICE_SPIKE 등)
- 심볼/사유/기간별 필터링
- 행 더블클릭 → 상세 팝업 (OHLCV + raw_data JSON 뷰어)
- 격리 사유별 색상 코딩
- CSV 내보내기
- Tick 재처리 (normalize_tick_to_candle → staging_candles)
- 전체 삭제 / 선택 삭제
- 30초 자동 갱신
"""
from __future__ import annotations

import csv
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QColor
    from PyQt5.QtWidgets import (
        QDialog, QTableWidgetItem, QFileDialog, QMessageBox,
        QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton,
        QGroupBox, QFormLayout,
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

# DB 조회 함수는 별도 모듈에서 임포트 (SRP 분리)
from .isolated_queries import (
    query_reason_stats as _query_reason_stats,
    query_isolated_rows as _query_isolated_rows,
    delete_all_from_db as _delete_all_from_db,
    get_db_conn as _get_db_conn,
    DEFAULT_QUERY_LIMIT as _DEFAULT_QUERY_LIMIT,
    PERIOD_FILTER_MAP as _PERIOD_FILTER_MAP,
)

# 30초 자동 갱신 간격 (밀리초)
_AUTO_REFRESH_INTERVAL_MS: int = 30_000
# Tick 재처리 배치 크기
_REPROCESS_BATCH_SIZE: int = 1_000
# UI 파일 경로
_UI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "isolated_detail_dialog.ui")

# 격리 사유별 색상 (배경색)
_REASON_COLORS: Dict[str, str] = {
    "price_negative": "#FFCCCC",
    "ohlc_invalid": "#FFCCCC",
    "OHLCV_INVALID": "#FFCCCC",
    "change_rate_extreme": "#FFE0B2",
    "volume_negative": "#FFE0B2",
    "VOLUME_ANOMALY": "#FFE0B2",
    "PRICE_SPIKE": "#FFE0B2",
    "timestamp_future": "#FFFDE7",
    "symbol_unknown": "#FFFDE7",
    "TIMESTAMP_DUPLICATE": "#FFFDE7",
}

# ============================================================
# 다이얼로그 클래스
# ============================================================

if _HAS_QT:
    class IsolatedDetailDialog(QDialog):
        """격리 데이터 상세 분석 다이얼로그.

        TimescaleDB isolated_candles 테이블에서 격리 사유별 통계 및
        상세 레코드를 조회하여 표시합니다.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowModality(Qt.NonModal)
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[IsolatedDetailDialog] UI 로드 실패: %s", exc)

            self._all_rows: List[tuple] = []
            # 현재 활성 필터 조건 저장 (전체 삭제 시 사용)
            self._current_symbol_filter: Optional[str] = None
            self._current_reason_filter: Optional[str] = None
            self._current_period_hours: Optional[int] = None

            # 버튼 연결
            if hasattr(self, "btn_close"):
                self.btn_close.clicked.connect(self.close)
            if hasattr(self, "btn_filter_apply"):
                self.btn_filter_apply.clicked.connect(self._apply_filter)
            if hasattr(self, "btn_export_csv"):
                self.btn_export_csv.clicked.connect(self._export_csv)
            if hasattr(self, "btn_refresh"):
                self.btn_refresh.clicked.connect(self._load_data)
            if hasattr(self, "btn_delete_selected"):
                self.btn_delete_selected.clicked.connect(self._delete_selected_rows)
            if hasattr(self, "btn_delete_all"):
                self.btn_delete_all.clicked.connect(self._delete_all_rows)
            if hasattr(self, "btn_reprocess_tick"):
                self.btn_reprocess_tick.clicked.connect(self._reprocess_tick_isolated)

            # 필터 Enter 키 연결
            if hasattr(self, "lineEdit_symbol_filter"):
                self.lineEdit_symbol_filter.returnPressed.connect(self._apply_filter)

            # 행 더블클릭 → 상세 팝업
            tbl = getattr(self, "table_isolated_detail", None)
            if tbl is not None:
                tbl.doubleClicked.connect(self._on_row_double_clicked)

            # 30초 자동 갱신 타이머
            self._auto_refresh_timer = QTimer(self)
            self._auto_refresh_timer.setInterval(_AUTO_REFRESH_INTERVAL_MS)
            self._auto_refresh_timer.timeout.connect(self._load_data)
            self._auto_refresh_timer.start()

            # 초기 데이터 로드 (200ms 지연)
            QTimer.singleShot(200, self._load_data)

        def closeEvent(self, event) -> None:
            """다이얼로그 닫힐 때 타이머 중지."""
            self._auto_refresh_timer.stop()
            super().closeEvent(event)

        # ------------------------------------------------------------------
        # 데이터 로드
        # ------------------------------------------------------------------
        def _load_data(self) -> None:
            """격리 사유별 통계 및 상세 레코드 로드 (필터 없이 전체 조회)."""
            self._set_status("데이터 조회 중...")

            stats, err = _query_reason_stats()
            if err:
                self._set_status(f"⚠ 통계 조회 실패: {err}")
            else:
                self._update_reason_stats(stats)
                # 사유 필터 콤보에 실제 DB 사유 목록 반영
                self._populate_reason_combo(list(stats.keys()))

            rows, err2 = _query_isolated_rows(
                symbol_filter=None, reason_filter=None, period_hours=None
            )
            if err2:
                self._set_status(f"⚠ 상세 조회 실패: {err2}")
                return
            self._all_rows = rows
            self._render_table(rows)

            # 재처리 가능 건수 계산하여 상태바 표시
            self._update_status_with_stats(len(rows))

            # 마지막 갱신 시각 표시
            now_str = datetime.now().strftime("%H:%M:%S")
            lbl_refresh = getattr(self, "label_last_refresh", None)
            if lbl_refresh is not None:
                lbl_refresh.setText(f"🕐 마지막 갱신: {now_str}")

        # ------------------------------------------------------------------
        # 필터 적용
        # ------------------------------------------------------------------
        def _apply_filter(self) -> None:
            """필터 조건에 따라 테이블 재조회. 빈 검색어 = 전체 조회."""
            symbol: Optional[str] = None
            reason: Optional[str] = None
            period_hours: Optional[int] = None

            if hasattr(self, "lineEdit_symbol_filter"):
                raw = self.lineEdit_symbol_filter.text().strip().upper()
                if raw:
                    symbol = raw
            if hasattr(self, "combo_reason_filter"):
                txt = self.combo_reason_filter.currentText()
                if txt and txt not in ("전체", ""):
                    reason = txt
            if hasattr(self, "combo_period_filter"):
                period_hours = _PERIOD_FILTER_MAP.get(self.combo_period_filter.currentText())

            self._set_status("조회 중...")
            rows, err = _query_isolated_rows(
                symbol_filter=symbol,
                reason_filter=reason,
                period_hours=period_hours,
            )
            if err:
                self._set_status(f"⚠ 조회 실패: {err}")
                return
            self._all_rows = rows  # 더블클릭 팝업에서 filtered rows 사용
            self._render_table(rows)
            filter_desc = []
            if symbol:
                filter_desc.append(f"심볼={symbol}")
            if reason:
                filter_desc.append(f"사유={reason}")
            if period_hours:
                filter_desc.append(f"최근 {period_hours}시간")
            filter_str = ", ".join(filter_desc) if filter_desc else "전체"
            self._set_status(f"필터 결과: {len(rows):,} 건 ({filter_str})")

            # 현재 필터 조건 저장 (전체 삭제 시 사용)
            self._current_symbol_filter = symbol
            self._current_reason_filter = reason
            self._current_period_hours = period_hours

        # ------------------------------------------------------------------
        # 상태바 통계 표시
        # ------------------------------------------------------------------
        def _update_status_with_stats(self, displayed: int) -> None:
            """상태바에 '격리 건 / 재처리 가능 건 / 처리 불가 건' 표시."""
            try:
                from .isolated_reprocessor import get_isolated_stats
                stats = get_isolated_stats()
                total = stats.get("total", 0)
                reprocessable = stats.get("reprocessable", 0)
                non_reprocessable = stats.get("non_reprocessable", 0)
                self._set_status(
                    f"표시: {displayed:,} 건 | "
                    f"전체 격리: {total:,} 건 | "
                    f"재처리 가능: {reprocessable:,} 건 | "
                    f"처리 불가: {non_reprocessable:,} 건"
                )
            except Exception:
                self._set_status(f"총 {displayed:,} 건 표시 중 (최대 {_DEFAULT_QUERY_LIMIT}건)")

        # ------------------------------------------------------------------
        # Tick 재처리
        # ------------------------------------------------------------------
        def _reprocess_tick_isolated(self) -> None:
            """격리된 tick 데이터를 normalize_tick_to_candle()로 재처리하여 staging_candles로 이동."""
            from PyQt5.QtWidgets import QProgressDialog
            try:
                from .isolated_reprocessor import get_tick_isolated_count, reprocess_tick_isolated
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

            self._set_status("🔄 Tick 재처리 중... (최대 1,000건)")
            try:
                result = reprocess_tick_isolated(batch_size=_REPROCESS_BATCH_SIZE)
                reprocessed = result.get("reprocessed", 0)
                failed = result.get("failed", 0)
                errors = result.get("errors", [])
                msg = f"재처리 완료: 성공 {reprocessed:,} 건, 실패 {failed:,} 건"
                if errors:
                    msg += f"\n오류 내용 (최대 5건):\n" + "\n".join(errors[:5])
                QMessageBox.information(self, "재처리 결과", msg)
                # 재처리 후 데이터 새로고침
                self._load_data()
            except Exception as exc:
                QMessageBox.critical(self, "재처리 오류", str(exc))
                self._set_status(f"⚠ 재처리 실패: {exc}")

        # ------------------------------------------------------------------
        # 전체 삭제
        # ------------------------------------------------------------------
        def _delete_all_rows(self) -> None:
            """현재 필터 조건에 해당하는 모든 레코드를 DB에서 삭제합니다."""
            # 현재 테이블 표시 건수 확인
            tbl = getattr(self, "table_isolated_detail", None)
            row_count = tbl.rowCount() if tbl is not None else 0

            if row_count == 0:
                QMessageBox.information(self, "알림", "삭제할 데이터가 없습니다.")
                return

            # 필터 조건 설명
            filter_parts = []
            if self._current_symbol_filter:
                filter_parts.append(f"심볼={self._current_symbol_filter}")
            if self._current_reason_filter:
                filter_parts.append(f"사유={self._current_reason_filter}")
            if self._current_period_hours:
                filter_parts.append(f"최근 {self._current_period_hours}시간")
            filter_desc = ", ".join(filter_parts) if filter_parts else "전체 (필터 없음)"

            answer = QMessageBox.question(
                self,
                "전체 삭제 확인",
                f"필터 조건 [{filter_desc}] 에 해당하는\n"
                f"모든 격리 데이터를 삭제하시겠습니까?\n\n"
                f"⚠ 이 작업은 되돌릴 수 없습니다.\n"
                f"(표시된 {row_count:,} 건 이상이 삭제될 수 있습니다)",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

            deleted, err_msg = _delete_all_from_db(
                symbol_filter=self._current_symbol_filter,
                reason_filter=self._current_reason_filter,
                period_hours=self._current_period_hours,
            )
            if err_msg:
                self._set_status(f"⚠ 전체 삭제 실패: {err_msg}")
                QMessageBox.warning(self, "삭제 실패", err_msg)
            else:
                self._set_status(f"✅ 전체 삭제 완료: {deleted:,} 건")
                self._load_data()

        # ------------------------------------------------------------------
        # UI 갱신
        # ------------------------------------------------------------------
        def _populate_reason_combo(self, reasons: List[str]) -> None:
            """격리 사유 콤보박스를 실제 DB 사유 목록으로 갱신."""
            combo = getattr(self, "combo_reason_filter", None)
            if combo is None:
                return
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("전체")
            for r in sorted(reasons):
                combo.addItem(str(r))
            # 이전 선택값 복원
            idx = combo.findText(current)
            combo.setCurrentIndex(max(0, idx))
            combo.blockSignals(False)

        def _update_reason_stats(self, stats: Dict[str, int]) -> None:
            """격리 사유별 통계 레이블 갱신."""
            mapping = {
                "OHLCV_INVALID": "label_reason_ohlcv",
                "TIMESTAMP_DUPLICATE": "label_reason_ts_dup",
                "PRICE_SPIKE": "label_reason_price_spike",
                "VOLUME_ANOMALY": "label_reason_volume",
            }
            total = 0
            for reason, widget_name in mapping.items():
                count = stats.get(reason, 0)
                total += count
                lbl = getattr(self, widget_name, None)
                if lbl is not None:
                    lbl.setText(f"{count:,} 건")

            known_keys = set(mapping.keys())
            other = sum(v for k, v in stats.items() if k not in known_keys)
            total += other
            lbl_other = getattr(self, "label_reason_other", None)
            if lbl_other is not None:
                lbl_other.setText(f"{other:,} 건")
            lbl_total = getattr(self, "label_reason_total", None)
            if lbl_total is not None:
                lbl_total.setText(f"{total:,} 건")

        def _render_table(self, rows: List[tuple]) -> None:
            """상세 테이블 렌더링 (9컬럼: 심볼, 시간, 격리사유, 시가, 고가, 저가, 종가, 거래량, 격리시간)."""
            tbl = getattr(self, "table_isolated_detail", None)
            if tbl is None:
                return
            tbl.setRowCount(len(rows))
            for i, row in enumerate(rows):
                # row = (symbol, time, isolation_reason, open, high, low, close, volume, isolated_at, raw_data)
                # 테이블에는 raw_data 제외한 9컬럼 표시
                display_cols = row[:9]
                reason = str(row[2]) if len(row) > 2 and row[2] is not None else ""
                bg_color = _REASON_COLORS.get(reason)
                for j, val in enumerate(display_cols):
                    if val is None:
                        text = ""
                    elif isinstance(val, float):
                        text = f"{val:,.8f}".rstrip('0').rstrip('.')
                    else:
                        text = str(val)
                    item = QTableWidgetItem(text)
                    if bg_color:
                        item.setBackground(QColor(bg_color))
                    tbl.setItem(i, j, item)
            tbl.resizeColumnsToContents()

        def _set_status(self, msg: str) -> None:
            """상태 레이블 갱신."""
            lbl = getattr(self, "label_status", None)
            if lbl is not None:
                lbl.setText(msg)

        # ------------------------------------------------------------------
        # 행 더블클릭 → 상세 팝업
        # ------------------------------------------------------------------
        def _on_row_double_clicked(self, index) -> None:
            """행 더블클릭 시 OHLCV + raw_data 상세 팝업 표시."""
            tbl = getattr(self, "table_isolated_detail", None)
            if tbl is None:
                return
            row_idx = index.row()
            if row_idx < 0 or row_idx >= len(self._all_rows):
                # 필터 조회 후 _all_rows와 불일치 가능 → 테이블에서 직접 읽기
                self._show_row_popup_from_table(tbl, row_idx)
                return
            self._show_row_popup(self._all_rows[row_idx])

        def _show_row_popup_from_table(self, tbl, row_idx: int) -> None:
            """테이블에서 직접 읽어 팝업 표시 (필터 결과용)."""
            cols = tbl.columnCount()
            vals = [
                tbl.item(row_idx, j).text() if tbl.item(row_idx, j) else ""
                for j in range(cols)
            ]
            self._show_row_popup_raw(
                symbol=vals[0] if cols > 0 else "",
                time=vals[1] if cols > 1 else "",
                reason=vals[2] if cols > 2 else "",
                open_=vals[3] if cols > 3 else "",
                high=vals[4] if cols > 4 else "",
                low=vals[5] if cols > 5 else "",
                close=vals[6] if cols > 6 else "",
                volume=vals[7] if cols > 7 else "",
                isolated_at=vals[8] if cols > 8 else "",
                raw_data_text="",
            )

        def _show_row_popup(self, row: tuple) -> None:
            """tuple row로 팝업 표시."""
            symbol = str(row[0]) if len(row) > 0 and row[0] is not None else ""
            time_ = str(row[1]) if len(row) > 1 and row[1] is not None else ""
            reason = str(row[2]) if len(row) > 2 and row[2] is not None else ""
            open_ = str(row[3]) if len(row) > 3 and row[3] is not None else ""
            high = str(row[4]) if len(row) > 4 and row[4] is not None else ""
            low = str(row[5]) if len(row) > 5 and row[5] is not None else ""
            close = str(row[6]) if len(row) > 6 and row[6] is not None else ""
            volume = str(row[7]) if len(row) > 7 and row[7] is not None else ""
            isolated_at = str(row[8]) if len(row) > 8 and row[8] is not None else ""
            raw_data = row[9] if len(row) > 9 else None
            try:
                if isinstance(raw_data, dict):
                    raw_text = json.dumps(raw_data, ensure_ascii=False, indent=2)
                elif isinstance(raw_data, str):
                    parsed = json.loads(raw_data)
                    raw_text = json.dumps(parsed, ensure_ascii=False, indent=2)
                else:
                    raw_text = str(raw_data) if raw_data is not None else ""
            except Exception:
                raw_text = str(raw_data) if raw_data is not None else ""

            self._show_row_popup_raw(symbol, time_, reason, open_, high, low, close, volume, isolated_at, raw_text)

        def _show_row_popup_raw(
            self, symbol, time, reason, open_, high, low, close, volume, isolated_at, raw_data_text
        ) -> None:
            """상세 팝업 다이얼로그 빌드 및 표시."""
            dlg = QDialog(self)
            dlg.setWindowTitle(f"🔍 격리 상세 — {symbol}")
            dlg.setMinimumWidth(600)
            dlg.setMinimumHeight(500)
            layout = QVBoxLayout(dlg)

            # OHLCV 정보 그룹
            grp = QGroupBox("📊 OHLCV 상세 정보")
            form = QFormLayout(grp)
            form.addRow("심볼:", QLabel(symbol))
            form.addRow("캔들 시간:", QLabel(time))
            form.addRow("격리 시간:", QLabel(isolated_at))
            reason_lbl = QLabel(reason)
            reason_lbl.setStyleSheet("font-weight: bold; font-size: 14px; color: red;")
            form.addRow("격리 사유:", reason_lbl)
            form.addRow("시가 (Open):", QLabel(open_))
            form.addRow("고가 (High):", QLabel(high))
            form.addRow("저가 (Low):", QLabel(low))
            form.addRow("종가 (Close):", QLabel(close))
            form.addRow("거래량 (Volume):", QLabel(volume))
            layout.addWidget(grp)

            # raw_data JSON 뷰어
            if raw_data_text:
                grp_raw = QGroupBox("📄 원본 데이터 (raw_data)")
                raw_layout = QVBoxLayout(grp_raw)
                txt_edit = QTextEdit()
                txt_edit.setReadOnly(True)
                txt_edit.setPlainText(raw_data_text)
                txt_edit.setMinimumHeight(150)
                raw_layout.addWidget(txt_edit)
                layout.addWidget(grp_raw)

            btn_close = QPushButton("✖ 닫기")
            btn_close.clicked.connect(dlg.close)
            layout.addWidget(btn_close)
            dlg.exec_()

        # ------------------------------------------------------------------
        # 선택 행 삭제
        # ------------------------------------------------------------------
        def _delete_selected_rows(self) -> None:
            """선택된 행을 DB(isolated_candles)에서 삭제합니다."""
            tbl = getattr(self, "table_isolated_detail", None)
            if tbl is None:
                return

            selected_rows = sorted(set(idx.row() for idx in tbl.selectedIndexes()))
            if not selected_rows:
                QMessageBox.information(self, "알림", "삭제할 행을 선택해 주세요.")
                return

            answer = QMessageBox.question(
                self,
                "삭제 확인",
                f"선택된 {len(selected_rows)}건을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

            # 삭제 대상 (symbol, time) 수집
            targets: List[Tuple[str, str]] = []
            for row in selected_rows:
                sym_item = tbl.item(row, 0)
                time_item = tbl.item(row, 1)
                if sym_item and time_item:
                    targets.append((sym_item.text(), time_item.text()))

            if not targets:
                return

            deleted, failed = self._delete_from_db(targets)
            self._set_status(f"삭제 완료: {deleted}건 / 실패: {failed}건")
            # 삭제 후 데이터 재조회
            self._load_data()

        def _delete_from_db(self, targets: List[Tuple[str, str]]) -> Tuple[int, int]:
            """isolated_candles 테이블에서 (symbol, time) 기준으로 삭제.

            Returns:
                (삭제 성공 건수, 실패 건수)
            """
            deleted = 0
            failed = 0
            conn = _get_db_conn()
            if conn is None:
                logger.warning("[IsolatedDetailDialog] DB 연결 실패 — 삭제 불가")
                return 0, len(targets)
            try:
                with conn.cursor() as cur:
                    for symbol, time_str in targets:
                        try:
                            # datetime 파싱 후 정확한 타임스탬프 비교
                            try:
                                time_dt = datetime.fromisoformat(time_str.strip())
                            except ValueError:
                                # 파싱 실패 시 문자열 앞부분(초 단위)으로 범위 비교
                                cur.execute(
                                    "DELETE FROM isolated_candles "
                                    "WHERE symbol = %s AND time::text LIKE %s",
                                    (symbol, f"{time_str[:19]}%"),
                                )
                            else:
                                cur.execute(
                                    "DELETE FROM isolated_candles "
                                    "WHERE symbol = %s AND time = %s",
                                    (symbol, time_dt),
                                )
                            if cur.rowcount > 0:
                                deleted += cur.rowcount
                        except Exception as exc:
                            logger.warning(
                                "[IsolatedDetailDialog] 행 삭제 실패: symbol=%s time=%s error=%s",
                                symbol, time_str, exc,
                            )
                            failed += 1
                conn.commit()
            except Exception as exc:
                logger.error("[IsolatedDetailDialog] 삭제 트랜잭션 실패: %s", exc)
                failed += len(targets)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            return deleted, failed

        # ------------------------------------------------------------------
        # CSV 내보내기
        # ------------------------------------------------------------------
        def _export_csv(self) -> None:
            """현재 테이블 데이터를 CSV 파일로 저장."""
            tbl = getattr(self, "table_isolated_detail", None)
            if tbl is None or tbl.rowCount() == 0:
                QMessageBox.information(self, "알림", "내보낼 데이터가 없습니다.")
                return

            filename, _ = QFileDialog.getSaveFileName(
                self, "CSV 파일 저장", "isolated_candles.csv", "CSV 파일 (*.csv)"
            )
            if not filename:
                return

            try:
                headers = [
                    tbl.horizontalHeaderItem(c).text()
                    for c in range(tbl.columnCount())
                ]
                with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    for r in range(tbl.rowCount()):
                        row_data = [
                            tbl.item(r, c).text() if tbl.item(r, c) else ""
                            for c in range(tbl.columnCount())
                        ]
                        writer.writerow(row_data)
                self._set_status(f"✅ CSV 저장 완료: {filename}")
            except Exception as exc:
                QMessageBox.warning(self, "저장 실패", str(exc))
                logger.warning("[IsolatedDetailDialog] CSV 저장 실패: %s", exc)

else:
    class IsolatedDetailDialog:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스."""

        def __init__(self, parent=None):
            pass

        def exec_(self):
            pass

        def show(self):
            pass
