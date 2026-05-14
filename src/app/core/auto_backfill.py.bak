# -*- coding: utf-8 -*-
"""
src.app.core.auto_backfill — AutoBackfillManager 재내보내기 모듈

AutoController(src/14_orchestrator/auto_controller.py)가
`from src.app.core.auto_backfill import AutoBackfillManager` 로 임포트합니다.
실제 구현은 src/14_orchestrator/auto_backfill.py 에 있으므로 그 파일을 래핑합니다.
"""
from __future__ import annotations

import importlib as _il
import logging as _log

_logger = _log.getLogger(__name__)

# 임포트 시도 순서: 일반적인 네임스페이스 → src 접두사 → 파일 직접 로딩
_CANDIDATES = (
    "14_orchestrator.auto_backfill",
    "src.14_orchestrator.auto_backfill",
)

_m = None
for _path in _CANDIDATES:
    try:
        _m = _il.import_module(_path)
        break
    except ImportError:
        continue

if _m is None:
    # 최후 수단: 파일 경로 직접 로딩
    import os as _os
    import importlib.util as _ilu

    _HERE = _os.path.dirname(_os.path.abspath(__file__))
    # src/app/core → src/14_orchestrator/auto_backfill.py
    _fp = _os.path.normpath(_os.path.join(_HERE, "..", "..", "14_orchestrator", "auto_backfill.py"))
    if _os.path.isfile(_fp):
        _spec = _ilu.spec_from_file_location("14_orchestrator.auto_backfill", _fp)
        if _spec and _spec.loader:
            _m = _ilu.module_from_spec(_spec)
            try:
                _spec.loader.exec_module(_m)  # type: ignore[union-attr]
            except (ImportError, AttributeError, OSError) as _exc:
                _logger.error("[auto_backfill shim] file-based load failed: %s", _exc)
                _m = None

if _m is None:
    raise ImportError(
        "AutoBackfillManager import failed: src/14_orchestrator/auto_backfill.py not found"
    )

AutoBackfillManager = getattr(_m, "AutoBackfillManager")
BackfillStartResult = getattr(_m, "BackfillStartResult")
create_auto_backfill_manager = getattr(_m, "create_auto_backfill_manager")
register_auto_backfill_manager = getattr(_m, "register_auto_backfill_manager")
get_registered_auto_backfill_manager = getattr(_m, "get_registered_auto_backfill_manager")

__all__ = [
    "AutoBackfillManager",
    "BackfillStartResult",
    "create_auto_backfill_manager",
    "register_auto_backfill_manager",
    "get_registered_auto_backfill_manager",
]
