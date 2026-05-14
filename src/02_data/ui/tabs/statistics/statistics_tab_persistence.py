# -*- coding: utf-8 -*-
"""
Persistence 모듈
- 설정(settings) 및 컬럼 레이아웃(layouts)을 파일로 로드/저장하는 책임만 가집니다.
- 안전한(원자적) 저장 및 편의성 헬퍼(get_setting/set_setting)를 제공합니다.
"""
from __future__ import annotations
import json
import logging
import os
import tempfile
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
        # 기본 경로: ~/.upbit_trader/...
        base_dir = os.path.join(home, ".upbit_trader")
        self.layout_file = layout_file or os.path.join(base_dir, "statistics_tab_layout.json")
        self.settings_file = settings_file or os.path.join(base_dir, "statistics_tab_settings.json")

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

    def get_setting(self, key: str, default: Any = None) -> Any:
        """설정 조회 (없으면 default 반환)."""
        return self.settings.get(key, self.defaults.get(key, default))

    def set_setting(self, key: str, value: Any, persist: bool = False) -> None:
        """설정 변경. persist=True이면 파일로 즉시 저장합니다."""
        try:
            self.settings[key] = value
            if persist:
                self.save_settings()
        except Exception as e:
            logger.debug("[Persistence] set_setting 실패: %s", e)

    def reset_settings_to_defaults(self, persist: bool = False) -> None:
        """설정을 기본값으로 리셋."""
        try:
            self.settings = dict(self.defaults)
            if persist:
                self.save_settings()
        except Exception as e:
            logger.debug("[Persistence] reset_settings_to_defaults 실패: %s", e)

    def save_settings(self) -> None:
        """
        settings를 원자적으로 저장합니다:
        1) 같은 디렉토리에 임시 파일로 작성
        2) os.replace로 교체 (원자적 교체 보장)
        """
        try:
            d = os.path.dirname(self.settings_file)
            if d and not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            # 임시 파일을 같은 디렉토리에 생성
            fd, tmp_path = tempfile.mkstemp(dir=d or ".", prefix=".tmp_settings_", suffix=".json")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.settings, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self.settings_file)
            finally:
                # 안전을 위해 임시파일이 남아있으면 제거
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
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
        """layouts를 원자적으로 저장 (임시파일 → 교체)."""
        try:
            d = os.path.dirname(self.layout_file)
            if d and not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=d or ".", prefix=".tmp_layouts_", suffix=".json")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.column_layouts, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self.layout_file)
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("[Persistence] save_layouts 실패: %s", e)