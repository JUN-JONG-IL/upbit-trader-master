#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[SHIM] Upbit 데이터 제공자 — 이 파일은 하위 호환성 유지를 위한 래퍼입니다.

실제 구현: src/data_01/clients/upbit_data_provider.py

CHANGELOG:
- 2026-03-19 | Copilot | src/data_01/clients/upbit_data_provider.py 로 이동 후 shim 유지
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
