#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Backward-compat shim ??canonical location: src/data_01/core/data_manager.py

???μΌ?€ src/data_01/core/data_manager.py λ΅??΄λ™?μ—?µλ‹??
?μ„ ?Έν™?±μ„ ?„ν•΄ ? μ??©λ‹??
"""
import importlib.util as _ilu
import os as _os

_path = _os.path.normpath(_os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)),
    "..", "..", "data_01", "core", "data_manager.py"
))
_spec = _ilu.spec_from_file_location("_02data_core_data_manager", _path)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore

DataManager = _mod.DataManager

__all__ = ["DataManager"]

