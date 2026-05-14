# -*- coding: utf-8 -*-
"""
14_orchestrator 패키지 초기화 모듈
(역할: 앱 시작 시 자동 실행)
"""
from __future__ import annotations

import importlib
import logging
import os
import threading
import builtins as _builtins
from typing import Optional, Any

__all__ = [
    "create_auto_backfill_manager",
    "register_auto_backfill_manager",
    "get_registered_auto_backfill_manager",
]

_log = logging.getLogger("14_orchestrator.__init__")
_auto_force_enqueue_guard_lock = threading.Lock()


def _orch_get_redis_url() -> str:
    """config.yaml 기반 Redis URL 반환 (fallback: 포트 58530)"""
    # 1순위: redis_factory (config.yaml 기반 설정)
    try:
        import importlib.util as _ilu
        import pathlib as _pl
        _factory_path = _pl.Path(__file__).resolve().parent.parent / "01_core" / "database" / "redis_factory.py"
        _spec = _ilu.spec_from_file_location("_redis_factory_orch", str(_factory_path))
        _factory_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_factory_mod)  # type: ignore[union-attr]
        _url = _factory_mod.get_redis_url()
        _log.debug("[Orchestrator] redis_factory URL: %s", _url)
        return _url
    except Exception as _e:
        _log.debug("[Orchestrator] redis_factory 로드 실패 (%s)", _e)

    # 2순위: 환경변수
    _redis_url = os.getenv("REDIS_URL", None)
    if _redis_url:
        _log.debug("[Orchestrator] REDIS_URL 환경변수 사용: %s", _redis_url)
        return _redis_url

    # 3순위: 기본값 (포트 58530)
    _log.debug("[Orchestrator] redis_factory 로드 실패, 기본 URL 사용")
    _password = os.getenv("REDIS_PASSWORD", "dummy")
    _default_url = f"redis://:{_password}@127.0.0.1:58530/0"
    _log.debug("[Orchestrator] 기본 Redis URL: %s", _default_url)
    return _default_url


def _resolve_static_module() -> Optional[Any]:
    candidates = (
        "src.11_server.app.static",
        "11_server.app.static",
        "app.static",
        "src.app.static",
        "static",
    )
    for name in candidates:
        try:
            mod = importlib.import_module(name)
            return mod
        except Exception:
            continue
    return None


def create_auto_backfill_manager(
    static: Optional[Any] = None,
    logger: Optional[logging.Logger] = None,
    on_run_complete: Optional[callable] = None,
    ready_wait_seconds: int = 15,
    ready_poll_interval: float = 1.0,
):
    try:
        mod = importlib.import_module("src.14_orchestrator.auto_backfill")
    except Exception:
        try:
            mod = importlib.import_module("14_orchestrator.auto_backfill")
        except Exception:
            _log.exception("Failed to import auto_backfill module")
            return None

    AB = getattr(mod, "AutoBackfillManager", None)
    if AB is None:
        _log.error("AutoBackfillManager class not found in auto_backfill module")
        return None

    try:
        mgr = AB(logger=logger, on_run_complete=on_run_complete, ready_wait_seconds=ready_wait_seconds, ready_poll_interval=ready_poll_interval)
    except Exception:
        _log.exception("Failed to instantiate AutoBackfillManager")
        return None

    if static is not None:
        register_auto_backfill_manager(mgr, static)
    return mgr


