# -*- coding: utf-8 -*-
"""
AutoBackfill 관리 헬퍼
- AutoBackfillManager 생성/등록/스케줄링
"""
from __future__ import annotations

import importlib
import time
import threading
from types import SimpleNamespace
from typing import Optional, Tuple, Callable

from .logger import SafeLogger
from .module_loader import try_import_names


def import_14_orchestrator_pkg() -> Optional[object]:
    """14_orchestrator 패키지 import"""
    pkg, attempts = try_import_names(("src.14_orchestrator", "14_orchestrator"))
    return pkg


def get_auto_backfill_helpers() -> Tuple[Optional[Callable], Optional[Callable], Optional[Callable]]:
    """
    create_auto_backfill_manager, register_auto_backfill_manager, get_registered_auto_backfill_manager
    를 가진 패키지/모듈을 반환(또는 None들).
    """
    pkg = import_14_orchestrator_pkg()
    if pkg:
        create_fn = getattr(pkg, "create_auto_backfill_manager", None)
        register_fn = getattr(pkg, "register_auto_backfill_manager", None)
        get_fn = getattr(pkg, "get_registered_auto_backfill_manager", None)
        return create_fn, register_fn, get_fn
    
    # fallback: try direct module import
    try:
        mod, _ = try_import_names(("src.14_orchestrator.auto_backfill", "14_orchestrator.auto_backfill"))
        if mod:
            create_fn = getattr(mod, "create_auto_backfill_manager", None)
            register_fn = getattr(mod, "register_auto_backfill_manager", None)
            get_fn = getattr(mod, "get_registered_auto_backfill_manager", None)
            return create_fn, register_fn, get_fn
    except Exception:
        pass
    
    return None, None, None


def auto_backfill_job(static: SimpleNamespace, log: SafeLogger):
    """주기적 AutoBackfill 실행"""
    try:
        log.debug("[main] AutoBackfill scheduled invocation")
        mgr = getattr(static, "auto_backfill_manager", None)
        
        # prefer registered getter if available
        try:
            _, _, get_fn = get_auto_backfill_helpers()
            if get_fn and mgr is None:
                found = None
                try:
                    found = get_fn(static)
                except Exception:
                    try:
                        found = get_fn()
                    except Exception:
                        found = None
                if found:
                    mgr = found
        except Exception:
            pass

        if mgr is None:
            # fallback: try to create manager now but do not force start automatically
            try:
                create_fn, register_fn, _ = get_auto_backfill_helpers()
                if create_fn:
                    try:
                        new_mgr = create_fn(static, logger=getattr(static, "log", None))
                        if new_mgr and register_fn:
                            try:
                                register_fn(new_mgr, static)
                            except Exception:
                                log.debug("[main] register_auto_backfill_manager failed (non-fatal)", exc_info=True)
                        mgr = new_mgr
                        log.debug("[main] AutoBackfillManager instance created at invocation time (no automatic run)")
                    except Exception:
                        log.exception("[main] Failed to create AutoBackfillManager at invocation time")
            except Exception:
                pass

        if mgr is None:
            log.debug("[main] AutoBackfillManager class not available; skipping invocation")
            return

        try:
            run_fn = getattr(mgr, "run_once_nonblocking", None)
            if callable(run_fn):
                res = run_fn()
                # last_start_result 에서 원인 코드 읽기 (BackfillStartResult enum이 있으면 사용)
                reason_code = "UNKNOWN"
                reason_desc = ""
                try:
                    last_result = getattr(mgr, "last_start_result", None)
                    if last_result is not None:
                        reason_code = str(getattr(last_result, "value", last_result))
                        reason_desc = str(getattr(last_result, "description", ""))
                except Exception:
                    pass
                if bool(res):
                    log.debug("[main] AutoBackfill.run_once_nonblocking 시작됨 [%s]", reason_code)
                else:
                    log.debug(
                        "[main] AutoBackfill.run_once_nonblocking 보류 [%s] — %s",
                        reason_code, reason_desc,
                    )
            else:
                log.debug("[main] auto_backfill_manager has no run_once_nonblocking")
        except Exception:
            log.exception("[main] AutoBackfill.run_once_nonblocking failed")
    except Exception:
        log.exception("[main] _auto_backfill_job unexpected error")


