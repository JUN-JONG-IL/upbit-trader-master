# -*- coding: utf-8 -*-
"""
遺?몄뒪?몃옪 紐⑤뱢 (紐⑤뱢??踰꾩쟾)
- 紐⑹쟻: ??珥덇린???먮쫫 愿由?
- ?먯튃: 500~700以??쒗븳 以??
- ??留덉씠洹몃젅?댁뀡 ?먮룞 ?ㅽ뻾 異붽? (?숈쟻 ?꾪룷??
- 蹂寃? GUI 紐⑤뱶????臾닿굅??珥덇린?붾뒗 諛깃렇?쇱슫???ㅻ젅?쒕줈 ?ㅽ뻾?섏뿬 UI ?곗꽑 ?쒖꽦??蹂댁옣
"""
from __future__ import annotations

import atexit
import asyncio as aio
import logging
import os
import platform
import threading
from multiprocessing import Queue, freeze_support
from types import SimpleNamespace

# ??紐⑤뱢?붾맂 core ?⑦궎吏?먯꽌 import
from .core import (
    create_safe_logger,
    ensure_src_root_on_path,
    schedule_websocket_start,
    try_import_names,
)

# src 猷⑦듃 寃쎈줈 蹂댁옣
SRC_ROOT = ensure_src_root_on_path()

# ?꾩뿭 濡쒓굅
log = create_safe_logger("bootstrap")

# ------------------- ?≪쓬??濡쒓굅 ?듭젣 -------------------
try:
    _lc_path = os.path.join(SRC_ROOT, "01_core", "config", "logging_config.py")
    if os.path.isfile(_lc_path):
        import importlib.util as _ilu
        _lc_spec = _ilu.spec_from_file_location("logging_config", _lc_path)
        if _lc_spec and _lc_spec.loader:
            _lc_mod = _ilu.module_from_spec(_lc_spec)
            _lc_spec.loader.exec_module(_lc_mod)
            _suppress_fn = getattr(_lc_mod, "suppress_noisy_loggers", None)
            if callable(_suppress_fn):
                _suppress_fn()
except Exception:
    pass

# ?꾩뿭 而⑦뀒?대꼫
static: SimpleNamespace = SimpleNamespace()
RealtimeManager = None
Account = None
SignalManager = None


