# -*- coding: utf-8 -*-
"""
UI 유틸리티 패키지 (v4.0 - 완전 모듈화)

구조:
    constants.py       — 공통 상수
    db_connectors.py   — DB 싱글톤 커넥터
    module_finder.py   — static 모듈 / RealtimeManager 탐색
    formatters.py      — 포맷 유틸리티
    db_status.py       — DB 연결 상태 조회
    data_queries.py    — 데이터 조회 함수
    network_helpers.py — TCP/HTTP probe
    config_helpers.py  — YAML/JSON 설정

CHANGELOG:
    v4.0 (2026-04-28) | Copilot | utils.py 완전 모듈화, _ui_utils_main 하위 호환 유지
"""
from __future__ import annotations

import logging
import sys
import types as _types

_logger = logging.getLogger(__name__)

# ============================================================
# 서브모듈에서 직접 import
# ============================================================
from .constants import ALLOWED_TABLES, GB, KB, MB, STATIC_MODULE_KEYS
from .config_helpers import (
    get_db_config_json_path,
    get_db_config_yaml_path,
    load_db_config,
    save_db_config,
)
from .data_queries import (
    get_active_symbols,
    get_backfill_progress,
    get_cache_stats,
    get_gap_queue_count_from_redis,
    get_gap_queue_count_realtime,
    get_gap_worker_status,
    get_gaps,
    get_pipeline_stats,
    get_table_stats,
    get_websocket_stats,
)
from .db_connectors import (
    get_mongo_sync_client,
    get_redis_connector,
    get_timescale_connector,
)
from .db_status import (
    get_clickhouse_status,
    get_gap_queue_size,
    get_kafka_status,
    get_mlflow_status,
    get_mongo_status,
    get_postgres_status,
    get_redis_status,
    get_timescale_status,
)
from .formatters import format_bytes, format_duration, format_timestamp
from .module_finder import (
    _find_static_module,
    get_auto_backfill_manager,
    get_realtime_manager,
)
from .network_helpers import http_probe, parse_hostport, tcp_probe

# ============================================================
# 하위 호환성: _ui_utils_main 이름으로 sys.modules 등록
# 기존 코드가 sys.modules["_ui_utils_main"]로 함수를 조회할 경우 대비
# ============================================================
_compat_mod = _types.ModuleType("_ui_utils_main")
_compat_mod.__dict__.update(
    {
        k: v
        for k, v in globals().items()
        if not k.startswith("_") or k in ("_find_static_module",)
    }
)
sys.modules.setdefault("_ui_utils_main", _compat_mod)

_logger.info("[utils.__init__] ✅ utils.py 로드 성공 (모듈화 버전)")

# ============================================================
# __all__
# ============================================================
__all__ = [
    # constants
    "KB",
    "MB",
    "GB",
    "STATIC_MODULE_KEYS",
    "ALLOWED_TABLES",
    # db_connectors
    "get_timescale_connector",
    "get_redis_connector",
    "get_mongo_sync_client",
    # module_finder
    "get_realtime_manager",
    "get_auto_backfill_manager",
    # formatters
    "format_bytes",
    "format_duration",
    "format_timestamp",
    # db_status
    "get_timescale_status",
    "get_redis_status",
    "get_mongo_status",
    "get_postgres_status",
    "get_kafka_status",
    "get_clickhouse_status",
    "get_mlflow_status",
    "get_gap_queue_size",
    # data_queries
    "get_active_symbols",
    "get_websocket_stats",
    "get_backfill_progress",
    "get_gap_queue_count_from_redis",
    "get_gap_queue_count_realtime",
    "get_gap_worker_status",
    "get_gaps",
    "get_table_stats",
    "get_pipeline_stats",
    "get_cache_stats",
    # network_helpers
    "tcp_probe",
    "http_probe",
    "parse_hostport",
    # config_helpers
    "get_db_config_yaml_path",
    "get_db_config_json_path",
    "load_db_config",
    "save_db_config",
]

_loaded_count = sum(1 for name in __all__ if globals().get(name) is not None)
_logger.info("[utils.__init__] 🎉 함수 로드 완료: %d/%d개", _loaded_count, len(__all__))