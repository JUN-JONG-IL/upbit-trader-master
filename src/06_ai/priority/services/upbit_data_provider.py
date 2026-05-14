#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[SHIM] Upbit ?곗씠???쒓났???????뚯씪? ?섏쐞 ?명솚???좎?瑜??꾪븳 ?섑띁?낅땲??

?ㅼ젣 援ы쁽: src/data_01/clients/upbit_data_provider.py

CHANGELOG:
- 2026-03-19 | Copilot | src/data_01/clients/upbit_data_provider.py 濡??대룞 ??shim ?좎?
"""
import importlib.util as _ilu
import os as _os

_path = _os.path.normpath(_os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)),
    "..", "..", "..", "data_01", "clients", "upbit_data_provider.py"
))
_spec = _ilu.spec_from_file_location("_02data_clients_upbit_data_provider", _path)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore

UpbitDataProvider = _mod.UpbitDataProvider

__all__ = ["UpbitDataProvider"]

