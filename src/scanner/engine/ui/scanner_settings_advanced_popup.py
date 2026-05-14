# -*- coding: utf-8 -*-
"""
[Purpose]
- Advanced scanner settings dialog with 5 tabs and 18 indicator groups
- Provides comprehensive UI for cryptocurrency scanner configuration

[Responsibilities]
- Load all tab UI files and integrate them into main dialog
- Initialize all UI elements with default values
- Collect and return user settings from all tabs
- Support preset management (save/load/delete)

[Main Flow]
- ScannerSettingsAdvancedPopup.__init__()
  - Load main dialog UI
  - Load and integrate all 5 tab UIs
  - Initialize all widgets with default values
  - Connect signals for apply/cancel buttons
- get_settings() - Collect all settings from all tabs into a dictionary
- load_preset() / save_preset() - Preset management

[Dependencies]
- PyQt5 (QDialog, uic)
- server.static.chart.coins: Coin list for combo boxes
- .preset_manager: Preset storage and retrieval

[UI Binding]
- scanner_settings_advanced_popup.ui (scanner/ui/ 폴더)
- tab_basic_indicators.ui
- tab_advanced_indicators.ui
- tab_patterns_volume.ui
- tab_filters.ui
- tab_alerts_presets.ui

[Author] GitHub Copilot
[Created] 2026-02-03
[Updated] 2026-03-12 - Moved to ui/, path uses same directory
"""
from __future__ import annotations

import os
from typing import Any, Dict

try:
    from PyQt5.QtWidgets import QDialog, QFileDialog
    from PyQt5 import uic
except Exception:
    from utils.qt_stub import QtWidgets
    QDialog = QtWidgets.QDialog
    QFileDialog = getattr(QtWidgets, 'QFileDialog', None)
    uic = None

try:
    import server.static as static
    HAS_STATIC = True
except ImportError:
    HAS_STATIC = False