def register_auto_backfill_manager(mgr: Any, static: Optional[Any] = None) -> bool:
    if mgr is None:
        _log.warning("register_auto_backfill_manager called with None manager")
        return False

    target_static = static or _resolve_static_module()
    if target_static is None:
        _log.warning("No static module available to register AutoBackfillManager")
        return False

    existing = getattr(target_static, "auto_backfill_manager", None) or getattr(target_static, "AutoBackfillManager", None)
    if existing:
        _log.debug("AutoBackfillManager already registered on static - skipping duplicate registration")
        return False

    try:
        try:
            setattr(target_static, "auto_backfill_manager", mgr)
        except Exception:
            _log.debug("failed to set auto_backfill_manager attribute on static", exc_info=True)
        try:
            setattr(target_static, "AutoBackfillManager", mgr)
        except Exception:
            _log.debug("failed to set AutoBackfillManager attribute on static", exc_info=True)
        _log.info("AutoBackfillManager registered to static successfully")
        return True
    except Exception:
        _log.exception("Failed to register AutoBackfillManager to static")
        return False


def get_registered_auto_backfill_manager(static: Optional[Any] = None):
    target_static = static or _resolve_static_module()
    if target_static is None:
        return None
    return getattr(target_static, "auto_backfill_manager", None) or getattr(target_static, "AutoBackfillManager", None)


# 자동 GapConsumer 시작(옵션 환경변수로 제어)
try:
    from .gap_consumer import GapConsumerManager  # type: ignore
except Exception:
    GapConsumerManager = None

def _start_gap_consumer_if_enabled():
    enable = os.getenv("ENABLE_GAP_CONSUMER", "false").lower() in ("1", "true", "yes")
    if not enable:
        _log.debug("GapConsumer 자동 시작 비활성화됨 (ENABLE_GAP_CONSUMER=false)")
        return None
    try:
        gc_mgr = None
        if GapConsumerManager is not None:
            try:
                workers = int(os.getenv("GAP_CONSUMER_WORKERS", "1"))
            except Exception:
                workers = 1
            gc_mgr = GapConsumerManager(workers=workers, redis_url=_orch_get_redis_url(), poll_interval=float(os.getenv("GAP_CONSUMER_POLL", "1.0")))
            gc_mgr.start()
            _log.info("GapConsumerManager auto-started (workers=%s)", workers)
            try:
                comp_mod = importlib.import_module("11_server.component.component")
                if getattr(comp_mod, "static", None) is not None:
                    try:
                        setattr(comp_mod.static, "gap_consumer", gc_mgr)
                    except Exception:
                        _log.debug("failed to attach gap_consumer to static", exc_info=True)
            except Exception:
                _log.debug("component.static not available to attach gap_consumer", exc_info=True)
        else:
            _log.debug("GapConsumerManager not available (module import failed)")
        return gc_mgr
    except Exception:
        _log.exception("Failed to start GapConsumerManager")
        return None

_gap_consumer_instance = _start_gap_consumer_if_enabled()


# optional: 앱 시작 시 enqueue (환경변수로 제어)
try:
    from .enqueue_all import maybe_enqueue_on_startup  # type: ignore
except Exception:
    maybe_enqueue_on_startup = None

# --- 자동 강제 enqueue 로직(추가 기능) ---
try:
    AUTO_FORCE = os.getenv("AUTO_FORCE_ENQUEUE", "false").lower() in ("1", "true", "yes")
    REDIS_URL = _orch_get_redis_url()
    GAP_QUEUE = os.getenv("GAP_QUEUE", "gap_fill_queue")
    _log.debug("[Orchestrator] AUTO_FORCE_ENQUEUE init: AUTO_FORCE=%s, REDIS_URL=%s, GAP_QUEUE=%s", AUTO_FORCE, REDIS_URL, GAP_QUEUE)
except Exception as _init_exc:
    _log.warning("[Orchestrator] AUTO_FORCE_ENQUEUE 초기화 실패: %s", _init_exc)
    AUTO_FORCE = False
    REDIS_URL = "redis://:dummy@127.0.0.1:58530/0"
    GAP_QUEUE = "gap_fill_queue"