def _do_full_init(sync_mode: bool = False) -> None:
    """
    ?ㅼ젣 臾닿굅??珥덇린?붾? ?섑뻾?섎뒗 ?⑥닔?낅땲??
    - sync_mode=True 硫??숆린 ?ㅽ뻾 (nogui ?곹솴)
    - sync_mode=False 硫?諛깃렇?쇱슫???곕が) ?ㅻ젅?쒖뿉???ㅽ뻾?⑸땲??
    """
    try:
        log.info("[_do_full_init] full init started (sync_mode=%s)", sync_mode)

        # 1. ?고???紐⑤뱢 濡쒕뱶
        from .core.runtime_loader import load_runtime_modules
        load_runtime_modules(static, log)

        # 2. DB 寃利?諛?留덉씠洹몃젅?댁뀡 (?숈쟻?쇰줈 濡쒕뱶/?ㅽ뻾)
        try:
            from .core.db_initializer import validate_db_connections
            validate_db_connections(static, log)
        except Exception:
            log.debug("[_do_full_init] validate_db_connections failed or skipped", exc_info=True)

        try:
            log.info("[init] ?봽 留덉씠洹몃젅?댁뀡 泥댄겕 ?쒖옉...")

            ts_connector = getattr(static, "timescale_connector", None)
            if ts_connector is None:
                try:
                    _ts_db_path = os.path.join(SRC_ROOT, "data_01", "timescale", "timescale_db.py")
                    if os.path.isfile(_ts_db_path):
                        import importlib.util as _ilu
                        _ts_spec = _ilu.spec_from_file_location("timescale_db_fallback", _ts_db_path)
                        if _ts_spec and _ts_spec.loader:
                            _ts_mod = _ilu.module_from_spec(_ts_spec)
                            _ts_spec.loader.exec_module(_ts_mod)
                            get_connector_fn = getattr(_ts_mod, "get_timescale_connector", None)
                            if callable(get_connector_fn):
                                ts_connector = get_connector_fn()
                                static.timescale_connector = ts_connector
                                log.debug("[_do_full_init] TimescaleDB 而ㅻ꽖???앹꽦 ?꾨즺 (?숈쟻 濡쒕뱶)")
                            else:
                                log.warning("[_do_full_init] ?좑툘 get_timescale_connector ?⑥닔瑜?李얠쓣 ???놁쓬")
                    else:
                        log.warning("[_do_full_init] ?좑툘 timescale_db.py ?뚯씪??李얠쓣 ???놁쓬")
                except Exception as exc:
                    log.warning("[_do_full_init] ?좑툘 TimescaleDB 而ㅻ꽖???앹꽦 ?ㅽ뙣: %s", exc)
            if ts_connector is not None:
                try:
                    _migration_path = os.path.join(
                        SRC_ROOT, "data_01", "timescale", "migrations",
                        "add_staging_processed_column.py"
                    )
                    if os.path.isfile(_migration_path):
                        import importlib.util as _ilu
                        _mig_spec = _ilu.spec_from_file_location(
                            "migration_staging_processed", _migration_path
                        )
                        if _mig_spec and _mig_spec.loader:
                            _mig_mod = _ilu.module_from_spec(_mig_spec)
                            _mig_spec.loader.exec_module(_mig_mod)
                            migrate_sync_fn = getattr(_mig_mod, "migrate_sync", None)
                            if callable(migrate_sync_fn):
                                try:
                                    if migrate_sync_fn(ts_connector):
                                        log.info("[init] ??留덉씠洹몃젅?댁뀡 ?꾨즺 (staging_candles.processed)")
                                    else:
                                        log.warning("[init] ?좑툘 留덉씠洹몃젅?댁뀡 ?ㅽ뙣 (怨꾩냽 吏꾪뻾)")
                                except Exception as exc:
                                    log.warning("[init] ?좑툘 migrate_sync raised: %s", exc, exc_info=True)
                            else:
                                log.warning("[init] ?좑툘 migrate_sync ?⑥닔瑜?李얠쓣 ???놁쓬")
                    else:
                        log.debug("[_do_full_init] 留덉씠洹몃젅?댁뀡 ?ㅽ겕由쏀듃 ?놁쓬 (?ㅽ궢)")
                except Exception as exc:
                    log.error("[init] ??留덉씠洹몃젅?댁뀡 ?ㅽ뻾 ?ㅽ뙣: %s", exc)

        except Exception as exc:
            log.error("[init] ??留덉씠洹몃젅?댁뀡 泥댄겕 ?ㅽ뙣: %s", exc)

        # Windows asyncio policy / multiprocessing (?대? ?ㅼ젙?섏뼱 ?덉쓣 ???덉쓬)
        try:
            set_windows_selector = globals().get("set_windows_selector_event_loop_global")
            if callable(set_windows_selector):
                set_windows_selector()
            else:
                if platform.system().lower().startswith("windows"):
                    try:
                        if hasattr(aio, "WindowsSelectorEventLoopPolicy"):
                            aio.set_event_loop_policy(aio.WindowsSelectorEventLoopPolicy())
                            log.debug("[_do_full_init] Applied WindowsSelectorEventLoopPolicy")
                    except Exception:
                        log.debug("[_do_full_init] Failed to apply WindowsSelectorEventLoopPolicy", exc_info=True)
        except Exception:
            log.debug("[_do_full_init] setting windows selector failed", exc_info=True)

        try:
            set_mp = globals().get("set_multiprocessing_context")
            if callable(set_mp):
                set_mp()
        except Exception:
            log.debug("[_do_full_init] setting multiprocessing context failed", exc_info=True)
        freeze_support()

        # Ensure signal queue exists (UI may rely on this)
        try:
            if not getattr(static, "signal_queue", None):
                static.signal_queue = Queue()
        except Exception:
            static.signal_queue = Queue()

        # RealtimeManager ?앹꽦 (媛?ν븯硫?
        try:
            log.info("[_do_full_init] Creating RealtimeManager...")
            RealtimeManagerCls = getattr(static, "RealtimeManager", None)
            codes = []
            try:
                import aiopyupbit
                ticker_timeout = float(os.getenv("INIT_TICKER_TIMEOUT_SEC", "1.5"))
                try:
                    codes = aio.run(
                        aio.wait_for(
                            aiopyupbit.get_tickers(fiat=getattr(static, "FIAT", "KRW"), contain_name=True),
                            timeout=ticker_timeout,
                        )
                    )
                except Exception:
                    try:
                        codes = aio.run(
                            aio.wait_for(
                                aiopyupbit.get_tickers(fiat=getattr(static, "FIAT", "KRW"), contain_name=False),
                                timeout=ticker_timeout,
                            )
                        )
                    except Exception:
                        log.warning("[_do_full_init] aiopyupbit ticker fetch timed out/failed ??鍮??щ낵濡?吏꾪뻾")
                        codes = []
            except ImportError:
                log.debug("[_do_full_init] aiopyupbit not installed; skipping remote ticker fetch")
                codes = []

            if RealtimeManagerCls is not None:
                try:
                    static.chart = RealtimeManagerCls(codes=codes)
                    static.realtime_manager = static.chart
                    static.rt_manager = static.chart
                    static.manager = static.chart
                    log.info("[_do_full_init] ??RealtimeManager ?깅줉 ?꾨즺 (%d媛?醫낅ぉ)", len(codes))
                except Exception as exc:
                    log.error("[_do_full_init] ??RealtimeManager ?앹꽦 ?ㅽ뙣: %s", exc, exc_info=True)
                    static.chart = SimpleNamespace(codes=codes, start=lambda *a, **kw: None, alive=False)
                    static.realtime_manager = static.chart
                    static.rt_manager = static.chart
                    static.manager = static.chart
            else:
                log.warning("[_do_full_init] ?좑툘 RealtimeManager ?대옒???놁쓬 ???붾?濡??泥?)
                static.chart = SimpleNamespace(codes=codes, start=lambda *a, **kw: None, alive=False)
                static.realtime_manager = static.chart
                static.rt_manager = static.chart
                static.manager = static.chart
        except Exception:
            log.debug("[_do_full_init] RealtimeManager creation failed (continuing)", exc_info=True)

        # ?щ낵 珥덇린??
        try:
            from .core.symbol_loader import ensure_initial_symbols
            ensure_initial_symbols(static, log)
        except Exception:
            log.debug("[_do_full_init] ensure_initial_symbols failed", exc_info=True)

        # MongoDB 珥덇린??
        try:
            from .core.db_initializer import init_mongodb
            init_mongodb(log)
        except Exception:
            log.debug("[_do_full_init] init_mongodb failed", exc_info=True)

        # DataManager / Pipeline 珥덇린??
        try:
            from .core.db_initializer import init_data_manager, init_pipeline
            init_data_manager(static, log)
            init_pipeline(static, log)
        except Exception:
            log.debug("[_do_full_init] init_data_manager/init_pipeline failed", exc_info=True)

        # staging_candles flush
        try:
            from .core.db_initializer import flush_staging_candles_once
            log.info("[_do_full_init] staging_candles 珥덇린 flush ?쒖옉...")
            flushed = flush_staging_candles_once(log)
            if flushed > 0:
                log.info("[_do_full_init] ??staging_candles 珥덇린 flush ?꾨즺: %d嫄?, flushed)
            else:
                log.debug("[_do_full_init] staging_candles 珥덇린 flush: 泥섎━???곗씠???놁쓬 (?먮뒗 DB 誘몄뿰寃?")
        except Exception:
            log.debug("[_do_full_init] flush_staging_candles_once failed", exc_info=True)

        # GapFinder / Gap detection 媛숈? 臾닿굅???묒뾽? ?대??먯꽌 鍮꾨룞湲??ㅻ젅?쒕줈 泥섎━?섎룄濡??ㅺ퀎?섏뼱????
        # runtime_loader 諛?pipeline 珥덇린?붿뿉???대??곸쑝濡?GapFinder瑜??쒖옉?????덉쓬.

        # WebSocket ?먮룞 ?쒖옉 ?ㅼ?以꾨쭅 (T+10珥?
        try:
            schedule_websocket_start(static, delay_seconds=10)
            log.info("[_do_full_init] ??WebSocket ?먮룞 ?쒖옉 ?ㅼ?以??깅줉 (T+10珥?")
        except Exception as e:
            log.warning("[_do_full_init] WebSocket ?먮룞 ?쒖옉 ?ㅼ?以??깅줉 ?ㅽ뙣 (怨꾩냽 吏꾪뻾): %s", e)

        log.info("[_do_full_init] full init finished")
    except Exception:
        log.exception("[_do_full_init] full init raised exception")


# ------------------- init / main -------------------
def init() -> bool:
    """??珥덇린??(寃쎈웾?? GUI 紐⑤뱶?대㈃ 利됱떆 諛섑솚?섍퀬 諛깃렇?쇱슫?쒖뿉???꾩껜 珥덇린???섑뻾)"""
    try:
        log.info("=" * 60)
        log.info("Upbit Trader Initialization...")
        log.info("=" * 60)

        _nogui = ("--nogui" in os.sys.argv) or (os.getenv("NOGUI", "").lower() in ("1", "true", "yes"))

        if _nogui:
            # ??GUI 紐⑤뱶: 湲곗〈 ?숆린 ?숈옉 ?좎? (?쒕쾭/諛곗튂 紐⑤뱶)
            log.info("[init] nogui mode detected ??running full init synchronously")
            _do_full_init(sync_mode=True)
            return True

        # GUI 紐⑤뱶: 鍮좊Ⅴ寃?諛섑솚?섏뿬 UI媛 利됱떆 ?쒖꽦?붾릺?꾨줉 ??
        # 理쒖냼?쒖쓽 濡쒖쭅: static.signal_queue 諛??뚮옯???뺤콉留?誘몃━ ?곸슜
        try:
            # 理쒖냼 ?고???濡쒕뜑 ?몄텧??吏?곗떆?ㅺ퀬, 臾닿굅??濡쒕뱶/珥덇린?붾뒗 諛깃렇?쇱슫?쒖뿉???섑뻾
            # (?ㅻ쭔, ?쇰? 留ㅼ슦 寃쎈웾???꾩닔 援ъ꽦? ?ш린???ㅼ젙)
            if not getattr(static, "signal_queue", None):
                static.signal_queue = Queue()
        except Exception:
            static.signal_queue = Queue()

        # 諛깃렇?쇱슫?쒖뿉???꾩껜 珥덇린???ㅽ뻾
        t = threading.Thread(target=_do_full_init, daemon=True, name="bootstrap_full_init")
        t.start()
        log.info("[init] GUI 紐⑤뱶: 珥덇린???遺遺꾩쓣 諛깃렇?쇱슫?쒖뿉???ㅽ뻾?⑸땲??(UI ?곗꽑).")

        return True
    except Exception:
        log.exception("[init] Initialization failed")
        return False


def main(gui: bool = True) -> None:
    """??硫붿씤 猷⑦봽"""
    log.info("=" * 60)
    log.info("Starting Upbit Trader...")
    log.info("=" * 60)

    # ?ㅼ?以꾨윭 ?쒖옉
    from .core.backfill_manager import start_scheduler
    start_scheduler(static, log)

    # GUI ?쒖옉
    if gui:
        log.info("[main] Starting GUI mode...")
        try:
            auth_mod, _ = try_import_names(("01_core.auth", "app.core.auth", "auth", "src.01_core.auth"))
            if auth_mod:
                gui_main = getattr(auth_mod, "gui_main", None)
                if callable(gui_main):
                    try:
                        gui_main()
                    finally:
                        from .core.cleanup import cleanup_on_exit
                        cleanup_on_exit(static, log)
                else:
                    log.warning("[main] gui_main not callable in auth module")
            else:
                log.warning("[main] auth module not found; cannot start GUI")
        except Exception:
            log.exception("[main] gui_main() raised an exception")


# 醫낅즺 ???뺣━
from .core.cleanup import cleanup_on_exit
atexit.register(lambda: cleanup_on_exit(static, log))
