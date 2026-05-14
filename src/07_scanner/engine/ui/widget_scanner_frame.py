# -*- coding: utf-8 -*-
"""
[Purpose]
- 사용자가 설정한 조건에 맞는 Upbit 종목(코인)을 스캔하여 목록으로 보여주는
  "종목 스캔기(Scanner)" 위젯이다.

[Responsibilities]
- widget_scanner_frame.ui 로드 및 UI 이벤트(설정/검색/자동검색/테이블 표시) 처리
- ScannerWorker(QThread)에서 종목별 OHLCV 조회 및 조건 검사 실행
- 실행률 및 결과 테이블 UI 업데이트
- 각 기능(리셋/검색/새로고침)과 동작하여, 결과 선택 시 현재 타겟에 업데이트 호출

[Main Flow]
- ScannerFrameWidget.__init__()
  - UI 로드(절대 경로 기준)
  - 기본 설정 로드(현재 사용 가능한 코인 → dict)
  - 버튼/이벤트 연결
  - ScannerWorker 생성 및 시그널 연결
- on_refresh() 호출 시 ScannerWorker 실행
- ScannerWorker.scan_loop()에서 종목 스캔 후 update_table 콜백 전달
- 테이블 선택 시 chart/order/trade로 타겟 업데이트 호출

[Dependencies]
- aiopyupbit: OHLCV 조회
- PyQt5: QWidget/QThread/Signal/Timer
- server.static: static.chart.coins 사용(이용 가능한 종목 목록)
- scanner.logic.popup_scanner_settings.ScannerSettingsPopup: 조건 설정 팝업
- scanner.logic.scanner_settings_advanced_popup.ScannerSettingsAdvancedPopup: 고급 설정 팝업

[UI Binding]
- widget_scanner_frame.ui
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

try:
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QHeaderView
    from PyQt5 import uic
except Exception:
    from utils.qt_stub import QtCore, QtWidgets
    Qt = QtCore.Qt
    QTimer = QtCore.QTimer
    QWidget = QtWidgets.QWidget
    QTableWidgetItem = QtWidgets.QTableWidgetItem
    QHeaderView = QtWidgets.QHeaderView
    uic = None

from ..workers import ScannerWorker
from .popup_scanner_settings import ScannerSettingsPopup
from .scanner_settings_advanced_popup import ScannerSettingsAdvancedPopup

_UI_PATH = os.path.join(os.path.dirname(__file__), "widget_scanner_frame.ui")


class ScannerFrameWidget(QWidget):
    """
    종목 스캔 위젯.

    ScannerWorker를 통해 백그라운드에서 스캔을 실행하고
    결과를 테이블에 표시한다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        if uic is not None:
            uic.loadUi(_UI_PATH, self)

        # 기본 설정(키 누락 방지)
        self.settings: Dict[str, Any] = {
            "interval": "minute1",
            "rsi_period": 14,
            "rsi_value": 30,
            "ma_short": 5,
            "ma_long": 20,
            "ma_direction": "우상향",
            "auto_interval": 60,
        }

        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self.on_refresh)

        self.remaining_timer = QTimer(self)
        self.remaining_timer.timeout.connect(self.update_remaining_time)

        if uic is not None:
            self.settingsButton.clicked.connect(self.open_settings)
            self.refreshButton.clicked.connect(self.on_refresh)
            self.autoRefreshCheckBox.stateChanged.connect(self.toggle_auto_refresh)
            self.searchTable.itemClicked.connect(self.on_table_click)

        self.sw = ScannerWorker(self.settings)
        self.sw.update_table.connect(self.update_table)
        self.sw.update_progress.connect(self._on_progress)
        self.sw.update_remaining.connect(self._on_remaining)

        if uic is not None:
            # 테이블 설정
            self.searchTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        # 외부 연동 객체(나중에 setChart/setOrder/setTrade에서 주입)
        self.chart = None
        self.order = None
        self.trade = None

        self.remaining_time = int(self.settings.get("auto_interval", 60))

    def _on_progress(self, value: int) -> None:
        """진행률 업데이트."""
        if uic is not None and hasattr(self, 'progressBar'):
            self.progressBar.setValue(value)

    def _on_remaining(self, text: str) -> None:
        """남은 시간 레이블 업데이트."""
        if uic is not None and hasattr(self, 'remainingTimeLabel'):
            self.remainingTimeLabel.setText(text)

    def setChart(self, chart) -> None:
        self.chart = chart

    def setOrder(self, order) -> None:
        self.order = order

    def setTrade(self, trade) -> None:
        self.trade = trade

    def open_settings(self) -> None:
        """
        설정창 열기.

        NOTE: 기본 설정창과 고급 설정창 두 가지 옵션 제공
        - 기본: ScannerSettingsPopup (간단한 설정)
        - 고급: ScannerSettingsAdvancedPopup (18개 지표 그룹)

        현재 고급 설정창 사용 중.
        기본 설정창으로 전환하려면:
        1. popup = ScannerSettingsPopup(self) 사용
        2. ScannerSettingsAdvancedPopup import 주석 처리
        """
        # Use advanced settings popup
        popup = ScannerSettingsAdvancedPopup(self)
        popup.exec_()
        temp_settings = popup.get_settings()

        # interval을 영문으로 매핑 (한글 → aiopyupbit 형식)
        self.settings = self.map_interval(temp_settings)

        # 워커가 참조하는 settings dict도 갱신
        self.sw.update_settings(self.settings)

        # 자동 갱신 주기 업데이트(켜져있으면 즉시 반영)
        if uic is not None and self.autoRefreshCheckBox.isChecked():
            self.toggle_auto_refresh(Qt.Checked)

    def map_interval(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """한글 interval을 aiopyupbit 형식으로 변환."""
        interval_map = {
            "틱1": "minute1",
            "틱3": "minute3",
            "틱5": "minute5",
            "틱10": "minute10",
            "틱30": "minute30",
            "틱60": "minute60",
            "초": "minute1",
            "1분": "minute1",
            "3분": "minute3",
            "5분": "minute5",
            "10분": "minute10",
            "15분": "minute15",
            "30분": "minute30",
            "60분": "minute60",
            "240분": "minute240",
            "일": "day",
            "주": "week",
            "월": "month",
            "년": "year",
        }
        raw = settings.get("interval", "minute1")
        settings["interval"] = interval_map.get(raw, "minute1")
        return settings

    def on_refresh(self) -> None:
        """스캔 시작/새로고침."""
        if uic is not None and hasattr(self, 'progressBar'):
            self.progressBar.setValue(0)

        # 이미 실행 중이면 재실행하지 않음(중복 스레드 방지)
        if not self.sw.isRunning():
            self.sw.start()

    def toggle_auto_refresh(self, state) -> None:
        """자동 새로고침 토글."""
        if state == Qt.Checked:
            interval = int(self.settings.get("auto_interval", 60))
            self.auto_timer.start(interval * 1000)
            self.remaining_time = interval
            self.remaining_timer.start(1000)
        else:
            self.auto_timer.stop()
            self.remaining_timer.stop()
            if uic is not None and hasattr(self, 'remainingTimeLabel'):
                self.remainingTimeLabel.setText("남은 시간: 00:00")

    def update_remaining_time(self) -> None:
        """남은 시간 카운트다운."""
        self.remaining_time -= 1
        mins, secs = divmod(max(self.remaining_time, 0), 60)
        if uic is not None and hasattr(self, 'remainingTimeLabel'):
            self.remainingTimeLabel.setText(f"남은 시간: {mins:02d}:{secs:02d}")

        if self.remaining_time <= 0:
            self.on_refresh()
            self.remaining_time = int(self.settings.get("auto_interval", 60))

    def update_table(self, results: List[Tuple[str, str]]) -> None:
        """스캔 결과를 테이블에 표시."""
        if uic is None or not hasattr(self, 'searchTable'):
            return
        self.searchTable.setRowCount(len(results))
        for row, result in enumerate(results):
            code = result[0] if len(result) > 0 else ""
            interval = result[1] if len(result) > 1 else ""
            self.searchTable.setItem(row, 0, QTableWidgetItem(code))
            self.searchTable.setItem(row, 1, QTableWidgetItem(interval))

    def on_table_click(self, item) -> None:
        """테이블 항목 클릭 시 외부 위젯에 심볼 전파."""
        if not hasattr(self, 'searchTable'):
            return
        code_item = self.searchTable.item(item.row(), 0)
        if code_item is None:
            return
        code = code_item.text()

        # 방어: 외부 연동이 아직 세팅되지 않았으면 무시
        if self.chart is not None:
            self.chart.update_chart(code)
        if self.order is not None:
            self.order.update_orderbook(code)
        if self.trade is not None:
            self.trade.update_trade(code)
