# -*- coding: utf-8 -*-
"""
설정 파일 유틸리티 (YAML/JSON 로드/저장)
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
DB_CONFIG_YAML = os.path.join(REPO_ROOT, "src", "core", "config", "db_connections.yaml")
DB_CONFIG_JSON = os.path.join(REPO_ROOT, "src", "core", "config", "db_connections.json")


def get_db_config_yaml_path() -> str:
    return DB_CONFIG_YAML


def get_db_config_json_path() -> str:
    return DB_CONFIG_JSON


def load_db_config() -> Dict[str, Any]:
    """YAML 우선, 실패 시 JSON으로 폴백하여 설정 로드"""
    try:
        import yaml
        if os.path.isfile(DB_CONFIG_YAML):
            with open(DB_CONFIG_YAML, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception:
        pass
    try:
        if os.path.isfile(DB_CONFIG_JSON):
            with open(DB_CONFIG_JSON, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def save_db_config(config: Dict[str, Any]) -> bool:
    """YAML 우선 저장, 실패 시 JSON으로 폴백"""
    try:
        import yaml
        os.makedirs(os.path.dirname(DB_CONFIG_YAML), exist_ok=True)
        with open(DB_CONFIG_YAML, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True, default_flow_style=False)
        return True
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(DB_CONFIG_JSON), exist_ok=True)
        with open(DB_CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        pass
    return False
