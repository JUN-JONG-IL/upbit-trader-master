# -*- coding: utf-8 -*-
"""
Gap Auto-Start 모듈

목적:
- 앱이 시작될 때 GapConsumer를 자동으로 백그라운드에서 실행하도록 지원합니다.
- 자동 시작은 환경변수 ENABLE_GAP_SERVICE 가 "1"로 설정된 경우에만 동작합니다.
- 이렇게 하면 기본 동작은 변경하지 않으면서 필요할 때만 Orchestrator에 Gap 서비스가 등록됩니다.

사용 방법:
1) 이 파일을 프로젝트에 추가합니다 (src/orchestrator/gap_auto_start.py).
2) 앱 실행 시 환경변수 설정으로 활성화:
   - ENABLE_GAP_SERVICE=1
   - TIMESCALE_DSN 및 REDIS_URL 환경변수는 이미 프로젝트에서 사용되는 값을 사용하도록 설정하세요.
3) 자동 시작을 비활성화하려면 ENABLE_GAP_SERVICE를 비워두거나 "0"으로 설정하면 됩니다.

동작 원리:
- 모듈 import 시 (예: 부트스트랩에서 import src.orchestrator.gap_auto_start)
  - ENABLE_GAP_SERVICE가 "1"이면 src.orchestrator.gap_service.start_service(...)를 호출합니다.
  - start_service는 내부적으로 현재 이벤트 루프 유무를 검사하여 안전하게 백그라운드에서 서비스(task/스레드)를 생성합니다.
- import-time에 무조건 실행되는 부작용을 최소화하기 위해 기본은 비활성화이며,
  환경변수로 명확히 활성화한 경우에만 동작합니다.

참고:
- 필요한 경우 부트스트랩에서 수동으로 start_service/start_service_async를 호출하도록 대체 가능.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

# Gap service 인터페이스 (이미 생성된 파일)
from src.orchestrator.gap_service import start_service  # type: ignore

logger = logging.getLogger("orchestrator.gap_auto_start")


def _should_enable() -> bool:
    """환경변수로 자동시작 여부 판별"""
    val = os.environ.get("ENABLE_GAP_SERVICE", "")
    return val == "1"


def _get_default_redis_url() -> str:
    """config.yaml 기반 Redis URL 반환 (fallback: 포트 58530, password=dummy)"""
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        return redis_url
    try:
        from _core.database.redis_factory import get_redis_url  # type: ignore
        return get_redis_url()
    except Exception:
        pass
    try:
        import importlib.util as _ilu
        import pathlib as _pl
        _factory_path = _pl.Path(__file__).resolve().parents[1] / "core" / "database" / "redis_factory.py"
        _spec = _ilu.spec_from_file_location("_redis_factory_gas", str(_factory_path))
        _factory_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_factory_mod)  # type: ignore[union-attr]
        return _factory_mod.get_redis_url()
    except Exception:
        return "redis://:dummy@127.0.0.1:58530/0"


def _get_cfg() -> tuple[Optional[str], str, float]:
    """
    환경변수에서 Timescale DSN, Redis URL, poll_interval을 읽음.
    - TIMESCALE_DSN: optional
    - REDIS_URL: config.yaml 기반 (환경변수 우선)
    - GAP_CONSUMER_POLL: 초 단위 폴링 간격
    """
    dsn = os.environ.get("TIMESCALE_DSN")
    redis_url = _get_default_redis_url()
    try:
        poll = float(os.environ.get("GAP_CONSUMER_POLL", "1.0"))
    except Exception:
        poll = 1.0
    return dsn, redis_url, poll


def auto_start_if_enabled():
    """
    자동 시작 체크 및 start_service 호출.
    - import 시 호출하도록만듬. (부작용을 줄이기 위해 ENABLE_GAP_SERVICE 체크)
    """
    try:
        if not _should_enable():
            logger.debug("[gap_auto_start] 자동 시작 비활성화(ENABLE_GAP_SERVICE != '1')")
            return
        dsn, redis_url, poll = _get_cfg()
        logger.info("[gap_auto_start] 자동 시작 활성화 - start_service 호출 (redis=%s)", redis_url)
        # start_service는 동기 함수이며 내부에서 이벤트 루프 유무를 처리하여
        # 백그라운드 스레드 또는 현재 루프에 태스크로 등록합니다.
        start_service(dsn, redis_url, poll_interval=poll)
    except Exception:
        logger.exception("[gap_auto_start] 자동 시작 중 예외 발생")


# 모듈 import 시 자동 실행 (조건부)
auto_start_if_enabled()