def ensure_auto_backfill_scheduled_async(scheduler, static: SimpleNamespace, log: SafeLogger, max_wait_seconds: int = 60):
    """AutoBackfillManager가 늦게 생성될 경우를 대비한 watcher"""
    def _watcher():
        waited = 0
        poll_interval = 2
        log.debug("[main][watcher] Started AutoBackfill watcher (max_wait=%ds)", max_wait_seconds)
        
        while waited <= max_wait_seconds:
            try:
                mgr = getattr(static, "auto_backfill_manager", None)
                if mgr is not None:
                    interval_sec = 30
                    try:
                        ts_mod = importlib.import_module("data_01.timescale.timescale_settings")
                        TimescaleSettings = getattr(ts_mod, "TimescaleSettings", None)
                        if TimescaleSettings:
                            ts = TimescaleSettings()
                            conn = ts.load_connection() or {}
                            interval_sec = max(5, int(conn.get("backfill_interval_sec", 30)))
                    except Exception:
                        pass
                    
                    try:
                        scheduler.add_job(
                            lambda: auto_backfill_job(static, log),
                            "interval",
                            seconds=interval_sec,
                            id="auto_backfill_periodic",
                            replace_existing=True,
                            max_instances=1
                        )
                        log.info("[main][watcher] Scheduled AutoBackfill periodic job every %ds (detected late manager)", interval_sec)
                    except Exception:
                        log.exception("[main][watcher] Failed to schedule AutoBackfill periodic job (detected late manager)")
                    return
            except Exception:
                log.debug("[main][watcher] exception during watcher loop", exc_info=True)
            
            time.sleep(poll_interval)
            waited += poll_interval
        
        log.debug("[main][watcher] AutoBackfillManager not found within watcher timeout; giving up")
    
    t = threading.Thread(target=_watcher, daemon=True, name="auto_backfill_watcher")
    t.start()


def start_scheduler(static: SimpleNamespace, log: SafeLogger):
    """스케줄러 시작 및 AutoBackfill 스케줄링"""
    scheduler = None
    try:
        from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore
        scheduler = BackgroundScheduler()
        scheduler.start()
        static.scheduler = scheduler
        log.info("[main] Scheduler started")
    except Exception:
        log.info("[main] Scheduler could not be started (skipping scheduling).")
        scheduler = None
        static.scheduler = None

    # AutoBackfill scheduling
    try:
        manager = getattr(static, "auto_backfill_manager", None)
        
        if manager is None:
            create_fn, register_fn, get_fn = get_auto_backfill_helpers()
            
            if get_fn:
                try:
                    found = get_fn(static)
                    if found:
                        manager = found
                except Exception:
                    try:
                        found = get_fn()
                        if found:
                            manager = found
                    except Exception:
                        manager = None
            
            if manager is None and create_fn:
                try:
                    new_mgr = create_fn(static, logger=getattr(static, "log", None))
                    if new_mgr and register_fn:
                        try:
                            register_fn(new_mgr, static)
                        except Exception:
                            log.debug("[main] register_auto_backfill_manager failed (non-fatal)", exc_info=True)
                    manager = new_mgr
                    log.info("[main] AutoBackfillManager instance created at scheduling time (no automatic run)")
                except Exception:
                    log.exception("[main] Failed to create AutoBackfillManager at scheduling time")
        
        if manager and scheduler:
            try:
                scheduler.remove_job("auto_backfill_periodic")
            except Exception:
                pass
            
            interval_sec = 30
            try:
                ts_mod = importlib.import_module("data_01.timescale.timescale_settings")
                TimescaleSettings = getattr(ts_mod, "TimescaleSettings", None)
                if TimescaleSettings:
                    ts = TimescaleSettings()
                    conn = ts.load_connection() or {}
                    interval_sec = max(5, int(conn.get("backfill_interval_sec", 30)))
            except Exception:
                pass
            
            try:
                scheduler.add_job(
                    lambda: auto_backfill_job(static, log),
                    "interval",
                    seconds=interval_sec,
                    id="auto_backfill_periodic",
                    replace_existing=True,
                    max_instances=1
                )
                log.info("[main] Scheduled AutoBackfill periodic job every %ds", interval_sec)
            except Exception:
                log.exception("[main] Failed to schedule AutoBackfill periodic job")
        else:
            if scheduler is None:
                log.info("[main] Scheduler not available; skipping auto backfill scheduling")
            else:
                log.info("[main] No AutoBackfillManager available at scheduling time; starting watcher")
                ensure_auto_backfill_scheduled_async(scheduler, static, log, max_wait_seconds=60)
    except Exception:
        log.debug("[main] AutoBackfill scheduling skipped", exc_info=True)

    # staging_candles 주기적 flush 스케줄링 (60초마다)
    if scheduler is not None:
        try:
            from .db_initializer import flush_staging_candles_once
            
            def _flush_staging_candles_job():
                """BackgroundScheduler에서 주기적으로 실행되는 staging_candles flush 작업"""
                try:
                    count = flush_staging_candles_once(log)
                    if count > 0:
                        log.info("[flush_staging_job] 주기적 flush 완료: %d건", count)
                except Exception:
                    log.debug("[flush_staging_job] 예외 발생", exc_info=True)
            
            scheduler.add_job(
                _flush_staging_candles_job,
                "interval",
                seconds=60,
                id="staging_candles_periodic_flush",
                replace_existing=True,
                max_instances=1,
            )
            log.info("[main] staging_candles 주기적 flush 스케줄 등록 완료 (60초마다)")
        except Exception:
            log.debug("[main] staging_candles 주기적 flush 스케줄 등록 실패 (계속 진행)", exc_info=True)
