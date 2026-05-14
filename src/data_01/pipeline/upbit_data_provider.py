#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[SHIM] src/data_01/pipeline/upbit_data_provider.py

실제 구현은 src/data_01/clients/upbit_data_provider.py 에 있습니다.

문제 명세 Phase 3-1에서 언급된 경로(pipeline/upbit_data_provider.py)를
clients/ 의 실제 구현으로 연결하는 하위 호환성 shim 입니다.

CHANGELOG:
- 2026-03-19 | Copilot | pipeline/ → clients/ shim 추가 (문제 명세 Phase 3-1)
"""
from __future__ import annotations

import importlib.util as _ilu
import os as _os
import sys as _sys

_path = _os.path.normpath(_os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)),
    "..", "clients", "upbit_data_provider.py"
))

_MODULE_NAME = "_02data_clients_upbit_data_provider"
if _MODULE_NAME not in _sys.modules:
    _spec = _ilu.spec_from_file_location(_MODULE_NAME, _path)
    _mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
    _sys.modules[_MODULE_NAME] = _mod
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
else:
    _mod = _sys.modules[_MODULE_NAME]

UpbitDataProvider = _mod.UpbitDataProvider

__all__ = ["UpbitDataProvider"]
