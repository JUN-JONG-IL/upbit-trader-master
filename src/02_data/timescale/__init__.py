# -*- coding: utf-8 -*-
"""
timescale 패키지 (shim)
- 이 패키지는 레포의 shim 모듈(src/timescale/operations/candle_writer.py)을 포함하며,
  pipeline_loader가 'timescale.*' 네임스페이스로 import 할 때 안정적으로 로드되도록 합니다.
"""
try:
    from .pool import (
        init_global_pool,
        get_connection,
        release_connection,
        close_global_pool,
    )
    __all__ = [
        "init_global_pool",
        "get_connection",
        "release_connection",
        "close_global_pool",
    ]
except Exception:
    __all__ = []
