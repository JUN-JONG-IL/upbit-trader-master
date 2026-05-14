# Advanced Scanner UI Documentation

## Overview
This directory contains 6 UI files for the advanced cryptocurrency scanner feature. The UI is optimized for 17" laptops (1920x1080 resolution) and follows the project's UI Style Guide.

## Files Created

### 1. Main Dialog: `scanner_settings_advanced_popup.ui`
- **Window Size**: 1200x800
- **Title**: "종목 스캐너 상세 설정"
- **Components**:
  - QTabWidget with 5 tabs
  - Bottom button panel with [적용] and [취소] buttons
- **Purpose**: Container for all advanced scanner settings

### 2. Tab 1: `tab_basic_indicators.ui` (기본 지표)
Three-column layout with 7 indicator groups:

**Left Column:**
1. **차트비교 (자동대교)** - Chart comparison settings
2. **OHLC** - Open/High/Low/Close price filters

**Center Column:**
3. **골든크로스 (데드크로스)** - Golden/Dead cross detection
4. **이동평균** - Moving average settings

**Right Column:**
5. **RSI** - Relative Strength Index
6. **RSI 다이버전스** - RSI divergence detection (7 timeframes)
7. **평균거래량 대비 거래량급등** - Volume surge detection (7 timeframes)

### 3. Tab 2: `tab_advanced_indicators.ui` (고급 지표)
Three-column layout with 6 indicator groups:

**Left Column:**
8. **볼린저 밴드** - Bollinger Bands (period, std dev, touch/squeeze/expand)
9. **MACD** - Moving Average Convergence Divergence

**Center Column:**
10. **스토캐스틱** - Stochastic oscillator
11. **CCI** - Commodity Channel Index

**Right Column:**
12. **ATR** - Average True Range
13. **피보나치 되돌림** - Fibonacci retracement levels

### 4. Tab 3: `tab_patterns_volume.ui` (패턴 & 거래량)
Two-column layout with 2 groups:

**Left Column:**
14. **패턴 인식** - Pattern recognition (7 patterns: hammer, doji, triangle, head & shoulders, double top/bottom, flag, wedge)

**Center Column:**
15. **거래량 분석** - Volume analysis (OBV, MA cross, spike, dry-up)

### 5. Tab 4: `tab_filters.ui` (필터)
Three-column layout with 3 filter groups:

**Left Column:**
16. **가격 필터** - Price filters (min/max price, market cap, 24h change, 52w high/low)

**Center Column:**
17. **시간 필터** - Time filters (time range, weekend exclusion, market start/end exclusion)

**Right Column:**
18. **종목 필터** - Coin filters (favorites, blacklist, top market cap/volume)

### 6. Tab 5: `tab_alerts_presets.ui` (알림 & 프리셋)
Horizontal layout with 2 sections plus bottom controls:

**Left Section:**
- **알림 설정** - Alert settings (sound, popup, Telegram, email)

**Right Section:**
- **프리셋 관리** - Preset management (8 presets: 기본, 단타용, 스윙용, 사용자 정의 1-5)

**Bottom:**
- Auto-refresh settings

## Widget Statistics

| File | GroupBoxes | CheckBoxes | ComboBoxes | SpinBoxes | DoubleSpinBoxes | Labels | Buttons | LineEdits | TextEdits | TimeEdits |
|------|------------|------------|------------|-----------|-----------------|--------|---------|-----------|-----------|-----------|
| Main Dialog | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
| Tab 1 | 7 | 17 | 14 | 14 | 5 | 25 | 0 | 0 | 0 | 0 |
| Tab 2 | 6 | 15 | 0 | 15 | 3 | 18 | 0 | 0 | 0 | 0 |
| Tab 3 | 2 | 11 | 0 | 1 | 1 | 2 | 0 | 0 | 0 | 0 |
| Tab 4 | 3 | 8 | 0 | 11 | 0 | 14 | 0 | 0 | 1 | 2 |
| Tab 5 | 2 | 5 | 1 | 2 | 0 | 5 | 4 | 3 | 0 | 0 |

**Total Indicator Groups**: 20 (including alert and preset groups)

## Styling Compliance

All UI files follow `docs/development/UI_STYLE_GUIDE.md`:

### Critical Styling Features:
✅ **QComboBox**: Includes `color: #111111` and `QAbstractItemView` styling
✅ **QCheckBox**: Includes both default and `:hover` state with `color: #111111`
✅ **QGroupBox**: Proper border, background, and title color
✅ **All input widgets**: Proper color and focus states
✅ **Consistent color palette**: Uses #111111 for text, #3b82f6 for accents

### Why This Matters:
- Prevents text invisibility issues in dropdowns
- Ensures text remains visible when hovering over checkboxes
- Consistent user experience across all dialogs
- Optimized for 17" laptop screens (1920x1080)

## Usage Example

```python
from PyQt5 import uic
from PyQt5.QtWidgets import QDialog

class ScannerSettingsAdvancedDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Load main dialog
        uic.loadUi('src/scanner/scanner_settings_advanced_popup.ui', self)
        
        # Load tab UIs
        uic.loadUi('src/scanner/tab_basic_indicators.ui', self.tab_basic)
        uic.loadUi('src/scanner/tab_advanced_indicators.ui', self.tab_advanced)
        uic.loadUi('src/scanner/tab_patterns_volume.ui', self.tab_patterns)
        uic.loadUi('src/scanner/tab_filters.ui', self.tab_filters)
        uic.loadUi('src/scanner/tab_alerts_presets.ui', self.tab_alerts)
        
        # Connect signals
        self.applyButton.clicked.connect(self.on_apply)
        self.cancelButton.clicked.connect(self.reject)
```

## Indicator Groups Summary

1. 차트비교 (Chart Comparison)
2. OHLC (Open/High/Low/Close)
3. 골든크로스 (Golden/Dead Cross)
4. 이동평균 (Moving Average)
5. RSI (Relative Strength Index)
6. RSI 다이버전스 (RSI Divergence)
7. 평균거래량 대비 거래량급등 (Volume Surge)
8. 볼린저 밴드 (Bollinger Bands)
9. MACD
10. 스토캐스틱 (Stochastic)
11. CCI (Commodity Channel Index)
12. ATR (Average True Range)
13. 피보나치 되돌림 (Fibonacci Retracement)
14. 패턴 인식 (Pattern Recognition)
15. 거래량 분석 (Volume Analysis)
16. 가격 필터 (Price Filter)
17. 시간 필터 (Time Filter)
18. 종목 필터 (Coin Filter)
19. 알림 설정 (Alert Settings)
20. 프리셋 관리 (Preset Management)

## Design Decisions

### Window Size: 1200x800
- Optimized for 17" laptops (1920x1080 resolution)
- Leaves room for taskbar and other windows
- Comfortable viewing without scrolling

### Three-Column Layout
- Maximizes horizontal space usage
- Groups related indicators together
- Reduces vertical scrolling
- Better visual organization

### Explicit Styling
- All widgets have explicit color properties
- Prevents Qt theme inconsistencies
- Ensures readability across different systems
- Follows proven patterns from existing UI files

## Validation

All files have been validated for:
- ✅ Valid XML syntax
- ✅ Proper Qt Designer structure
- ✅ Style guide compliance
- ✅ Widget naming conventions
- ✅ Korean label support

## Future Enhancements

Potential additions:
- Save/load custom indicator combinations
- Export/import settings as JSON
- Indicator testing against historical data
- Performance optimization for real-time scanning
- Additional pattern recognition algorithms

---

**Last Updated**: 2026-02-08
**Version**: 2.0
**Author**: GitHub Copilot
