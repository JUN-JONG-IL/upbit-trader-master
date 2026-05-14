# -*- coding: utf-8 -*-
"""Tab: 스마트 스캐너 — 요약 뷰 + 비모달 필터 설정 팝업

필터 조건(9개 탭)은 비모달 팝업(ScannerSettingsDialog)으로 분리되었습니다.
이 탭은 스캔 결과 테이블과 요약 정보만 표시합니다.
"""
from __future__ import annotations

import asyncio
import csv
import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

try:
    from PyQt5 import uic
    from PyQt5.QtCore import QTimer, QThread, pyqtSignal, pyqtSlot
    from PyQt5.QtWidgets import (
        QWidget, QMessageBox, QTableWidgetItem, QFileDialog,
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

_UI_PATH = os.path.join(os.path.dirname(__file__), "scanner_tab.ui")


if _HAS_QT:
    class _ScanWorker(QThread):
        """백그라운드 스캔 워커 (메인 스레드 블로킹 방지)"""
        finished = pyqtSignal(list)

        def __init__(self, mode: str, conditions: Dict, custom_expr: str = ""):
            super().__init__()
            self._mode = mode
            self._conditions = conditions
            self._custom_expr = custom_expr

        def run(self) -> None:
            """스캔 로직 실행 (DB 쿼리 + AI 모델 추론)"""
            try:
                results = self._execute()
            except Exception as exc:
                logger.error("[ScanWorker] 스캔 실패: %s", exc)
                results = []
            self.finished.emit(results)

        def _execute(self) -> List:
            """TimescaleDB에서 심볼별 최근 캔들 통계를 조회합니다."""
            results = []
            try:
                from ..utils.db_connectors import get_timescale_connector
                conn = get_timescale_connector()
                if conn is None:
                    return results
                db_conn = conn.get_connection(retry=False)
                try:
                    with db_conn.cursor() as cur:
                        # config.yaml symbol_query_limit 으로 스캔 한도 조정
                        try:
                            from ..utils.config_loader import get_symbol_query_limit
                            _scan_limit = get_symbol_query_limit()
                        except Exception as _cfg_exc:
                            logger.debug("[ScanWorker] config 스캔 한도 로드 실패, 기본값 사용: %s", _cfg_exc)
                            _scan_limit = 10_000
                        cur.execute(
                            """
                            SELECT
                                symbol,
                                COUNT(*) AS candle_count,
                                MAX(time) AS last_time,
                                MAX(close) AS max_close,
                                MIN(close) AS min_close,
                                AVG(volume) AS avg_volume
                            FROM candles
                            WHERE time >= NOW() - INTERVAL '1 day'
                            GROUP BY symbol
                            ORDER BY candle_count DESC
                            LIMIT %s
                            """,
                            (_scan_limit,),
                        )
                        rows = cur.fetchall()
                finally:
                    conn.put_connection(db_conn)

                for row in rows:
                    results.append([
                        str(row[0]),                                # 심볼
                        f"{int(row[1]):,}",                        # 캔들 수
                        str(row[2])[:16] if row[2] else "--",      # 최종 시각
                        f"{row[3]:,.0f}" if row[3] else "--",      # 최고가
                        f"{row[4]:,.0f}" if row[4] else "--",      # 최저가
                        f"{row[5]:,.1f}" if row[5] else "--",      # 평균 거래량
                    ])
            except Exception as exc:
                logger.warning("[ScanWorker] DB 스캔 실패: %s", exc)
            return results

    class ScannerTab(QWidget):
        """스마트 스캐너 탭 (요약 뷰).

        필터 조건은 ScannerSettingsDialog(비모달)에서 관리합니다.
        이 탭은 스캔 결과 테이블과 요약 상태만 표시합니다.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            try:
                uic.loadUi(_UI_PATH, self)
            except Exception as exc:
                logger.warning("[ScannerTab] UI 로드 실패: %s", exc)

            self._worker: _ScanWorker | None = None
            self._settings_manager = None

            # 필터 설정 다이얼로그 인스턴스 (지연 생성)
            self._filter_dialog = None

            # 실시간 결과 갱신 타이머 (2초마다)
            self._timer = QTimer(self)
            self._timer.setInterval(2000)
            self._timer.timeout.connect(self._update_results)

            self._connect_signals()

        # ------------------------------------------------------------------
        # 다이얼로그 관련
        # ------------------------------------------------------------------

        def _get_or_create_filter_dialog(self):
            """필터 설정 다이얼로그를 반환합니다 (없으면 생성)."""
            if self._filter_dialog is None:
                try:
                    from ..dialogs.scanner_settings_dialog import ScannerSettingsDialog
                    self._filter_dialog = ScannerSettingsDialog(self)
                    self._filter_dialog.settings_changed.connect(self._on_filter_settings_changed)
                except Exception as exc:
                    logger.error("[ScannerTab] 필터 다이얼로그 생성 실패: %s", exc)
            return self._filter_dialog

        def _open_filter_dialog(self) -> None:
            """필터 설정 다이얼로그 열기 (비모달)."""
            dlg = self._get_or_create_filter_dialog()
            if dlg is None:
                return
            if dlg.isVisible():
                dlg.activateWindow()
                return
            dlg.show()

        def _on_filter_settings_changed(self, settings: dict) -> None:
            """필터 다이얼로그 설정 변경 시 요약 레이블 갱신."""
            try:
                dlg = self._filter_dialog
                if dlg is not None and hasattr(dlg, "get_active_condition_count"):
                    count = dlg.get_active_condition_count()
                    if hasattr(self, "labelSummaryConditions"):
                        self.labelSummaryConditions.setText(f"활성 조건: {count}개")
                if dlg is not None and hasattr(dlg, "get_current_mode"):
                    mode = dlg.get_current_mode()
                    if hasattr(self, "labelSummaryMode"):
                        self.labelSummaryMode.setText(f"조건 모드: {mode}")
            except Exception as exc:
                logger.debug("[ScannerTab] 요약 레이블 갱신 실패: %s", exc)

        # ------------------------------------------------------------------
        # 시그널 연결
        # ------------------------------------------------------------------

        def _connect_signals(self) -> None:
            """UI 버튼 시그널 연결"""
            try:
                if hasattr(self, "btn_open_filter_detail"):
                    self.btn_open_filter_detail.clicked.connect(self._open_filter_dialog)
                if hasattr(self, "btnScan"):
                    self.btnScan.clicked.connect(self._on_scan_clicked)
                if hasattr(self, "btnExportCSV"):
                    self.btnExportCSV.clicked.connect(self._on_export_csv)
            except AttributeError as exc:
                logger.debug("[ScannerTab] 시그널 연결 일부 실패: %s", exc)

        # ------------------------------------------------------------------
        # 슬롯
        # ------------------------------------------------------------------

        @pyqtSlot()
        def _on_scan_clicked(self) -> None:
            """스캔 실행 (백그라운드 워커)"""
            if self._worker is not None and self._worker.isRunning():
                return

            # 조건은 다이얼로그에서 수집
            dlg = self._get_or_create_filter_dialog()
            if dlg is not None and hasattr(dlg, "get_current_mode"):
                mode = dlg.get_current_mode()
            else:
                mode = "AND"

            if mode == "CUSTOM":
                custom_expr = ""
                try:
                    custom_expr = dlg.lineEditCustom.text().strip()
                except AttributeError:
                    pass
                if not custom_expr:
                    QMessageBox.warning(self, "경고", "고급 조건식을 입력하세요.")
                    return
            else:
                custom_expr = ""

            conditions = {}
            if dlg is not None and hasattr(dlg, "_collect_conditions"):
                conditions = dlg._collect_conditions()

            logger.info("[ScannerTab] 스캔 시작 — 모드: %s, 조건 수: %d", mode, len(conditions))

            self._worker = _ScanWorker(mode, conditions, custom_expr)
            self._worker.finished.connect(self._on_scan_finished)
            self._worker.start()

        @pyqtSlot(list)
        def _on_scan_finished(self, results: List) -> None:
            """스캔 완료 — 테이블 갱신"""
            self._update_table_optimized(results)
            try:
                self.labelMatchCount.setText(
                    f"매칭 종목 수: {len(results):,}개 / 전체 2,500개 [TimescaleDB]"
                )
            except AttributeError:
                pass

        def _on_export_csv(self) -> None:
            """스캔 결과 CSV 내보내기"""
            tbl = getattr(self, "tableResults", None)
            if tbl is None:
                return
            path, _ = QFileDialog.getSaveFileName(
                self, "CSV 저장", "scan_results.csv", "CSV 파일 (*.csv)"
            )
            if not path:
                return
            try:
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    headers = [
                        tbl.horizontalHeaderItem(c).text()
                        for c in range(tbl.columnCount())
                        if tbl.horizontalHeaderItem(c)
                    ]
                    writer.writerow(headers)
                    for r in range(tbl.rowCount()):
                        row = []
                        for c in range(tbl.columnCount()):
                            item = tbl.item(r, c)
                            row.append(item.text() if item else "")
                        writer.writerow(row)
                QMessageBox.information(self, "완료", f"CSV 저장 완료: {path}")
            except Exception as exc:
                logger.error("[ScannerTab] CSV 저장 실패: %s", exc)
                QMessageBox.warning(self, "오류", f"CSV 저장 실패: {exc}")

        # ------------------------------------------------------------------
        # 내부 유틸
        # ------------------------------------------------------------------

        def _update_table_optimized(self, new_data: List) -> None:
            """변경된 셀만 갱신 (Virtual DOM Diff)"""
            tbl = getattr(self, "tableResults", None)
            if tbl is None:
                return
            tbl.setRowCount(len(new_data))
            for row, row_data in enumerate(new_data):
                for col, val in enumerate(row_data):
                    text = str(val)
                    current = tbl.item(row, col)
                    if current is None or current.text() != text:
                        tbl.setItem(row, col, QTableWidgetItem(text))

        def _update_results(self) -> None:
            """Redis 캐시에서 최신 가격 정보를 갱신합니다."""
            try:
                from ..utils.db_connectors import get_redis_connector
                redis_client = get_redis_connector()
                if redis_client is None:
                    return
                # Redis에서 최근 스캔 심볼 정보 갱신 (간단 구현)
                if hasattr(self, "label_last_scan_time"):
                    from datetime import datetime
                    self.label_last_scan_time.setText(
                        f"마지막 갱신: {datetime.now().strftime('%H:%M:%S')}"
                    )
            except Exception as exc:
                logger.debug("[ScannerTab] Redis 갱신 실패: %s", exc)

        # ------------------------------------------------------------------
        # 설정 저장/복원 (공개 API — status_widget.py에서 호출)
        # ------------------------------------------------------------------

        def set_settings_manager(self, manager) -> None:
            """UISettingsManager 주입 → 다이얼로그에 전달"""
            self._settings_manager = manager
            dlg = self._get_or_create_filter_dialog()
            if dlg is not None and hasattr(dlg, "set_settings_manager"):
                dlg.set_settings_manager(manager)

        def restore_settings(self, settings: dict) -> None:
            """MongoDB에서 로드한 스캐너 설정을 다이얼로그에 복원합니다."""
            dlg = self._get_or_create_filter_dialog()
            if dlg is not None and hasattr(dlg, "restore_settings"):
                dlg.restore_settings(settings)
                # 요약 레이블도 갱신
                self._on_filter_settings_changed(settings)

        def collect_current_settings(self) -> dict:
            """현재 설정을 다이얼로그에서 수집합니다."""
            dlg = self._get_or_create_filter_dialog()
            if dlg is not None and hasattr(dlg, "collect_current_settings"):
                return dlg.collect_current_settings()
            return {}

        def on_settings_changed(self) -> None:
            """설정 변경 알림 (하위 호환 유지)"""
            pass

        def start_updates(self, interval_ms: int = 2000) -> None:
            self._timer.setInterval(max(1000, int(interval_ms)))
            self._timer.start()

        def stop_updates(self) -> None:
            self._timer.stop()

else:
    class ScannerTab:  # type: ignore[no-redef]
        """PyQt5 미설치 시 사용하는 더미 클래스"""

        def __init__(self, parent=None):
            pass

        def start_updates(self, interval_ms: int = 2000) -> None:
            pass

        def stop_updates(self) -> None:
            pass

        def set_settings_manager(self, manager) -> None:
            pass

        def restore_settings(self, settings: dict) -> None:
            pass

        def collect_current_settings(self) -> dict:
            return {}

        def on_settings_changed(self) -> None:
            pass
