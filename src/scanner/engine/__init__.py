# -*- coding: utf-8 -*-
"""
[Purpose]
- scanner(종목 스캐너) 기능 패키지의 공개 진입점을 제공한다.

[Responsibilities]
- UI, 로직, 워커, 모델, 지표, 패턴 모듈을 외부에서 쉽게 import할 수 있도록 재노출한다.

[Main Flow]
- window_main.py 등에서 `from src.scanner.engine import ScannerFrameWidget` 형태로 사용 가능.

[Dependencies]
- .ui (UI 컨트롤러)
- .logic (비즈니스 로직)
- .workers (백그라운드 작업)
- .models (데이터 모델)
- .indicators (기술 지표)
- .patterns (패턴 인식)

[Author] Copilot (Updated 2026-03-05)
"""

from .ui.widget_scanner_frame import ScannerFrameWidget
from .ui.popup_scanner_settings import ScannerSettingsPopup
from .ui.scanner_settings_advanced_popup import ScannerSettingsAdvancedPopup

from .logic.scanner_engine import ScannerEngine
from .logic.scanner_rules import RULES
from .logic.preset_manager import PresetManager
from .logic.condition_builder import ConditionBuilder
from .logic.filter_engine import FilterEngine

from .workers.scanner_worker import ScannerWorker
from .workers.data_fetcher import DataFetcher

from .models.scan_result import ScanResult
from .models.condition import Condition, ConditionGroup, ConditionOperator
from .models.preset import Preset

__all__ = [
    # UI 컴포넌트
    'ScannerFrameWidget',
    'ScannerSettingsPopup',
    'ScannerSettingsAdvancedPopup',

    # 로직
    'ScannerEngine',
    'RULES',
    'PresetManager',
    'ConditionBuilder',
    'FilterEngine',

    # 워커
    'ScannerWorker',
    'DataFetcher',

    # 모델
    'ScanResult',
    'Condition',
    'ConditionGroup',
    'ConditionOperator',
    'Preset',
]
