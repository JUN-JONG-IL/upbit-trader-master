# -*- coding: utf-8 -*-
"""
로그인 윈도우 - core/auth 모듈 연동
"""
from __future__ import annotations
import sys
from pathlib import Path

# core/auth 임포트 경로 보장
_core_dir = str(Path(__file__).parents[4] / "core")
if _core_dir not in sys.path:
    sys.path.insert(0, _core_dir)

try:
    from auth.login_widget import LoginWidget as LoginWindow  # type: ignore
except ImportError:
    try:
        from auth.auth_widget import AuthWidget as LoginWindow  # type: ignore
    except ImportError:
        LoginWindow = None  # type: ignore

__all__ = ["LoginWindow"]