def _run_auto_force_enqueue_once() -> None:
    try:
        try:
            import redis as _redis
        except Exception:
            _redis = None

        do_enqueue = False
        if _redis is None:
            _log.warning("redis 패키지 미설치로 AUTO_FORCE_ENQUEUE 동작 불가")
            do_enqueue = False
        else:
            try:
                _log.debug("[Orchestrator] Redis 연결 시도: %s", REDIS_URL)
                # URL 파싱을 직접 수행하여 redis 구버전 호환성 확보
                from urllib.parse import urlparse
                parsed = urlparse(REDIS_URL)

                # None 값 및 빈 문자열 명시적 처리
                _host = parsed.hostname if (parsed.hostname and parsed.hostname.strip()) else '127.0.0.1'
                _port = parsed.port if parsed.port else 58530
                _db = 0
                if parsed.path:
                    _path_clean = parsed.path.strip('/')
                    if _path_clean and _path_clean.isdigit():
                        _db = int(_path_clean)
                _password = parsed.password if parsed.password else None

                _log.debug("[Orchestrator] Redis 연결 파라미터: host=%s, port=%s, db=%s", _host, _port, _db)

                r = _redis.Redis(
                    host=_host,
                    port=_port,
                    db=_db,
                    password=_password,
                    decode_responses=True
                )
                zcard = r.zcard(GAP_QUEUE)
                _log.debug("AUTO_FORCE_ENQUEUE: gap_fill_queue size=%s", zcard)
                if zcard == 0:
                    do_enqueue = True
            except Exception as _redis_exc:
                _log.exception("Redis 연결/조회 중 오류 (AUTO_FORCE_ENQUEUE 검사): %s", _redis_exc)
                do_enqueue = False

        if do_enqueue:
            try:
                delay = float(os.getenv("FORCE_ENQUEUE_DELAY_AFTER_STARTUP", "3.0"))
            except Exception:
                delay = 3.0
            _log.info(
                "AUTO_FORCE_ENQUEUE 조건 만족 - %ss 후 백그라운드 백필 enqueue 시작 (lookback_days=%s)",
                delay,
                os.getenv("FORCE_ENQUEUE_LOOKBACK_DAYS", "3"),
            )
            try:
                import time
                time.sleep(delay)
            except Exception:
                pass
            try:
                cnt = maybe_enqueue_on_startup()
                _log.info("AUTO_FORCE_ENQUEUE: enqueue 요청 완료 (등록된 갭백 수=%s)", cnt)
            except Exception as _enqueue_exc:
                _log.exception("AUTO_FORCE_ENQUEUE 실행 중 오류: %s", _enqueue_exc)
    except Exception as _outer_exc:
        _log.exception("AUTO_FORCE_ENQUEUE 초기화 중 오류: %s", _outer_exc)


def _start_auto_force_enqueue_background() -> None:
    """
    앱 시작(import) 경로를 블로킹하지 않기 위해 AUTO_FORCE_ENQUEUE를 백그라운드로 실행한다.
    또한 패키지가 별칭(src.14_orchestrator / 14_orchestrator)으로 중복 import 되어도
    프로세스당 1회만 시작되도록 builtins 전역 가드를 사용한다.
    """
    guard_name = "_UPBIT_ORCH_AUTO_FORCE_ENQUEUE_STARTED"
    try:
        with _auto_force_enqueue_guard_lock:
            if bool(getattr(_builtins, guard_name, False)):
                _log.debug("AUTO_FORCE_ENQUEUE already started in this process; skipping duplicate startup")
                return
            setattr(_builtins, guard_name, True)
    except AttributeError as _guard_exc:
        _log.warning("AUTO_FORCE_ENQUEUE guard check failed; continuing without global guard: %s", _guard_exc)

    try:
        t = threading.Thread(
            target=_run_auto_force_enqueue_once,
            daemon=True,
            name="orchestrator_auto_force_enqueue",
        )
        t.start()
    except RuntimeError:
        _log.exception("AUTO_FORCE_ENQUEUE 백그라운드 시작 실패")


if maybe_enqueue_on_startup is not None and AUTO_FORCE:
    _start_auto_force_enqueue_background()
