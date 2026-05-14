#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
[Purpose]
- login(로그인) 기능 패키지의 공개 진입점을 제공한다.

[Responsibilities]
- gui_main 및 LoginWidget을 외부에서 import 하기 쉽게 재노출한다.
- services 모듈 re-export (하위 호환성)

[Main Flow]
- main.py 등에서 `from auth import gui_main` 형태로 사용 가능.

[Dependencies]
- .ui.widget_login
- .services
"""

from .ui.widget_login import gui_main, LoginWidget
from .services import AuthService, SessionManager, TwoFactorAuth

__all__ = [
    'gui_main',
    'LoginWidget',
    'AuthService',
    'SessionManager',
    'TwoFactorAuth',
]