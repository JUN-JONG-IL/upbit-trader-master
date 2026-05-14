#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Backward-compat shim ??canonical location: src/data_01/workers/aggregator.py

???뚯씪? src/data_01/workers/aggregator.py 濡??대룞?섏뿀?듬땲??
?섏쐞 ?명솚?깆쓣 ?꾪빐 ?좎??⑸땲??
"""
import importlib.util as _ilu
import os as _os

_path = _os.path.normpath(_os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)),
    "..", "..", "data_01", "workers", "aggregator.py"
))
_spec = _ilu.spec_from_file_location("_02data_workers_aggregator", _path)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore

Aggregator = _mod.Aggregator
refresh_cagg = _mod.refresh_cagg

__all__ = ["Aggregator", "refresh_cagg"]

