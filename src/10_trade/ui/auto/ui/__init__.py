# -*- coding: utf-8 -*-
"""
[Purpose]
- 11_server/settings/ui 패키지의 공개 진입점을 제공한다.

[Responsibilities]
- 서버 설정 UI 컨트롤러 클래스를 외부에서 쉽게 import 할 수 있도록 재노출한다.

[Dependencies]
- .widget_settings (SettingsWidget)
"""
from .widget_settings import SettingsWidget

__all__ = ['SettingsWidget']