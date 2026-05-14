# -*- coding: utf-8 -*-
"""
DB 뷰어 데이터 조회 + 콤보 로직 Mixin (db_viewer_logic.py)

DBViewerLogicMixin:
  - 자산군/거래소/타임프레임/기간 콤보 초기값 설정
  - 심볼 콤보 로드 및 필터
  - 조회 / 테이블 채우기
  - CSV 내보내기
"""
from __future__ import annotations

import csv
import logging
import time as _time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QFileDialog, QTableWidgetItem
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
ASSET_CLASSES = ["전체", "암호화폐", "국내주식", "해외주식", "파생상품/선물"]

EXCHANGE_MAP: Dict[str, List[str]] = {
    "전체":         ["전체"],
    "암호화폐":     ["전체", "업비트", "빗썸", "바이낸스"],
    "국내주식":     ["전체", "KRX/코스피", "코스닥"],
    "해외주식":     ["전체", "NYSE", "NASDAQ"],
    "파생상품/선물": ["전체", "CME", "CBOE"],
}

_TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"]

_PERIOD_OPTIONS = [
    ("최근 100건",   {"type": "limit", "limit": 100}),
    ("최근 1,000건 [TimescaleDB]", {"type": "limit", "limit": 1000}),
    ("최근 3,000건", {"type": "limit", "limit": 3000}),
    ("최근 5,000건 [TimescaleDB]", {"type": "limit", "limit": 5000}),
    ("오늘",         {"type": "today"}),
    ("최근 7일",     {"type": "days",  "days": 7}),
    ("최근 30일",    {"type": "days",  "days": 30}),
]

_DATA_SOURCES = [
    "candles",
    "staging_candles",
    "cagg_candles_5m",
    "cagg_candles_15m",
    "cagg_candles_1h",
    "cagg_candles_1d",
]

_COL_HEADERS = ["시각", "시가", "고가", "저가", "종가", "거래량", "거래대금", "체결수", "완성"]

# 타임프레임 → 분 단위 매핑 (백필 검증용)
_TF_MINUTES: Dict[str, int] = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15,
    "30m": 30, "1h": 60, "4h": 240, "1d": 1440,
}

