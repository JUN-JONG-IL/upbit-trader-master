# -*- coding: utf-8 -*-
"""
app.ui.resources - UI 리소스 파일 경로 헬퍼
"""
from pathlib import Path

RESOURCES_DIR = Path(__file__).parent

def get_resource_path(filename: str) -> Path:
    """Return the absolute path to a resource file in this directory."""
    return RESOURCES_DIR / filename

__all__ = ["RESOURCES_DIR", "get_resource_path"]
