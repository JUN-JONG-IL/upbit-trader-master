#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[SHIM] src/data_01/pipeline/upbit_data_provider.py

?¤ì œ êµ¬í˜„?€ src/data_01/clients/upbit_data_provider.py ???ˆìŠµ?ˆë‹¤.

ë¬¸ì œ ëª…ì„¸ Phase 3-1?ì„œ ?¸ê¸‰??ê²½ë¡œ(pipeline/upbit_data_provider.py)ë¥?
clients/ ???¤ì œ êµ¬í˜„?¼ë¡œ ?°ê²°?˜ëŠ” ?˜ìœ„ ?¸í™˜??shim ?…ë‹ˆ??

CHANGELOG:
- 2026-03-19 | Copilot | pipeline/ ??clients/ shim ì¶”ê? (ë¬¸ì œ ëª…ì„¸ Phase 3-1)
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

