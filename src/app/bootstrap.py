# -*- coding: utf-8 -*-
"""
Î∂Ä?∏Ïä§?∏Îû© Î™®Îìà (Î™®Îìà??Î≤ÑÏ†Ñ)
- Î™©Ï†Å: ??Ï¥àÍ∏∞???êÎ¶Ñ Í¥ÄÎ¶?
- ?êÏπô: 500~700Ï§??úÌïú Ï§Ä??
- ??ÎßàÏù¥Í∑∏Î†à?¥ÏÖò ?êÎèô ?§Ìñâ Ï∂îÍ? (?ôÏ†Å ?ÑÌè¨??
- Î≥ÄÍ≤? GUI Î™®Îìú????Î¨¥Í±∞??Ï¥àÍ∏∞?îÎäî Î∞±Í∑∏?ºÏö¥???§Î†à?úÎ°ú ?§Ìñâ?òÏó¨ UI ?∞ÏÑ† ?úÏÑ±??Î≥¥Ïû•
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

# ??Î™®Îìà?îÎêú core ?®ÌÇ§ÏßÄ?êÏÑú import
from .core import (
    create_safe_logger,
    ensure_src_root_on_path,
    schedule_websocket_start,
    try_import_names,
)

# src Î£®Ìä∏ Í≤ΩÎ°ú Î≥¥Ïû•
SRC_ROOT = ensure_src_root_on_path()

# ?ÑÏó≠ Î°úÍ±∞
log = create_safe_logger("bootstrap")

# ------------------- ?°Ïùå??Î°úÍ±∞ ?µÏ†ú -------------------
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

# ?ÑÏó≠ Ïª®ÌÖå?¥ÎÑà
static: SimpleNamespace = SimpleNamespace()
RealtimeManager = None
Account = None
SignalManager = None


def _do_full_init(sync_mode: bool = False) -> None:
    """
    ?§Ï†ú Î¨¥Í±∞??Ï¥àÍ∏∞?îÎ? ?òÌñâ?òÎäî ?®Ïàò?ÖÎãà??
    - sync_mode=True Î©??ôÍ∏∞ ?§Ìñâ (nogui ?ÅÌô©)
    - sync_mode=False Î©?Î∞±Í∑∏?ºÏö¥???∞Î™¨) ?§Î†à?úÏóê???§Ìñâ?©Îãà??
    """
    try:
        log.info("[_do_full_init] full init started (sync_mode=%s)", sync_mode)

        # 1. ?∞Ì???Î™®Îìà Î°úÎìú
        from .core.runtime_loader import load_runtime_modules
        load_runtime_modules(static, log)

        # 2. DB Í≤ÄÏ¶?Î∞?ÎßàÏù¥Í∑∏Î†à?¥ÏÖò (?ôÏ†Å?ºÎ°ú Î°úÎìú/?§Ìñâ)
        try:
            from .core.db_initializer import validate_db_connections
            validate_db_connections(static, log)
        except Exception:
            log.debug("[_do_full_init] validate_db_connections failed or skipped", exc_info=True)

        try:
            log.info("[init] ?îÑ ÎßàÏù¥Í∑∏Î†à?¥ÏÖò Ï≤¥ÌÅ¨ ?úÏûë...")

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
                                log.debug("[_do_full_init] TimescaleDB Ïª§ÎÑ•???ùÏÑ± ?ÑÎ£å (?ôÏ†Å Î°úÎìú)")
                            else:
                                log.warning("[_do_full_init] ?†Ô∏è get_timescale_connector ?®ÏàòÎ•?Ï∞æÏùÑ ???ÜÏùå")
                    else:
                        log.warning("[_do_full_init] ?†Ô∏è timescale_db.py ?åÏùº??Ï∞æÏùÑ ???ÜÏùå")
                except Exception as exc:
                    log.warning("[_do_full_init] ?†Ô∏è TimescaleDB Ïª§ÎÑ•???ùÏÑ± ?§Ìå®: %s", exc)
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
                                        log.info("[init] ??ÎßàÏù¥Í∑∏Î†à?¥ÏÖò ?ÑÎ£å (staging_candles.processed)")
                                    else:
                                        log.warning("[init] ?†Ô∏è ÎßàÏù¥Í∑∏Î†à?¥ÏÖò ?§Ìå® (Í≥ÑÏÜç ÏßÑÌñâ)")
                                except Exception as exc:
                                    log.warning("[init] ?†Ô∏è migrate_sync raised: %s", exc, exc_info=True)
                            else:
                                log.warning("[init] ?†Ô∏è migrate_sync ?®ÏàòÎ•?Ï∞æÏùÑ ???ÜÏùå")
                    else:
                        log.debug("[_do_full_init] ÎßàÏù¥Í∑∏Î†à?¥ÏÖò ?§ÌÅ¨Î¶ΩÌä∏ ?ÜÏùå (?§ÌÇµ)")
                except Exception as exc:
                    log.error("[init] ??ÎßàÏù¥Í∑∏Î†à?¥ÏÖò ?§Ìñâ ?§Ìå®: %s", exc)

        except Exception as exc:
            log.error("[init] ??ÎßàÏù¥Í∑∏Î†à?¥ÏÖò Ï≤¥ÌÅ¨ ?§Ìå®: %s", exc)

        # Windows asyncio policy / multiprocessing (?¥Î? ?§Ï†ï?òÏñ¥ ?àÏùÑ ???àÏùå)
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

        # RealtimeManager ?ùÏÑ± (Í∞Ä?•ÌïòÎ©?
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
                        log.warning("[_do_full_init] aiopyupbit ticker fetch timed out/failed ??Îπ??¨Î≥ºÎ°?ÏßÑÌñâ")
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
                    log.info("[_do_full_init] ??RealtimeManager ?±Î°ù ?ÑÎ£å (%dÍ∞?Ï¢ÖÎ™©)", len(codes))
                except Exception as exc:
                    log.error("[_do_full_init] ??RealtimeManager ?ùÏÑ± ?§Ìå®: %s", exc, exc_info=True)
                    static.chart = SimpleNamespace(codes=codes, start=lambda *a, **kw: None, alive=False)
                    static.realtime_manager = static.chart
                    static.rt_manager = static.chart
                    static.manager = static.chart
            else:
                log.warning("[_do_full_init] ?†Ô∏è RealtimeManager ?¥Îûò???ÜÏùå ???îÎ?Î°??ÄÏ≤?)
                static.chart = SimpleNamespace(codes=codes, start=lambda *a, **kw: None, alive=False)
                static.realtime_manager = static.chart
                static.rt_manager = static.chart
                static.manager = static.chart
        except Exception:
            log.debug("[_do_full_init] RealtimeManager creation failed (continuing)", exc_info=True)

        # ?¨Î≥º Ï¥àÍ∏∞??
        try:
            from .core.symbol_loader import ensure_initial_symbols
            ensure_initial_symbols(static, log)
        except Exception:
            log.debug("[_do_full_init] ensure_initial_symbols failed", exc_info=True)

        # MongoDB Ï¥àÍ∏∞??
        try:
            from .core.db_initializer import init_mongodb
            init_mongodb(log)
        except Exception:
            log.debug("[_do_full_init] init_mongodb failed", exc_info=True)

        # DataManager / Pipeline Ï¥àÍ∏∞??
        try:
            from .core.db_initializer import init_data_manager, init_pipeline
            init_data_manager(static, log)
            init_pipeline(static, log)
        except Exception:
            log.debug("[_do_full_init] init_data_manager/init_pipeline failed", exc_info=True)

        # staging_candles flush
        try:
            from .core.db_initializer import flush_staging_candles_once
            log.info("[_do_full_init] staging_candles Ï¥àÍ∏∞ flush ?úÏûë...")
            flushed = flush_staging_candles_once(log)
            if flushed > 0:
                log.info("[_do_full_init] ??staging_candles Ï¥àÍ∏∞ flush ?ÑÎ£å: %dÍ±?, flushed)
            else:
                log.debug("[_do_full_init] staging_candles Ï¥àÍ∏∞ flush: Ï≤òÎ¶¨???∞Ïù¥???ÜÏùå (?êÎäî DB ÎØ∏Ïó∞Í≤?")
        except Exception:
            log.debug("[_do_full_init] flush_staging_candles_once failed", exc_info=True)

        # GapFinder / Gap detection Í∞ôÏ? Î¨¥Í±∞???ëÏóÖ?Ä ?¥Î??êÏÑú ÎπÑÎèôÍ∏??§Î†à?úÎ°ú Ï≤òÎ¶¨?òÎèÑÎ°??§Í≥Ñ?òÏñ¥????
        # runtime_loader Î∞?pipeline Ï¥àÍ∏∞?îÏóê???¥Î??ÅÏúºÎ°?GapFinderÎ•??úÏûë?????àÏùå.

        # WebSocket ?êÎèô ?úÏûë ?§Ï?Ï§ÑÎßÅ (T+10Ï¥?
        try:
            schedule_websocket_start(static, delay_seconds=10)
            log.info("[_do_full_init] ??WebSocket ?êÎèô ?úÏûë ?§Ï?Ï§??±Î°ù (T+10Ï¥?")
        except Exception as e:
            log.warning("[_do_full_init] WebSocket ?êÎèô ?úÏûë ?§Ï?Ï§??±Î°ù ?§Ìå® (Í≥ÑÏÜç ÏßÑÌñâ): %s", e)

        log.info("[_do_full_init] full init finished")
    except Exception:
        log.exception("[_do_full_init] full init raised exception")


# ------------------- init / main -------------------
def init() -> bool:
    """??Ï¥àÍ∏∞??(Í≤ΩÎüâ?? GUI Î™®Îìú?¥Î©¥ Ï¶âÏãú Î∞òÌôò?òÍ≥† Î∞±Í∑∏?ºÏö¥?úÏóê???ÑÏ≤¥ Ï¥àÍ∏∞???òÌñâ)"""
    try:
        log.info("=" * 60)
        log.info("Upbit Trader Initialization...")
        log.info("=" * 60)

        _nogui = ("--nogui" in os.sys.argv) or (os.getenv("NOGUI", "").lower() in ("1", "true", "yes"))

        if _nogui:
            # ??GUI Î™®Îìú: Í∏∞Ï°¥ ?ôÍ∏∞ ?ôÏûë ?†Ï? (?úÎ≤Ñ/Î∞∞Ïπò Î™®Îìú)
            log.info("[init] nogui mode detected ??running full init synchronously")
            _do_full_init(sync_mode=True)
            return True

        # GUI Î™®Îìú: Îπ†Î•¥Í≤?Î∞òÌôò?òÏó¨ UIÍ∞Ä Ï¶âÏãú ?úÏÑ±?îÎêò?ÑÎ°ù ??
        # ÏµúÏÜå?úÏùò Î°úÏßÅ: static.signal_queue Î∞??åÎû´???ïÏ±ÖÎß?ÎØ∏Î¶¨ ?ÅÏö©
        try:
            # ÏµúÏÜå ?∞Ì???Î°úÎçî ?∏Ï∂ú??ÏßÄ?∞Ïãú?§Í≥†, Î¨¥Í±∞??Î°úÎìú/Ï¥àÍ∏∞?îÎäî Î∞±Í∑∏?ºÏö¥?úÏóê???òÌñâ
            # (?§Îßå, ?ºÎ? Îß§Ïö∞ Í≤ΩÎüâ???ÑÏàò Íµ¨ÏÑ±?Ä ?¨Í∏∞???§Ï†ï)
            if not getattr(static, "signal_queue", None):
                static.signal_queue = Queue()
        except Exception:
            static.signal_queue = Queue()

        # Î∞±Í∑∏?ºÏö¥?úÏóê???ÑÏ≤¥ Ï¥àÍ∏∞???§Ìñâ
        t = threading.Thread(target=_do_full_init, daemon=True, name="bootstrap_full_init")
        t.start()
        log.info("[init] GUI Î™®Îìú: Ï¥àÍ∏∞???ÄÎ∂ÄÎ∂ÑÏùÑ Î∞±Í∑∏?ºÏö¥?úÏóê???§Ìñâ?©Îãà??(UI ?∞ÏÑ†).")

        return True
    except Exception:
        log.exception("[init] Initialization failed")
        return False


def main(gui: bool = True) -> None:
    """??Î©îÏù∏ Î£®ÌîÑ"""
    log.info("=" * 60)
    log.info("Starting Upbit Trader...")
    log.info("=" * 60)

    # ?§Ï?Ï§ÑÎü¨ ?úÏûë
    from .core.backfill_manager import start_scheduler
    start_scheduler(static, log)

    # GUI ?úÏûë
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


# Ï¢ÖÎ£å ???ïÎ¶¨
from .core.cleanup import cleanup_on_exit
atexit.register(lambda: cleanup_on_exit(static, log))