def _ui_file_path(filename: str) -> str:
    """ui/ 폴더(현재 파일과 같은 디렉토리)의 파일 경로를 반환한다."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


class ScannerSettingsAdvancedPopup(QDialog):
    """Advanced scanner settings dialog"""

    # 11 timeframes for interval selection
    TIMEFRAMES = [
        "1분", "3분", "5분", "15분", "30분",
        "1시간", "4시간", "일", "주", "월", "년"
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        if uic is None:
            return

        # Load main dialog
        uic.loadUi(_ui_file_path("scanner_settings_advanced_popup.ui"), self)

        # Load all tab UIs
        self._load_tabs()

        # Initialize widgets
        self._init_widgets()

        # Connect signals
        self._connect_signals()

    def _load_tabs(self):
        """Load all tab UI files"""
        if uic is None:
            return
        try:
            # Tab 1: Basic Indicators
            uic.loadUi(_ui_file_path("tab_basic_indicators.ui"), self.tab_basic)

            # Tab 2: Advanced Indicators
            uic.loadUi(_ui_file_path("tab_advanced_indicators.ui"), self.tab_advanced)

            # Tab 3: Patterns & Volume
            uic.loadUi(_ui_file_path("tab_patterns_volume.ui"), self.tab_patterns)

            # Tab 4: Filters
            uic.loadUi(_ui_file_path("tab_filters.ui"), self.tab_filters)

            # Tab 5: Alerts & Presets
            uic.loadUi(_ui_file_path("tab_alerts_presets.ui"), self.tab_alerts)

        except Exception as e:
            print(f"Error loading tab UIs: {e}")

    def _init_widgets(self):
        """
        Initialize all widgets with default values

        [AttributeError Fix]
        If UI file has camelCase attributes (tabBasic), convert them to snake_case (tab_basic)
        """
        try:
            # Convert attribute names from camelCase to snake_case if needed
            if hasattr(self, 'tabBasic') and not hasattr(self, 'tab_basic'):
                self.tab_basic = self.tabBasic
                if HAS_STATIC:
                    static.log.debug("[ScannerSettingsAdvancedPopup] Converted tabBasic -> tab_basic")
            if hasattr(self, 'tabAdvanced') and not hasattr(self, 'tab_advanced'):
                self.tab_advanced = self.tabAdvanced
                if HAS_STATIC:
                    static.log.debug("[ScannerSettingsAdvancedPopup] Converted tabAdvanced -> tab_advanced")
            if hasattr(self, 'tabPatterns') and not hasattr(self, 'tab_patterns'):
                self.tab_patterns = self.tabPatterns
                if HAS_STATIC:
                    static.log.debug("[ScannerSettingsAdvancedPopup] Converted tabPatterns -> tab_patterns")
            if hasattr(self, 'tabFilters') and not hasattr(self, 'tab_filters'):
                self.tab_filters = self.tabFilters
                if HAS_STATIC:
                    static.log.debug("[ScannerSettingsAdvancedPopup] Converted tabFilters -> tab_filters")
            if hasattr(self, 'tabAlerts') and not hasattr(self, 'tab_alerts'):
                self.tab_alerts = self.tabAlerts
                if HAS_STATIC:
                    static.log.debug("[ScannerSettingsAdvancedPopup] Converted tabAlerts -> tab_alerts")

            self._init_tab1_basic()
            self._init_tab2_advanced()
            self._init_tab3_patterns()
            self._init_tab4_filters()
            self._init_tab5_alerts()

            if HAS_STATIC:
                static.log.info("[ScannerSettingsAdvancedPopup] Widget initialization complete")
        except Exception as e:
            if HAS_STATIC:
                static.log.error(f"[ScannerSettingsAdvancedPopup] Widget initialization error: {e}")
            else:
                print(f"[ScannerSettingsAdvancedPopup] Widget initialization error: {e}")

    def _init_tab1_basic(self):
        """Initialize Tab 1: Basic Indicators"""
        # Get coin list from static
        coins: list = []
        if HAS_STATIC and hasattr(static, 'chart') and hasattr(static.chart, 'coins'):
            coins = [coin.code for coin in static.chart.coins.values()]

        if not coins:
            coins = ["KRW-BTC", "KRW-ETH", "KRW-WAXP"]  # Fallback

        # Chart Comparison
        self.tab_basic.baseCoinCombo.clear()
        self.tab_basic.baseCoinCombo.addItems(coins)
        self.tab_basic.chartIntervalCombo.clear()
        self.tab_basic.chartIntervalCombo.addItems(self.TIMEFRAMES)

        # OHLC
        self.tab_basic.ohlcIntervalCombo.clear()
        self.tab_basic.ohlcIntervalCombo.addItems(self.TIMEFRAMES)
        conditions = ["이상", "이하", "초과", "미만"]
        for combo in [self.tab_basic.openCondition, self.tab_basic.closeCondition,
                      self.tab_basic.highCondition, self.tab_basic.lowCondition]:
            combo.clear()
            combo.addItems(conditions)

        # Golden Cross
        self.tab_basic.goldenShortInterval.clear()
        self.tab_basic.goldenShortInterval.addItems(self.TIMEFRAMES)
        self.tab_basic.goldenLongInterval.clear()
        self.tab_basic.goldenLongInterval.addItems(self.TIMEFRAMES)
        self.tab_basic.priceDiffCondition.clear()
        self.tab_basic.priceDiffCondition.addItems(["이하", "이상"])

        # Moving Average
        self.tab_basic.maInterval.clear()
        self.tab_basic.maInterval.addItems(self.TIMEFRAMES)
        self.tab_basic.maCondition.clear()
        self.tab_basic.maCondition.addItems([
            "골든크로스", "데드크로스", "단기>장기", "단기<장기"
        ])

        # RSI
        self.tab_basic.rsiInterval.clear()
        self.tab_basic.rsiInterval.addItems(self.TIMEFRAMES)
        self.tab_basic.rsiCondition.clear()
        self.tab_basic.rsiCondition.addItems(["이하", "이상"])

    def _init_tab2_advanced(self):
        """Initialize Tab 2: Advanced Indicators"""
        # All advanced indicators use default spinbox values set in UI
        pass

    def _init_tab3_patterns(self):
        """Initialize Tab 3: Patterns & Volume"""
        # Pattern and volume use default values set in UI
        pass

    def _init_tab4_filters(self):
        """Initialize Tab 4: Filters"""
        # Filters use default values set in UI
        pass

    def _init_tab5_alerts(self):
        """Initialize Tab 5: Alerts & Presets"""
        # Initialize preset combo
        presets = [
            "기본", "단타용", "스윙용",
            "사용자 정의 1", "사용자 정의 2", "사용자 정의 3",
            "사용자 정의 4", "사용자 정의 5"
        ]
        self.tab_alerts.presetCombo.clear()
        self.tab_alerts.presetCombo.addItems(presets)

    def _connect_signals(self):
        """Connect all signals"""
        try:
            # Apply/Cancel buttons
            self.applyButton.clicked.connect(self.accept)
            self.cancelButton.clicked.connect(self.reject)

            # Preset buttons (Tab 5) - with widget existence validation
            if hasattr(self.tab_alerts, 'savePreset'):
                self.tab_alerts.savePreset.clicked.connect(self._on_save_preset)
            if hasattr(self.tab_alerts, 'loadPreset'):
                self.tab_alerts.loadPreset.clicked.connect(self._on_load_preset)
            if hasattr(self.tab_alerts, 'deletePreset'):
                self.tab_alerts.deletePreset.clicked.connect(self._on_delete_preset)

            # Sound file selection button
            if hasattr(self.tab_alerts, 'soundFileButton'):
                self.tab_alerts.soundFileButton.clicked.connect(self._on_select_sound_file)

        except Exception as e:
            if HAS_STATIC:
                static.log.error(f"[ScannerSettingsAdvancedPopup] Signal connection error: {e}")
            else:
                print(f"[ScannerSettingsAdvancedPopup] Signal connection error: {e}")
            raise

    def _on_select_sound_file(self):
        """Open file dialog to select sound file"""
        if QFileDialog is None:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "사운드 파일 선택",
            "",
            "Audio Files (*.wav *.mp3 *.ogg);;All Files (*)"
        )
        if filename:
            print(f"Selected sound file: {filename}")

    def _on_save_preset(self):
        """Save current settings as a preset"""
        preset_name = self.tab_alerts.presetCombo.currentText()
        settings = self.get_settings()

        try:
            from .preset_manager import PresetManager
            pm = PresetManager()
            pm.save(preset_name, settings)
            print(f"Preset '{preset_name}' saved successfully")
        except ImportError:
            print("preset_manager not available")
        except Exception as e:
            print(f"Error saving preset: {e}")

    def _on_load_preset(self):
        """Load settings from a preset"""
        preset_name = self.tab_alerts.presetCombo.currentText()

        try:
            from .preset_manager import PresetManager
            pm = PresetManager()
            settings = pm.load(preset_name)
            if settings:
                self.apply_settings(settings)
                print(f"Preset '{preset_name}' loaded successfully")
            else:
                print(f"Preset '{preset_name}' not found")
        except ImportError:
            print("preset_manager not available")
        except Exception as e:
            print(f"Error loading preset: {e}")

    def _on_delete_preset(self):
        """Delete a preset"""
        preset_name = self.tab_alerts.presetCombo.currentText()

        # Don't delete built-in presets
        if preset_name in ["기본", "단타용", "스윙용"]:
            print(f"Cannot delete built-in preset: {preset_name}")
            return

        try:
            from .preset_manager import PresetManager
            pm = PresetManager()
            pm.delete(preset_name)
            print(f"Preset '{preset_name}' deleted successfully")
        except ImportError:
            print("preset_manager not available")
        except Exception as e:
            print(f"Error deleting preset: {e}")

    def get_settings(self) -> Dict[str, Any]:
        """
        Collect all settings from all tabs

        Returns:
            Dictionary with all scanner settings
        """
        if uic is None:
            return {}
        settings: Dict[str, Any] = {}

        # Tab 1: Basic Indicators
        settings.update(self._get_tab1_settings())

        # Tab 2: Advanced Indicators
        settings.update(self._get_tab2_settings())

        # Tab 3: Patterns & Volume
        settings.update(self._get_tab3_settings())

        # Tab 4: Filters
        settings.update(self._get_tab4_settings())

        # Tab 5: Alerts & Presets
        settings.update(self._get_tab5_settings())

        return settings

    def _get_tab1_settings(self) -> Dict[str, Any]:
        """Get settings from Tab 1: Basic Indicators"""
        return {
            # Chart Comparison
            'chart_compare_enabled': self.tab_basic.chartCompareEnable.isChecked(),
            'base_coin': self.tab_basic.baseCoinCombo.currentText(),
            'chart_interval': self.tab_basic.chartIntervalCombo.currentText(),

            # OHLC
            'ohlc_interval': self.tab_basic.ohlcIntervalCombo.currentText(),
            'open_value': self.tab_basic.openValue.value(),
            'open_condition': self.tab_basic.openCondition.currentText(),
            'close_value': self.tab_basic.closeValue.value(),
            'close_condition': self.tab_basic.closeCondition.currentText(),
            'high_value': self.tab_basic.highValue.value(),
            'high_condition': self.tab_basic.highCondition.currentText(),
            'low_value': self.tab_basic.lowValue.value(),
            'low_condition': self.tab_basic.lowCondition.currentText(),
            'exclude_recent': self.tab_basic.excludeRecent.value(),

            # Golden Cross
            'golden_enabled': self.tab_basic.goldenEnable.isChecked(),
            'golden_short_interval': self.tab_basic.goldenShortInterval.currentText(),
            'golden_short_period': self.tab_basic.goldenShortPeriod.value(),
            'golden_long_interval': self.tab_basic.goldenLongInterval.currentText(),
            'golden_long_period': self.tab_basic.goldenLongPeriod.value(),
            'use_price_diff': self.tab_basic.usePriceDiff.isChecked(),
            'price_diff_value': self.tab_basic.priceDiffValue.value(),
            'price_diff_condition': self.tab_basic.priceDiffCondition.currentText(),

            # Moving Average
            'ma_interval': self.tab_basic.maInterval.currentText(),
            'ma_short': self.tab_basic.maShortPeriod.value(),
            'ma_long': self.tab_basic.maLongPeriod.value(),
            'ma_condition': self.tab_basic.maCondition.currentText(),

            # RSI
            'rsi_interval': self.tab_basic.rsiInterval.currentText(),
            'rsi_period': self.tab_basic.rsiPeriod.value(),
            'rsi_threshold': self.tab_basic.rsiThreshold.value(),
            'rsi_condition': self.tab_basic.rsiCondition.currentText(),

            # RSI Divergence
            'rsi_div': {
                '1m': self.tab_basic.rsiDiv1m.isChecked(),
                '5m': self.tab_basic.rsiDiv5m.isChecked(),
                '15m': self.tab_basic.rsiDiv15m.isChecked(),
                '30m': self.tab_basic.rsiDiv30m.isChecked(),
                '1h': self.tab_basic.rsiDiv1h.isChecked(),
                '4h': self.tab_basic.rsiDiv4h.isChecked(),
                '1d': self.tab_basic.rsiDiv1d.isChecked(),
            },
            'rsi_div_max': self.tab_basic.rsiDivMax.value(),
            'rsi_div_min': self.tab_basic.rsiDivMin.value(),
            'rsi_div_ignore': self.tab_basic.rsiDivIgnore.value(),
            'rsi_div_time_allow': self.tab_basic.rsiDivTimeAllow.value(),
            'rsi_div_recent_exclude': self.tab_basic.rsiDivRecentExclude.value(),

            # Volume Surge
            'volume_surge': {
                '1m': self.tab_basic.vol1m.isChecked(),
                '5m': self.tab_basic.vol5m.isChecked(),
                '15m': self.tab_basic.vol15m.isChecked(),
                '30m': self.tab_basic.vol30m.isChecked(),
                '1h': self.tab_basic.vol1h.isChecked(),
                '4h': self.tab_basic.vol4h.isChecked(),
                '1d': self.tab_basic.vol1d.isChecked(),
            },
            'vol_avg_count': self.tab_basic.volAvgCount.value(),
            'vol_avg_ratio': self.tab_basic.volAvgRatio.value(),
        }

    def _get_tab2_settings(self) -> Dict[str, Any]:
        """Get settings from Tab 2: Advanced Indicators"""
        return {
            # Bollinger Bands
            'bb_period': self.tab_advanced.bbPeriod.value(),
            'bb_std_dev': self.tab_advanced.bbStdDev.value(),
            'bb_lower_touch': self.tab_advanced.bbLowerTouch.isChecked(),
            'bb_upper_touch': self.tab_advanced.bbUpperTouch.isChecked(),
            'bb_squeeze': self.tab_advanced.bbSqueeze.isChecked(),
            'bb_expand': self.tab_advanced.bbExpand.isChecked(),

            # MACD
            'macd_short': self.tab_advanced.macdShort.value(),
            'macd_long': self.tab_advanced.macdLong.value(),
            'macd_signal': self.tab_advanced.macdSignal.value(),
            'macd_golden': self.tab_advanced.macdGolden.isChecked(),
            'macd_dead': self.tab_advanced.macdDead.isChecked(),
            'macd_histo_inc': self.tab_advanced.macdHistoInc.isChecked(),
            'macd_divergence': self.tab_advanced.macdDivergence.isChecked(),

            # Stochastic
            'stoch_k': self.tab_advanced.stochK.value(),
            'stoch_d': self.tab_advanced.stochD.value(),
            'stoch_slow': self.tab_advanced.stochSlow.value(),
            'stoch_overbought': self.tab_advanced.stochOverbought.value(),
            'stoch_oversold': self.tab_advanced.stochOversold.value(),
            'stoch_k_gt_d': self.tab_advanced.stochKgtD.isChecked(),
            'stoch_k_lt_d': self.tab_advanced.stochKltD.isChecked(),

            # CCI
            'cci_period': self.tab_advanced.cciPeriod.value(),
            'cci_overbought': self.tab_advanced.cciOverbought.value(),
            'cci_oversold': self.tab_advanced.cciOversold.value(),

            # ATR
            'atr_period': self.tab_advanced.atrPeriod.value(),
            'atr_multiple': self.tab_advanced.atrMultiple.value(),
            'atr_increase': self.tab_advanced.atrIncrease.value(),

            # Fibonacci
            'fibo_period': self.tab_advanced.fiboPeriod.value(),
            'fibo_236': self.tab_advanced.fibo236.isChecked(),
            'fibo_382': self.tab_advanced.fibo382.isChecked(),
            'fibo_500': self.tab_advanced.fibo500.isChecked(),
            'fibo_618': self.tab_advanced.fibo618.isChecked(),
            'fibo_786': self.tab_advanced.fibo786.isChecked(),
            'fibo_tolerance': self.tab_advanced.fiboTolerance.value(),
        }

    def _get_tab3_settings(self) -> Dict[str, Any]:
        """Get settings from Tab 3: Patterns & Volume"""
        return {
            # Pattern Recognition
            'pattern_hammer': self.tab_patterns.patternHammer.isChecked(),
            'pattern_doji': self.tab_patterns.patternDoji.isChecked(),
            'pattern_triangle': self.tab_patterns.patternTriangle.isChecked(),
            'pattern_head_shoulder': self.tab_patterns.patternHeadShoulder.isChecked(),
            'pattern_double_top': self.tab_patterns.patternDoubleTop.isChecked(),
            'pattern_flag': self.tab_patterns.patternFlag.isChecked(),
            'pattern_wedge': self.tab_patterns.patternWedge.isChecked(),
            'pattern_period': self.tab_patterns.patternPeriod.value(),

            # Volume Analysis
            'obv_inc': self.tab_patterns.obvInc.isChecked(),
            'volume_ma_cross': self.tab_patterns.volumeMaCross.isChecked(),
            'volume_spike': self.tab_patterns.volumeSpike.isChecked(),
            'volume_dry_up': self.tab_patterns.volumeDryUp.isChecked(),
            'volume_spike_multiple': self.tab_patterns.volumeSpikeMultiple.value(),
        }

    def _get_tab4_settings(self) -> Dict[str, Any]:
        """Get settings from Tab 4: Filters"""
        return {
            # Price Filter
            'min_price': self.tab_filters.minPrice.value(),
            'max_price': self.tab_filters.maxPrice.value(),
            'min_market_cap': self.tab_filters.minMarketCap.value(),
            'max_market_cap': self.tab_filters.maxMarketCap.value(),
            'change_24h': self.tab_filters.change24h.value(),
            'from_52w_high': self.tab_filters.from52wHigh.value(),
            'from_52w_low': self.tab_filters.from52wLow.value(),

            # Time Filter
            'use_time_range': self.tab_filters.useTimeRange.isChecked(),
            'start_time': self.tab_filters.startTime.time().toString("HH:mm"),
            'end_time': self.tab_filters.endTime.time().toString("HH:mm"),
            'exclude_weekend': self.tab_filters.excludeWeekend.isChecked(),
            'exclude_market_start': self.tab_filters.excludeMarketStart.isChecked(),
            'exclude_market_end': self.tab_filters.excludeMarketEnd.isChecked(),
            'market_start_minutes': self.tab_filters.marketStartMinutes.value(),
            'market_end_minutes': self.tab_filters.marketEndMinutes.value(),

            # Coin Filter
            'favorite_only': self.tab_filters.favoriteOnly.isChecked(),
            'use_blacklist': self.tab_filters.useBlacklist.isChecked(),
            'blacklist': self.tab_filters.blacklistText.toPlainText(),
            'top_market_cap': self.tab_filters.topMarketCap.isChecked(),
            'top_market_cap_count': self.tab_filters.topMarketCapCount.value(),
            'top_volume': self.tab_filters.topVolume.isChecked(),
            'top_volume_count': self.tab_filters.topVolumeCount.value(),
        }

    def _get_tab5_settings(self) -> Dict[str, Any]:
        """Get settings from Tab 5: Alerts & Presets"""
        return {
            # Alert Settings
            'sound_alert': self.tab_alerts.soundAlert.isChecked(),
            'popup_alert': self.tab_alerts.popupAlert.isChecked(),
            'telegram_alert': self.tab_alerts.telegramAlert.isChecked(),
            'email_alert': self.tab_alerts.emailAlert.isChecked(),
            'telegram_token': self.tab_alerts.telegramToken.text(),
            'telegram_chat_id': self.tab_alerts.telegramChatId.text(),
            'email_address': self.tab_alerts.emailAddress.text(),
            'alert_cooldown': self.tab_alerts.alertCooldown.value(),

            # Auto Refresh
            'auto_refresh': self.tab_alerts.autoRefreshCheck.isChecked(),
            'auto_refresh_interval': self.tab_alerts.autoRefreshInterval.value(),

            # Current Preset
            'current_preset': self.tab_alerts.presetCombo.currentText(),
        }

    def apply_settings(self, settings: Dict[str, Any]) -> None:
        """
        Apply settings to all UI elements

        Args:
            settings: Dictionary with all scanner settings
        """
        # Placeholder for loading settings back into UI
        # Full implementation would set all widget values from settings dict
        print(f"Applying settings: {len(settings)} items")
