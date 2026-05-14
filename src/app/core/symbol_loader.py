# -*- coding: utf-8 -*-
"""
심볼 로더
- Upbit API에서 전체 심볼 로드
- MongoDB/TimescaleDB에 저장
- GapFinder 초기화
- AutoBackfill 시작
"""
from __future__ import annotations

import asyncio as aio
import os
import platform
from typing import List, Tuple
from types import SimpleNamespace

from .logger import SafeLogger
from .module_loader import try_import_names

try:
    import aiopyupbit
except ImportError:
    aiopyupbit = None


def should_fetch_all_symbols_from_settings(log: SafeLogger) -> bool:
    """TimescaleSettings 우선순위 플래그 확인"""
    names = ("data_01.timescale.timescale_settings", "src.data_01.timescale.timescale_settings", "timescale.timescale_settings")
    mod, _ = try_import_names(names)
    
    if not mod:
        return True
    
    TimescaleSettings = getattr(mod, "TimescaleSettings", None)
    if not TimescaleSettings:
        return True
    
    try:
        ts = TimescaleSettings()
        conn = ts.load_connection() or {}
        priority_keys = ("volume", "ai_reco", "popular", "favorite", "hot", "first_fetch")
        for k in priority_keys:
            v = conn.get(k)
            if isinstance(v, bool) and v:
                return False
            if isinstance(v, (str, int)) and str(v).lower() in ("1", "true", "yes", "on"):
                return False
    except Exception:
        log.debug("[bootstrap] TimescaleSettings check failed", exc_info=True)
    
    return True


