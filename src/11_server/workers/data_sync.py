#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Backward-compat shim — canonical location: src/02_data/workers/data_sync.py

이 파일은 src/02_data/workers/data_sync.py 로 이동되었습니다.
하위 호환성을 위해 유지됩니다.
"""
import importlib.util as _ilu
import os as _os

_path = _os.path.normpath(_os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)),
    "..", "..", "02_data", "workers", "data_sync.py"
))
_spec = _ilu.spec_from_file_location("_02data_workers_data_sync", _path)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore

DataSyncWorker = _mod.DataSyncWorker
hydrate_redis = _mod.hydrate_redis

__all__ = ["DataSyncWorker", "hydrate_redis"]
