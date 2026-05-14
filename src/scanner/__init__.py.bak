# -*- coding: utf-8 -*-
"""
[Purpose]
- 07_scanner 모듈 진입점

[Responsibilities]
- scanner 하위 패키지의 주요 심볼을 최상위에서 재노출한다.

[Author] Copilot (Updated 2026-03-05)
"""
try:
    from .engine import (
        ScannerFrameWidget,
        ScannerSettingsPopup,
        ScannerSettingsAdvancedPopup,
        ScannerEngine,
        RULES,
        PresetManager,
        ScannerWorker,
        ConditionBuilder,
        FilterEngine,
        DataFetcher,
        ScanResult,
        Condition,
        ConditionGroup,
        ConditionOperator,
        Preset,
    )
except ImportError:
    # Allow the package to be imported in headless/test environments
    # where PyQt5 or other heavy dependencies are not installed.
    pass

__all__ = [
    'ScannerFrameWidget',
    'ScannerSettingsPopup',
    'ScannerSettingsAdvancedPopup',
    'ScannerEngine',
    'RULES',
    'PresetManager',
    'ScannerWorker',
    'ConditionBuilder',
    'FilterEngine',
    'DataFetcher',
    'ScanResult',
    'Condition',
    'ConditionGroup',
    'ConditionOperator',
    'Preset',
]
