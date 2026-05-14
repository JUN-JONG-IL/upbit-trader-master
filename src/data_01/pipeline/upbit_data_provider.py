#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[SHIM] src/data_01/pipeline/upbit_data_provider.py

?ㅼ젣 援ы쁽? src/data_01/clients/upbit_data_provider.py ???덉뒿?덈떎.

臾몄젣 紐낆꽭 Phase 3-1?먯꽌 ?멸툒??寃쎈줈(pipeline/upbit_data_provider.py)瑜?
clients/ ???ㅼ젣 援ы쁽?쇰줈 ?곌껐?섎뒗 ?섏쐞 ?명솚??shim ?낅땲??

CHANGELOG:
- 2026-03-19 | Copilot | pipeline/ ??clients/ shim 異붽? (臾몄젣 紐낆꽭 Phase 3-1)
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

