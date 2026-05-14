"""
Chart Settings Dialog - Load from .ui file

[Features]
- .ui 파일 로드 (100+ 지표 선택)
- 비모달 팝업 (메인과 동시 조작 가능)
- 차트 타입 선택
- 설정 저장 결과 signal emit

[Author] Copilot
[Modified] 2026-03-15 - Rewritten to load from .ui file, non-modal
"""

from pathlib import Path
from typing import Dict, List, Any

try:
    from PyQt5.QtCore import pyqtSignal, Qt
    from PyQt5.QtWidgets import QDialog, QCheckBox, QVBoxLayout
    from PyQt5 import uic
except Exception as _e:
    from utils.qt_stub import QtCore, QtWidgets
    QDialog = QtWidgets.QDialog
    QCheckBox = QtWidgets.QCheckBox
    QVBoxLayout = QtWidgets.QVBoxLayout
    pyqtSignal = QtCore.pyqtSignal
    Qt = QtCore.Qt

import logging
log = logging.getLogger(__name__)


class ChartSettingsDialog(QDialog):
    """차트 설정 다이얼로그 (.ui 파일 로드)

    [Signals]
    - settings_saved(dict): 설정 저장 시 emit

    [Settings Dict Format]
    {
        'indicators': {
            'sma_20': bool, 'ema_20': bool, 'wma_20': bool,
            'bb': bool, 'atr_14': bool,
            'rsi_14': bool, 'macd': bool, 'stochastic': bool, 'adx_14': bool,
            'volume': bool, 'obv': bool,
            'ichimoku': bool,
        },
        'general': {
            'chart_engine': str,   # 'mplfinance'|'matplotlib'|'lightweight'|'plotly'
            'chart_type': str,     # 'candlestick'|'ohlc'|'line'|'area'
            'theme': str,          # 'dark'|'light'
        },
    }
    """

    settings_saved = pyqtSignal(dict)

    # Indicator definitions mapped to scroll content container widget names
    _INDICATOR_GROUPS: List[tuple] = [
        ('trendScrollContent', [
            ('sma_20', 'SMA 20'),
            ('ema_20', 'EMA 20'),
            ('wma_20', 'WMA 20'),
        ]),
        ('momentumScrollContent', [
            ('rsi_14', 'RSI 14'),
            ('macd', 'MACD'),
            ('stochastic', '스토캐스틱'),
            ('adx_14', 'ADX 14'),
        ]),
        ('volatilityScrollContent', [
            ('bb', '볼린저 밴드'),
            ('atr_14', 'ATR 14'),
        ]),
        ('volumeScrollContent', [
            ('volume', '거래량'),
            ('obv', 'OBV'),
        ]),
        ('supportScrollContent', [
            ('ichimoku', '이치모쿠'),
        ]),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)

        # .ui 파일 로드
        ui_path = Path(__file__).parent / "chart_settings_dialog.ui"
        uic.loadUi(str(ui_path), self)

        # 비모달 설정 (메인과 동시 조작 가능)
        self.setModal(False)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        # 초기 설정값 로드
        self._init_indicators: Dict[str, bool] = {}
        self._init_general: Dict[str, Any] = {}
        if parent is not None:
            self._init_indicators = dict(getattr(parent, 'active_indicators', {}) or {})
            self._init_general = dict(getattr(parent, 'general_settings', {}) or {})

        # 지표 체크박스 동적 생성
        self._populate_indicators()

        # 일반 설정 초기화
        self._init_general_widgets()

        # 시그널 연결
        self._connect_signals()

    def _populate_indicators(self) -> None:
        """지표 체크박스를 스크롤 컨테이너에 동적 생성"""
        for widget_name, indicators in self._INDICATOR_GROUPS:
            container = getattr(self, widget_name, None)
            if container is None:
                continue

            layout = container.layout()
            if layout is None:
                layout = QVBoxLayout(container)

            for key, label in indicators:
                cb = QCheckBox(label)
                cb.setChecked(bool(self._init_indicators.get(key, False)))
                layout.addWidget(cb)
                # check_ 접두사로 저장 (get_settings()에서 자동 수집)
                setattr(self, f'check_{key}', cb)

    def _init_general_widgets(self) -> None:
        """일반 설정 위젯 초기값 설정"""
        chart_type = self._init_general.get('chart_type', 'candlestick')
        if hasattr(self, 'chartTypeCombo'):
            idx = self.chartTypeCombo.findText(chart_type)
            if idx >= 0:
                self.chartTypeCombo.setCurrentIndex(idx)

    def _connect_signals(self) -> None:
        """시그널 연결"""
        # 저장 버튼
        if hasattr(self, 'saveButton'):
            self.saveButton.clicked.connect(self._on_accept)
        # 취소 버튼
        if hasattr(self, 'cancelButton'):
            self.cancelButton.clicked.connect(self.reject)
        # QDialogButtonBox (있는 경우)
        if hasattr(self, 'buttonBox'):
            self.buttonBox.accepted.connect(self._on_accept)
            self.buttonBox.rejected.connect(self.reject)

    def _on_accept(self) -> None:
        """확인/저장 버튼 클릭 시 설정 저장"""
        try:
            settings = self.get_settings()
            self.settings_saved.emit(settings)
            self.accept()
        except Exception as e:
            log.error(f"[ChartSettingsDialog] _on_accept error: {e}")
            self.accept()

    def get_settings(self) -> dict:
        """현재 설정 반환"""
        settings: dict = {
            'indicators': {},
            'general': {},
        }

        # 지표 체크박스 상태 수집 (check_ 접두사)
        for attr_name in dir(self):
            if attr_name.startswith('check_'):
                checkbox = getattr(self, attr_name, None)
                if checkbox is not None and hasattr(checkbox, 'isChecked'):
                    indicator_key = attr_name[len('check_'):]
                    settings['indicators'][indicator_key] = checkbox.isChecked()

        # 일반 설정
        general = dict(self._init_general)
        if hasattr(self, 'chartTypeCombo'):
            general['chart_type'] = self.chartTypeCombo.currentText()
        if hasattr(self, 'comboEngine'):
            general['chart_engine'] = self.comboEngine.currentText()
        if hasattr(self, 'comboTheme'):
            general['theme'] = self.comboTheme.currentText()
        settings['general'] = general

        return settings
