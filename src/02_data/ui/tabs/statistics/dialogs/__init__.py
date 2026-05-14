# -*- coding: utf-8 -*-
"""
Package initializer for statistics.dialogs

이 패키지에는 statistics 탭과 관련된 다이얼로그 모듈만 노출합니다.
원래 __init__.py가 존재하지 않는 모듈을 import 하고 있었으므로
여기서는 실제로 존재하는 모듈(statistics_settings_dialog.py)만 안전하게 export 합니다.

뷰-컨트롤러 분리 원칙을 따르므로, __init__에서는 가벼운 노출만 수행합니다.
"""
from __future__ import annotations
from typing import Any

__all__ = ["SettingsDialog", "show_settings_dialog"]

try:
    # 실제로 존재하는 다이얼로그만 import 합니다.
    from .statistics_settings_dialog import SettingsDialog, show_settings_dialog  # type: ignore
except Exception:
    # PyQt 또는 UI 파일이 없을 때 안전한 실패를 위해 최소 스텁을 제공합니다.
    SettingsDialog = None  # type: ignore

    def show_settings_dialog(*args: Any, **kwargs: Any):
        raise RuntimeError("SettingsDialog is not available in this environment")