if _HAS_QT:
    class DBViewerLogicMixin:
        """DB 데이터 뷰어 데이터 조회 및 콤보 로직 Mixin."""

        # ------------------------------------------------------------------
        # 콤보 초기화
        # ------------------------------------------------------------------

        def _populate_combos(self) -> None:
            """자산군/거래소/타임프레임/기간 콤보 초기값 설정."""
            for attr, items in [
                ("combo_asset_class", ASSET_CLASSES),
                ("combo_timeframe",   _TIMEFRAMES),
            ]:
                cb = getattr(self, attr, None)
                if cb is not None:
                    cb.clear()
                    cb.addItems(items)

            cb_period = getattr(self, "combo_period", None)
            if cb_period is not None:
                cb_period.clear()
                cb_period.addItems([label for label, _ in _PERIOD_OPTIONS])

            cb_ds = getattr(self, "combo_data_source", None)
            if cb_ds is not None:
                cb_ds.clear()
                cb_ds.addItems(_DATA_SOURCES)

            self._on_asset_changed()

        def _load_symbols_for_combo(self) -> None:
            """candle_queries 기반으로 심볼 콤보를 채웁니다."""
            try:
                from ..utils.candle_queries import query_symbols_with_stats
                symbol_stats = query_symbols_with_stats()
                self._all_symbol_stats = symbol_stats
                self._all_symbols = [s["symbol"] for s in symbol_stats]
            except Exception as exc:
                logger.warning("[DBViewerLogic] 심볼 로드 실패: %s", exc)
                self._all_symbol_stats = []
                self._all_symbols = []

            if not self._all_symbols:
                self._all_symbols = self._get_default_symbols()

            self._refresh_symbol_combo(self._all_symbols)

        # ------------------------------------------------------------------
        # 자산군/거래소 변경
        # ------------------------------------------------------------------

        def _on_asset_changed(self, index: int = 0) -> None:
            """자산군 변경 시 거래소 콤보 동기화."""
            combo_ac = getattr(self, "combo_asset_class", None)
            combo_ex = getattr(self, "combo_exchange", None)
            if combo_ac is None or combo_ex is None:
                return
            exchanges = EXCHANGE_MAP.get(combo_ac.currentText(), ["전체"])
            combo_ex.blockSignals(True)
            combo_ex.clear()
            combo_ex.addItems(exchanges)
            combo_ex.blockSignals(False)
            self._filter_symbols_by_asset_exchange()

        def _on_exchange_changed(self, index: int = 0) -> None:
            """거래소 변경 시 심볼 콤보 필터링."""
            self._filter_symbols_by_asset_exchange()

        def _filter_symbols_by_asset_exchange(self) -> None:
            """자산군/거래소 기준으로 심볼 콤보를 필터링합니다."""
            all_stats = getattr(self, "_all_symbol_stats", [])
            if not all_stats:
                return

            combo_ac = getattr(self, "combo_asset_class", None)
            combo_ex = getattr(self, "combo_exchange", None)
            asset = combo_ac.currentText() if combo_ac else "전체"
            exchange = combo_ex.currentText() if combo_ex else "전체"

            filtered = []
            for s in all_stats:
                if asset != "전체" and s.get("asset_class") != asset:
                    continue
                if exchange != "전체" and s.get("exchange") != exchange:
                    continue
                filtered.append(s["symbol"])

            if not filtered:
                filtered = [s["symbol"] for s in all_stats]

            self._refresh_symbol_combo(filtered)

        # ------------------------------------------------------------------
        # 검색
        # ------------------------------------------------------------------

        def _on_search(self, text: str) -> None:
            """검색어로 심볼 콤보를 필터링합니다 (한글/초성/영문/영문명 모두 지원)."""
            all_symbols = getattr(self, "_all_symbols", [])
            if not text:
                self._refresh_symbol_combo(all_symbols)
                self._update_search_result_label(0, show=False)
                return

            try:
                from ..utils.symbol_search import filter_symbols, build_name_map, build_name_en_map

                # 캐시 (최초 1회만 빌드)
                name_map = getattr(self, "_name_map", None)
                if name_map is None:
                    self._name_map = build_name_map()
                    name_map = self._name_map

                name_en_map = getattr(self, "_name_en_map", None)
                if name_en_map is None:
                    self._name_en_map = build_name_en_map()
                    name_en_map = self._name_en_map

                filtered = filter_symbols(text, all_symbols, name_map, name_en_map)
            except Exception as exc:
                logger.warning("[DBViewerLogic] 검색 필터 실패 (폴백 사용): %s", exc)
                # 폴백: 심볼 텍스트 + 캐시된 한글명 검색
                q = text.lower()
                name_map_fallback: dict = getattr(self, "_name_map", None) or {}
                filtered = [
                    s for s in all_symbols
                    if q in s.lower() or q in name_map_fallback.get(s, "").lower()
                ]

            self._refresh_symbol_combo(filtered)
            self._update_search_result_label(len(filtered), show=True)

        def _update_search_result_label(self, count: int, show: bool) -> None:
            """검색 결과 건수를 label_search_result에 표시합니다.

            Args:
                count: 매칭된 심볼 수
                show: True이면 건수 표시, False이면 빈 문자열
            """
            lbl = getattr(self, "label_search_result", None)
            if lbl is None:
                return
            lbl.setText(f"{count}개 매칭" if show else "")

        # ------------------------------------------------------------------
        # 조회
        # ------------------------------------------------------------------

        def _on_query(self) -> None:
            """조회 버튼 클릭 처리."""
            btn = getattr(self, "btn_query", None)
            if btn:
                btn.setEnabled(False)
                btn.setText("조회 중…")

            t0 = _time.monotonic()
            try:
                symbol = self._get_current_symbol()
                timeframe = self._get_current_timeframe()
                period_opt = self._get_current_period_opt()
                data_source = self._get_current_data_source()

                from ..utils.candle_queries import (
                    query_candles_extended, query_table_counts_extended, get_save_rate_per_sec
                )
                rows = query_candles_extended(symbol, timeframe, period_opt, data_source)
                self._rows = rows
                self._populate_table(rows)

                counts = query_table_counts_extended()
                rate = get_save_rate_per_sec()

                self.update_summary(
                    len(rows),
                    counts.get("candles", 0),
                    counts.get("staging", 0),
                    counts.get("isolated", 0),
                )
                self.update_status_banner(
                    counts.get("candles", 0),
                    counts.get("staging", 0),
                    counts.get("isolated", 0),
                    rate,
                    counts.get("last_save_time"),
                )
                elapsed = _time.monotonic() - t0
                self.update_query_time(elapsed)

            except Exception as exc:
                logger.error("[DBViewerLogic] 조회 중 오류: %s", exc)
                lbl = getattr(self, "label_summary", None)
                if lbl:
                    lbl.setText(f"조회 오류: {exc}")
            finally:
                if btn:
                    btn.setEnabled(True)
                    btn.setText("조회")

        def _populate_table(self, rows: List[Tuple]) -> None:
            """테이블 위젯에 캔들 데이터를 채웁니다 (9컬럼 지원).

            Note:
                _fmt_num 은 DBViewerUIUpdatersMixin 에 정의되어 있습니다.
                DBDataViewerTab(DBViewerLogicMixin, DBViewerUIUpdatersMixin, ...) 순서로
                상속해야 MRO에서 올바르게 탐색됩니다.
            """
            table = getattr(self, "table_candles", None)
            if table is None:
                return

            table.setSortingEnabled(False)
            table.setRowCount(0)
            table.setRowCount(len(rows))

            for r_idx, row in enumerate(rows):
                time_val     = row[0] if len(row) > 0 else None
                open_        = row[1] if len(row) > 1 else None
                high         = row[2] if len(row) > 2 else None
                low          = row[3] if len(row) > 3 else None
                close        = row[4] if len(row) > 4 else None
                volume       = row[5] if len(row) > 5 else None
                quote_volume = row[6] if len(row) > 6 else None
                trade_count  = row[7] if len(row) > 7 else None
                is_complete  = row[8] if len(row) > 8 else None

                if isinstance(time_val, datetime):
                    time_str = time_val.strftime("%Y-%m-%d %H:%M")
                else:
                    time_str = str(time_val) if time_val is not None else "-"

                # is_complete 표시: True → ✅ / False → ⬜ / None → -
                if is_complete is None:
                    complete_str = "-"
                elif is_complete:
                    complete_str = "OK"
                else:
                    complete_str = "⬜"

                values = [
                    time_str,
                    self._fmt_num(open_),
                    self._fmt_num(high),
                    self._fmt_num(low),
                    self._fmt_num(close),
                    self._fmt_num(volume),
                    self._fmt_num(quote_volume),
                    self._fmt_num(trade_count),
                    complete_str,
                ]
                for c_idx, val in enumerate(values):
                    item = QTableWidgetItem(val)
                    align = Qt.AlignLeft | Qt.AlignVCenter if c_idx == 0 else Qt.AlignRight | Qt.AlignVCenter
                    item.setTextAlignment(align)
                    table.setItem(r_idx, c_idx, item)

            table.setSortingEnabled(True)

        # ------------------------------------------------------------------
        # 내보내기
        # ------------------------------------------------------------------

        def _on_export(self) -> None:
            """CSV 내보내기."""
            rows = getattr(self, "_rows", [])
            if not rows:
                return
            path, _ = QFileDialog.getSaveFileName(
                self,
                "CSV 저장",
                "candles_export.csv",
                "CSV Files (*.csv);;All Files (*)",
            )
            if not path:
                return
            try:
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(_COL_HEADERS)
                    for row in rows:
                        writer.writerow([str(v) if v is not None else "" for v in row])
                logger.info("[DBViewerLogic] CSV 저장 완료: %s (%d행)", path, len(rows))
                lbl = getattr(self, "label_summary", None)
                if lbl:
                    lbl.setText(lbl.text() + f"  →  CSV 저장: {path}")
            except Exception as exc:
                logger.error("[DBViewerLogic] CSV 저장 실패: %s", exc)

        # ------------------------------------------------------------------
        # 내부 헬퍼
        # ------------------------------------------------------------------

        def _refresh_symbol_combo(self, symbols: List[str]) -> None:
            """심볼 콤보박스 내용을 교체합니다."""
            combo = getattr(self, "combo_symbol", None)
            if combo is None:
                return
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(symbols)
            # 기존 선택값 유지 시도
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)

        def _get_current_symbol(self) -> str:
            combo = getattr(self, "combo_symbol", None)
            return combo.currentText().strip() if combo else ""

        def _get_current_timeframe(self) -> str:
            combo = getattr(self, "combo_timeframe", None)
            return combo.currentText().strip() if combo else "1m"

        def _get_current_period_opt(self) -> dict:
            combo = getattr(self, "combo_period", None)
            if combo is None:
                return {"type": "limit", "limit": 100}
            idx = combo.currentIndex()
            if 0 <= idx < len(_PERIOD_OPTIONS):
                return _PERIOD_OPTIONS[idx][1]
            return {"type": "limit", "limit": 100}

        def _get_current_data_source(self) -> str:
            """현재 선택된 데이터 소스를 반환합니다."""
            combo = getattr(self, "combo_data_source", None)
            if combo is None:
                return "candles"
            return combo.currentText().strip() or "candles"

        @staticmethod
        def _get_default_symbols() -> List[str]:
            return [
                "KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-ADA",
                "KRW-DOGE", "KRW-DOT", "KRW-AVAX", "KRW-LINK", "KRW-MATIC",
            ]

        # ------------------------------------------------------------------
        # 백필 검증
        # ------------------------------------------------------------------

        def _connect_verify_signals(self) -> None:
            """백필 검증 버튼 시그널 연결. DBDataViewerTab.__init__ 에서 호출합니다."""
            btn = getattr(self, "btn_verify", None)
            if btn is not None:
                btn.clicked.connect(self._on_verify)
            # 검증용 타임프레임 콤보 초기화
            combo = getattr(self, "combo_verify_timeframe", None)
            if combo is not None and combo.count() == 0:
                combo.addItems(["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"])
            # 타임프레임 변경 시 수집설정 캔들 수 기반으로 시작/종료 날짜 자동 갱신
            # (DBViewerAutoPeriodMixin._on_verify_tf_changed 사용)
            try:
                if (
                    combo is not None
                    and hasattr(combo, "currentTextChanged")
                    and hasattr(self, "_on_verify_tf_changed")
                ):
                    combo.currentTextChanged.connect(self._on_verify_tf_changed)
            except Exception as exc:
                logger.debug("[DBViewerLogic] verify TF 시그널 연결 실패: %s", exc)
            # QDateEdit 초기값 설정 (종료=오늘, 시작=7일 전)
            self._init_date_widgets()
            # 현재 선택된 TF 기준으로 즉시 자동 기간 적용 (수집설정 반영)
            try:
                cur_tf = combo.currentText().strip() if combo is not None else ""
                if cur_tf and hasattr(self, "_apply_auto_verify_period_for_tf"):
                    self._apply_auto_verify_period_for_tf(cur_tf)
            except Exception as exc:
                logger.debug("[DBViewerLogic] verify 초기 자동 기간 적용 실패: %s", exc)

        # ------------------------------------------------------------------
        # 백필 검증: 타임프레임별 자동 기간 계산은 DBViewerAutoPeriodMixin 에서
        # 제공한다 (db_viewer_auto_period.py 참고).
        # ------------------------------------------------------------------

        def _init_date_widgets(self) -> None:
            """QDateEdit 위젯의 초기 날짜를 설정합니다 (종료=오늘, 시작=7일 전)."""
            try:
                from PyQt5.QtCore import QDate
                today = QDate.currentDate()
                week_ago = today.addDays(-7)
                edit_start = getattr(self, "edit_verify_start", None)
                edit_end = getattr(self, "edit_verify_end", None)
                if edit_start is not None and hasattr(edit_start, "setDate"):
                    edit_start.setDate(week_ago)
                if edit_end is not None and hasattr(edit_end, "setDate"):
                    edit_end.setDate(today)
            except Exception as exc:
                logger.debug("[DBViewerLogic] 날짜 위젯 초기화 실패: %s", exc)

        @staticmethod
        def _safe_ensure_utc(dt: datetime) -> datetime:
            """datetime이 timezone-aware인지 확인하고 UTC를 부여합니다.

            Args:
                dt: 변환할 datetime 객체

            Returns:
                UTC timezone-aware datetime
            """
            if not isinstance(dt, datetime):
                return datetime.now(timezone.utc)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        def _read_date_widget(self, attr_name: str, default_days_ago: int = 0) -> datetime:
            """날짜 위젯(QDateEdit 또는 QLineEdit)에서 UTC datetime을 읽습니다.

            QDateEdit이면 date().toPyDate()로 읽고, QLineEdit이면 텍스트 파싱을 시도합니다.
            읽기 실패 시 오늘 기준 default_days_ago 일 전의 UTC datetime을 반환합니다.

            Args:
                attr_name: 위젯 속성명 (예: "edit_verify_start")
                default_days_ago: 실패 시 사용할 기본 오프셋(일)

            Returns:
                UTC timezone-aware datetime
            """
            widget = getattr(self, attr_name, None)
            default = datetime.now(timezone.utc) - timedelta(days=default_days_ago)
            if widget is None:
                return default
            # QDateEdit
            if hasattr(widget, "date") and callable(widget.date):
                try:
                    py_date = widget.date().toPyDate()
                    return datetime(py_date.year, py_date.month, py_date.day,
                                    tzinfo=timezone.utc)
                except Exception as exc:
                    logger.debug("[DBViewerLogic] QDateEdit 읽기 실패 (%s): %s", attr_name, exc)
                    return default
            # QLineEdit 폴백
            if hasattr(widget, "text"):
                text = widget.text().strip()
                if text:
                    try:
                        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass
            return default

        def _on_verify(self) -> None:
            """백필 검증 실행: 기대 봉수 vs 실제 봉수, 누락/중복 진단."""
            btn = getattr(self, "btn_verify", None)
            if btn:
                btn.setEnabled(False)
                btn.setText("검증 중...")

            lbl_status = getattr(self, "label_verify_status", None)
            if lbl_status:
                lbl_status.setText("상태: 검증 중...")
                lbl_status.setStyleSheet("font-weight: bold; color: #FF9800;")

            try:
                symbol = self._get_current_symbol()
                combo_vtf = getattr(self, "combo_verify_timeframe", None)
                timeframe = combo_vtf.currentText().strip() if combo_vtf else self._get_current_timeframe()

                start_dt = self._read_date_widget("edit_verify_start", default_days_ago=7)
                end_dt = self._read_date_widget("edit_verify_end", default_days_ago=0)

                # 날짜 범위 검증
                if end_dt <= start_dt:
                    if lbl_status:
                        lbl_status.setText("상태: 오류 — 종료일이 시작일보다 이전입니다")
                        lbl_status.setStyleSheet("font-weight: bold; color: #e74c3c;")
                    return

                # 기대 봉수 계산 (모듈 수준 상수 사용)
                minutes_per_bar = _TF_MINUTES.get(timeframe, 1)
                total_minutes = max(0, int((end_dt - start_dt).total_seconds() / 60))
                expected = total_minutes // minutes_per_bar if minutes_per_bar > 0 else 0

                # 실제 봉수 + 중복 수 + 데이터 소스 조회
                actual, duplicates, source_table, used_fallback = self._query_verify_counts_ex(
                    symbol, timeframe, start_dt, end_dt
                )

                missing = max(0, expected - actual)

                # 레이블 갱신
                lbl_exp = getattr(self, "label_verify_expected", None)
                if lbl_exp:
                    lbl_exp.setText(f"기대 봉수: {expected:,}")

                lbl_act = getattr(self, "label_verify_actual", None)
                if lbl_act:
                    src_suffix = ""
                    if source_table:
                        src_suffix = (
                            f"  [출처: {source_table}{' (CAGG 폴백)' if used_fallback else ''}]"
                        )
                    lbl_act.setText(f"실제 봉수: {actual:,}{src_suffix}")

                lbl_miss = getattr(self, "label_verify_missing", None)
                if lbl_miss:
                    lbl_miss.setText(f"누락: {missing:,}")
                    lbl_miss.setStyleSheet("color: #e74c3c;" if missing > 0 else "color: #27ae60;")

                lbl_dup = getattr(self, "label_verify_duplicate", None)
                if lbl_dup:
                    lbl_dup.setText(f"중복: {duplicates:,}")
                    lbl_dup.setStyleSheet("color: #e67e22;" if duplicates > 0 else "color: #27ae60;")

                if lbl_status:
                    if missing == 0 and duplicates == 0:
                        lbl_status.setText("상태: 정상 (백필 완료)")
                        lbl_status.setStyleSheet("font-weight: bold; color: #27ae60;")
                    elif missing > 0 and duplicates > 0:
                        lbl_status.setText(f"상태: 누락+중복 발생 ({missing:,}개 누락, {duplicates:,}개 중복)")
                        lbl_status.setStyleSheet("font-weight: bold; color: #e74c3c;")
                    elif missing > 0:
                        pct = (missing / expected * 100) if expected > 0 else 0
                        lbl_status.setText(f"상태: 누락 발생 ({missing:,}개, {pct:.1f}%)")
                        lbl_status.setStyleSheet("font-weight: bold; color: #e74c3c;")
                    else:
                        lbl_status.setText(f"상태: 중복 발생 ({duplicates:,}개)")
                        lbl_status.setStyleSheet("font-weight: bold; color: #e67e22;")

                logger.info(
                    "[DBViewerLogic] 백필 검증 완료: symbol=%s tf=%s 기대=%d 실제=%d 누락=%d 중복=%d",
                    symbol, timeframe, expected, actual, missing, duplicates,
                )

            except Exception as exc:
                logger.error("[DBViewerLogic] 백필 검증 오류: %s", exc)
                if lbl_status:
                    lbl_status.setText(f"상태: 검증 오류 — {exc}")
                    lbl_status.setStyleSheet("font-weight: bold; color: #e74c3c;")
            finally:
                if btn:
                    btn.setEnabled(True)
                    btn.setText("검증 실행")

        def _query_verify_counts(
            self,
            symbol: str,
            timeframe: str,
            start_dt: Any,
            end_dt: Any,
        ) -> Tuple[int, int]:
            """TimescaleDB에서 실제 봉수 및 중복 수를 조회합니다 (호환용 2-튜플).

            Returns:
                Tuple[actual_count, duplicate_count]
            """
            actual, dup, _src, _fb = self._query_verify_counts_ex(
                symbol, timeframe, start_dt, end_dt
            )
            return actual, dup

        def _query_verify_counts_ex(
            self,
            symbol: str,
            timeframe: str,
            start_dt: Any,
            end_dt: Any,
        ) -> Tuple[int, int, str, bool]:
            """검증 카운트 + 데이터 소스/폴백 정보 (CAGG 폴백 포함).

            Returns:
                Tuple[actual_count, duplicate_count, source_table, used_fallback]
            """
            try:
                from ..utils.candle_queries import query_verify_backfill_ex
                return query_verify_backfill_ex(symbol, timeframe, start_dt, end_dt)
            except ImportError:
                pass
            except Exception as exc:
                logger.warning("[DBViewerLogic] query_verify_backfill_ex 실패: %s", exc)

            # 폴백: 직접 DB 접속 시도 (원본 candles 만, 폴백 없음)
            try:
                import os
                import psycopg2
                dsn = (
                    f"host={os.getenv('TIMESCALE_HOST', 'localhost')} "
                    f"port={os.getenv('TIMESCALE_PORT', '5432')} "
                    f"dbname={os.getenv('TIMESCALE_DB', 'upbit_ohlcv')} "
                    f"user={os.getenv('TIMESCALE_USER', 'postgres')} "
                    f"password={os.getenv('TIMESCALE_PASSWORD', '')}"
                )
                with psycopg2.connect(dsn) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT
                                COUNT(*) AS actual_count,
                                COUNT(*) - COUNT(DISTINCT time) AS duplicate_count
                            FROM candles
                            WHERE symbol = %s
                              AND timeframe = %s
                              AND time >= %s
                              AND time < %s
                            """,
                            (symbol, timeframe, start_dt, end_dt),
                        )
                        row = cur.fetchone()
                        if row:
                            return int(row[0] or 0), int(row[1] or 0), "candles", False
            except Exception as exc:
                logger.debug("[DBViewerLogic] DB 직접 검증 실패: %s", exc)

            return 0, 0, "", False

else:
    class DBViewerLogicMixin:  # type: ignore[no-redef]
        """PyQt5 미설치 시 더미 Mixin."""

        def _populate_combos(self) -> None:
            pass

        def _load_symbols_for_combo(self) -> None:
            pass

        def _on_asset_changed(self, index: int = 0) -> None:
            pass

        def _on_exchange_changed(self, index: int = 0) -> None:
            pass

        def _on_search(self, text: str) -> None:
            pass

        def _on_query(self) -> None:
            pass

        def _on_export(self) -> None:
            pass

        def _get_current_data_source(self) -> str:
            return "candles"

        def _connect_verify_signals(self) -> None:
            pass

        def _on_verify(self) -> None:
            pass
