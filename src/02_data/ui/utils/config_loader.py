# -*- coding: utf-8 -*-
"""
config_loader.py — config/config.yaml 로드 유틸리티

lru_cache를 이용한 싱글턴 패턴으로 중복 로드를 방지합니다.
환경 변수가 config 값보다 항상 우선합니다.

주요 함수:
  - load_config()                   → Dict  전체 config 반환
  - get_symbol_query_limit()        → int   DB 심볼 쿼리 LIMIT
  - get_ws_max_subscribe()          → int   WebSocket 최대 구독 수
  - get_confirm_before_delete()     → bool  삭제 확인 팝업 여부
  - get_progress_dialog_threshold() → int   대용량 삭제 진행률 임계값
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _find_config_path() -> Path:
    """config/config.yaml 파일 경로를 안정적으로 탐색합니다.

    전략:
      1. 현재 파일 기준으로 상위 디렉토리를 순회하며 config/config.yaml 탐색
      2. 환경변수 APP_CONFIG_PATH 가 설정된 경우 최우선 사용
    """
    # 환경변수 오버라이드
    env_path = os.getenv("APP_CONFIG_PATH")
    if env_path:
        return Path(env_path)

    # 현재 파일 기준 상위 디렉토리 순회
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "config" / "config.yaml"
        if candidate.exists():
            return candidate

    # 최후 폴백: 파일 위치 기준 4단계 상위 (기존 동작 유지)
    return here.parents[4] / "config" / "config.yaml"


_CONFIG_PATH = _find_config_path()


@lru_cache(maxsize=1)
def load_config() -> Dict[str, Any]:
    """config/config.yaml 을 읽어 dict 로 반환합니다.

    파일이 없거나 yaml 파싱 실패 시 빈 dict를 반환합니다.
    lru_cache 로 중복 로드가 방지됩니다.
    """
    try:
        import yaml  # type: ignore[import]
    except ImportError:
        logger.warning("[config_loader] PyYAML 미설치 — pip install pyyaml")
        return {}

    try:
        with open(_CONFIG_PATH, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        logger.debug("[config_loader] config.yaml 로드 완료: %s", _CONFIG_PATH)
        return data
    except FileNotFoundError:
        logger.debug("[config_loader] config.yaml 없음: %s", _CONFIG_PATH)
        return {}
    except Exception as exc:
        logger.warning("[config_loader] config.yaml 파싱 오류: %s", exc)
        return {}


def invalidate_cache() -> None:
    """캐시를 무효화합니다. 런타임 설정 변경 후 호출하세요."""
    load_config.cache_clear()
    logger.debug("[config_loader] 캐시 무효화 완료")


def get_symbol_query_limit() -> int:
    """DB 심볼 목록 조회 최대 개수를 반환합니다.

    설정 경로: ui.db_viewer.symbol_query_limit
    기본값: 10000
    """
    cfg = load_config()
    try:
        return int(cfg["ui"]["db_viewer"]["symbol_query_limit"])
    except (KeyError, TypeError, ValueError):
        return 10_000


def get_ws_max_subscribe() -> int:
    """WebSocket 최대 구독 심볼 수를 반환합니다.

    우선순위: 환경변수 UPBIT_WS_MAX_SUBSCRIBE > config.yaml > 기본값(300)
    설정 경로: websocket.upbit.max_subscribe
    """
    # 환경변수가 존재하면 최우선
    env_val = os.getenv("UPBIT_WS_MAX_SUBSCRIBE")
    if env_val is not None:
        try:
            return int(env_val)
        except ValueError:
            logger.warning("[config_loader] UPBIT_WS_MAX_SUBSCRIBE 값 파싱 실패: %s", env_val)

    cfg = load_config()
    try:
        return int(cfg["websocket"]["upbit"]["max_subscribe"])
    except (KeyError, TypeError, ValueError):
        return 300


def get_confirm_before_delete() -> bool:
    """삭제 전 확인 팝업 표시 여부를 반환합니다.

    설정 경로: db_management.confirm_before_delete
    기본값: True (안전을 위해 기본 활성화)
    """
    cfg = load_config()
    try:
        return bool(cfg["db_management"]["confirm_before_delete"])
    except (KeyError, TypeError):
        return True


def get_progress_dialog_threshold() -> int:
    """대용량 삭제 시 진행률 표시 임계값(건수)을 반환합니다.

    설정 경로: db_management.progress_dialog_threshold
    기본값: 10000
    """
    cfg = load_config()
    try:
        return int(cfg["db_management"]["progress_dialog_threshold"])
    except (KeyError, TypeError, ValueError):
        return 10000


def get_max_markets() -> int:
    """업비트 REST /v1/market/all 조회 최대 심볼 수를 반환합니다.

    설정 경로: collection.max_markets
    기본값: 300
    """
    cfg = load_config()
    try:
        return int(cfg["collection"]["max_markets"])
    except (KeyError, TypeError, ValueError):
        return 300
