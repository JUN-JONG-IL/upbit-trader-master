# -*- coding: utf-8 -*-
"""UI 유틸리티 공통 상수 (v1.0)"""
from __future__ import annotations

from typing import FrozenSet, Tuple

# 바이트 단위 변환 상수
KB: int = 1024
MB: int = 1024 ** 2
GB: int = 1024 ** 3

# static 모듈 검색 키 목록 (sys.modules 탐색 순서)
STATIC_MODULE_KEYS: Tuple[str, ...] = (
    "static-fallback",
    "server.app.static",
    "src.server.app.static",
    "src.server.app.static.static",
    "src._server.app.static",
    "_server_static",
    "static",
    "app.static",
    "src.static",
    "server.static",
    "src.app.static",
)

# ── 수집 설정 제한값 ───────────────────────────────────────────────────
MAX_CANDLE_LIMIT: int = 10_000       # 사용자 설정 최대 캔들 수
DEFAULT_CANDLE_LIMIT: int = 10_000   # 기본 캔들 조회 수
WARN_SUBSCRIBE_THRESHOLD: int = 1_000  # WebSocket 구독 수 경고 임계값
MAX_SUBSCRIBE_LIMIT: int = 10_000    # WebSocket 최대 구독 수

# 허용된 테이블 이름 (SQL Injection 방지)
ALLOWED_TABLES: FrozenSet[str] = frozenset({
    "staging_candles",
    "candles",
    "isolated_candles",
    "gap_fill_queue",
})
