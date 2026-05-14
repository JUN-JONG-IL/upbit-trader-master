# -*- coding: utf-8 -*-
"""
Persistence 모듈
- 설정(settings) 및 컬럼 레이아웃(layouts)을 파일로 로드/저장하는 책임만 가집니다.
- 다른 모듈에서 Persistence 클래스를 import 하여 사용합니다.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "num_live_tabs": 3,
    "flush_interval_ms": 200,
    "flush_batch": 200,
    "max_pending": 100000,
    "enable_forwarding": True,
    "autostart_timer": True,
    "auto_load_history_on_start": False,
    "history_max_lines": 1000,
}


class Persistence:
    """설정 및 컬럼 레이아웃의 로드/저장 책임을 담당"""

    def __init__(
        self,
        layout_file: Optional[str] = None,
        settings_file: Optional[str] = None,
        defaults: Optional[Dict[str, Any]] = None,
    ):
        self.defaults = dict(defaults or _DEFAULTS)
        home = os.path.expanduser("~")
        self.layout_file = layout_file or os.path.join(home, ".upbit_trader", "statistics_tab_layout.json")
        self.settings_file = settings_file or os.path.join(home, ".upbit_trader", "statistics_tab_settings.json")

        self.settings: Dict[str, Any] = dict(self.defaults)
        self.column_layouts: Dict[str, List[int]] = {}

        self._load_settings()
        self._load_layouts()

    # ---- settings ----
    def _load_settings(self) -> None:
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.settings.update(data)
        except Exception as e:
            logger.debug("[Persistence] _load_settings 실패: %s", e)

    def save_settings(self) -> None:
        try:
            d = os.path.dirname(self.settings_file)
            if d and not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug("[Persistence] save_settings 실패: %s", e)

    # ---- layouts ----
    def _load_layouts(self) -> None:
        try:
            if os.path.exists(self.layout_file):
                with open(self.layout_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.column_layouts = {k: [int(x) for x in v] for k, v in data.items() if isinstance(v, (list, tuple))}
        except Exception as e:
            logger.debug("[Persistence] _load_layouts 실패: %s", e)
            self.column_layouts = {}

    def save_layouts(self) -> None:
        try:
            d = os.path.dirname(self.layout_file)
            if d and not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            with open(self.layout_file, "w", encoding="utf-8") as f:
                json.dump(self.column_layouts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug("[Persistence] save_layouts 실패: %s", e)