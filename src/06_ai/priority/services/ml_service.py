#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
[SHIM] ML 서비스 모듈 — 이 파일은 하위 호환성 유지를 위한 래퍼입니다.

실제 구현: src/06_ai/ai_engine/ml_service.py

CHANGELOG:
- 2026-03-19 | Copilot | src/06_ai/ai_engine/ml_service.py 로 이동 후 shim 유지
"""
import importlib.util as _ilu
import os as _os

_path = _os.path.normpath(_os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)),
    "..", "..", "ai_engine", "ml_service.py"
))
_spec = _ilu.spec_from_file_location("_06ai_ai_engine_ml_service", _path)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore

MLService = _mod.MLService

__all__ = ["MLService"]