def ensure_initial_symbols(static: SimpleNamespace, log: SafeLogger) -> None:
    """초기 심볼 수집 및 저장"""
    try:
        if not should_fetch_all_symbols_from_settings(log):
            log.debug("[init] Priority settings present — skipping full symbols fetch")
            return
        
        log.info("[init] No priority settings set — fetching full Upbit symbol list")
        
        codes = []
        
        # Windows aiodns 호환성
        if platform.system().lower().startswith("windows"):
            try:
                if hasattr(aio, "WindowsSelectorEventLoopPolicy"):
                    aio.set_event_loop_policy(aio.WindowsSelectorEventLoopPolicy())
                    log.debug("[init] Set WindowsSelectorEventLoopPolicy for aiodns compatibility")
            except Exception:
                log.debug("[init] Failed to set WindowsSelectorEventLoopPolicy", exc_info=True)
        
        # Upbit API에서 심볼 로드
        if aiopyupbit is not None:
            try:
                codes = aio.run(aiopyupbit.get_tickers(fiat=getattr(static, "FIAT", "KRW"), contain_name=True))
            except Exception:
                try:
                    codes = aio.run(aiopyupbit.get_tickers(fiat=getattr(static, "FIAT", "KRW"), contain_name=False))
                except Exception:
                    log.debug("[init] aiopyupbit ticker fetch failed", exc_info=True)
                    codes = []
        else:
            log.debug("[init] aiopyupbit not available; skipping remote ticker fetch")

        normalized: List[Tuple[str, str]] = []
        if codes and isinstance(codes, (list, tuple)):
            for item in codes:
                if isinstance(item, dict):
                    sym = item.get("market") or item.get("symbol") or item.get("code") or str(item)
                    kname = item.get("korean_name") or item.get("name") or ""
                    normalized.append((kname, sym))
                else:
                    normalized.append(("", str(item)))
        
        static.available_symbols = normalized
        log.info("[init] Loaded %d upbit symbols as initial set", len(normalized))
        
        # MongoDB 저장
        try:
            from .module_loader import try_load_from_files
            
            mod, _ = try_import_names(("data_01.mongodb.init_mongodb", "src.data_01.mongodb.init_mongodb", "mongodb.init_mongodb"))
            
            if not mod:
                file_path = os.path.join("data_01", "mongodb", "init_mongodb.py")
                mod, _ = try_load_from_files([file_path], alias_prefix="init_mongodb")
            
            if mod:
                save_fn = getattr(mod, "save_symbols_to_mongodb", None)
                if callable(save_fn) and codes:
                    aio.run(save_fn(codes))
                    log.debug("[init] Persisted symbols to MongoDB metadata collection")
        except Exception:
            log.debug("[init] MongoDB persist skipped", exc_info=True)
        
        # TimescaleSettings 저장
        try:
            mod, _ = try_import_names(("data_01.timescale.timescale_settings",))
            if mod:
                TimescaleSettings = getattr(mod, "TimescaleSettings", None)
                if TimescaleSettings:
                    ts = TimescaleSettings()
                    save_fn = getattr(ts, "save_symbols", None)
                    if callable(save_fn):
                        try:
                            save_fn(normalized)
                            log.debug("[init] Persisted available symbols via TimescaleSettings.save_symbols()")
                        except Exception:
                            log.debug("[init] TimescaleSettings.save_symbols failed", exc_info=True)
        except Exception:
            pass
        
        # GapFinder 초기화 (백그라운드 실행 — 로그인/UI 진입을 블로킹하지 않음)
        # 부팅 시 256개 심볼 × 다중 TF에 대한 갭 검출은 수십 초가 소요될 수 있어
        # 메인 스레드에서 동기 실행하면 로그인창이 늦게 뜬다.
        # daemon 스레드로 분리하여 init_snapshots 호출이 로그인 흐름을 방해하지 않도록 한다.
        try:
            gap_mod, _ = try_import_names(("data_01.timescale.operations.gap_finder", "src.data_01.timescale.operations.gap_finder"))
            if gap_mod:
                GapFinder = getattr(gap_mod, "GapFinder", None)
                if GapFinder:
                    symbol_codes = [s[1] for s in normalized if isinstance(s, tuple) and len(s) >= 2]

                    def _run_gap_init_bg() -> None:
                        try:
                            GapFinder().init_snapshots(symbol_codes)
                        except Exception:
                            log.debug("[init] GapFinder.init_snapshots failed (background)", exc_info=True)

                    try:
                        import threading as _threading
                        _t = _threading.Thread(
                            target=_run_gap_init_bg,
                            name="gap_finder_init_bg",
                            daemon=True,
                        )
                        _t.start()
                        log.info("[init] GapFinder.init_snapshots 백그라운드 시작 (로그인 비차단)")
                    except Exception:
                        # 스레드 생성 실패 시 폴백: 종전과 동일 동기 호출
                        try:
                            GapFinder().init_snapshots(symbol_codes)
                        except Exception:
                            log.debug("[init] GapFinder.init_snapshots failed (sync fallback)", exc_info=True)
        except Exception:
            log.debug("[init] GapFinder init skipped", exc_info=True)
        
        # AutoBackfill 초기 트리거
        try:
            from .backfill_manager import get_auto_backfill_helpers
            
            create_fn, register_fn, get_fn = get_auto_backfill_helpers()
            mgr = None
            
            if get_fn:
                try:
                    mgr = get_fn(static)
                except Exception:
                    try:
                        mgr = get_fn()
                    except Exception:
                        mgr = None
            
            if mgr is None and create_fn:
                try:
                    mgr = create_fn(static, logger=getattr(static, "log", None))
                    if mgr and register_fn:
                        try:
                            register_fn(mgr, static)
                        except Exception:
                            log.debug("[init] register_auto_backfill_manager failed (non-fatal)", exc_info=True)
                except Exception:
                    log.debug("[init] create_auto_backfill_manager failed", exc_info=True)
            
            static.auto_backfill_manager = mgr
            
            try:
                auto_env = os.getenv("AUTO_BACKFILL_ON_STARTUP", "1")
                auto_ok = str(auto_env).lower() not in ("0", "false", "no", "")
                enable_ai_env = os.getenv("ENABLE_AI", "0")
                ai_enabled = str(enable_ai_env).lower() not in ("0", "false", "no", "")
                
                if mgr and auto_ok and not ai_enabled:
                    try:
                        # force=True: symbols were just loaded above into static.available_symbols,
                        # but _has_symbols_available() checks src.server.app.static (which has
                        # chart=None at startup), so the readiness check would always fail here.
                        # Since we know symbols are ready, bypass the check directly.
                        res = getattr(mgr, "run_once_nonblocking", lambda *a, **k: False)(force=True)
                        log.info("[init] AutoBackfillManager created; run_once_nonblocking invoked (started=%s)", bool(res))
                    except Exception:
                        log.debug("[init] AutoBackfill run_once_nonblocking failed", exc_info=True)
                else:
                    if mgr:
                        log.info("[init] AutoBackfillManager created but automatic run skipped (AUTO_ON=%s, AI=%s)", auto_ok, ai_enabled)
            except Exception:
                log.debug("[init] AutoBackfill startup control failed", exc_info=True)
        except Exception:
            log.debug("[init] AutoBackfill initial creation skipped", exc_info=True)
            
    except Exception:
        log.exception("[init] _ensure_initial_symbols failed")