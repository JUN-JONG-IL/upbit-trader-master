# -*- coding: utf-8 -*-
"""
부트스트랩 모듈 (모듈화 버전)
- 목적: 앱 초기화 흐름 관리
- 원칙: 500~700줄 제한 준수
- ✅ 마이그레이션 자동 실행 추가 (동적 임포트)
- 변경: GUI 모드일 때 무거운 초기화는 백그라운드 스레드로 실행하여 UI 우선 활성화 보장
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

# ✅ 모듈화된 core 패키지에서 import
from .core import (
    create_safe_logger,
    ensure_src_root_on_path,
    schedule_websocket_start,
    try_import_names,
)

# src 루트 경로 보장
SRC_ROOT = ensure_src_root_on_path()

# 전역 로거
log = create_safe_logger("bootstrap")

# ------------------- 잡음성 로거 억제 -------------------
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

# 전역 컨테이너
static: SimpleNamespace = SimpleNamespace()
RealtimeManager = None
Account = None
SignalManager = None


def _do_full_init(sync_mode: bool = False) -> None:
    """
    실제 무거운 초기화를 수행하는 함수입니다.
    - sync_mode=True 면 동기 실행 (nogui 상황)
    - sync_mode=False 면 백그라운드(데몬) 스레드에서 실행됩니다.
    """
    try:
        log.info("[_do_full_init] full init started (sync_mode=%s)", sync_mode)

        # 1. 런타임 모듈 로드
        from .core.runtime_loader import load_runtime_modules
        load_runtime_modules(static, log)

        # 2. DB 검증 및 마이그레이션 (동적으로 로드/실행)
        try:
            from .core.db_initializer import validate_db_connections
            validate_db_connections(static, log)
        except Exception:
            log.debug("[_do_full_init] validate_db_connections failed or skipped", exc_info=True)

        try:
            log.info("[init] 🔄 마이그레이션 체크 시작...")

            ts_connector = getattr(static, "timescale_connector", None)
            if ts_connector is None:
                try:
                    _ts_db_path = os.path.join(SRC_ROOT, "02_data", "timescale", "timescale_db.py")
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
                                log.debug("[_do_full_init] TimescaleDB 커넥터 생성 완료 (동적 로드)")
                            else:
                                log.warning("[_do_full_init] ⚠️ get_timescale_connector 함수를 찾을 수 없음")
                    else:
                        log.warning("[_do_full_init] ⚠️ timescale_db.py 파일을 찾을 수 없음")
                except Exception as exc:
                    log.warning("[_do_full_init] ⚠️ TimescaleDB 커넥터 생성 실패: %s", exc)
            if ts_connector is not None:
                try:
                    _migration_path = os.path.join(
                        SRC_ROOT, "02_data", "timescale", "migrations",
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
                                        log.info("[init] ✅ 마이그레이션 완료 (staging_candles.processed)")
                                    else:
                                        log.warning("[init] ⚠️ 마이그레이션 실패 (계속 진행)")
                                except Exception as exc:
                                    log.warning("[init] ⚠️ migrate_sync raised: %s", exc, exc_info=True)
                            else:
                                log.warning("[init] ⚠️ migrate_sync 함수를 찾을 수 없음")
                    else:
                        log.debug("[_do_full_init] 마이그레이션 스크립트 없음 (스킵)")
                except Exception as exc:
                    log.error("[init] ❌ 마이그레이션 실행 실패: %s", exc)

        except Exception as exc:
            log.error("[init] ❌ 마이그레이션 체크 실패: %s", exc)

        # Windows asyncio policy / multiprocessing (이미 설정되어 있을 수 있음)
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

        # RealtimeManager 생성 (가능하면)
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
                        log.warning("[_do_full_init] aiopyupbit ticker fetch timed out/failed — 빈 심볼로 진행")
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
                    log.info("[_do_full_init] ✅ RealtimeManager 등록 완료 (%d개 종목)", len(codes))
                except Exception as exc:
                    log.error("[_do_full_init] ❌ RealtimeManager 생성 실패: %s", exc, exc_info=True)
                    static.chart = SimpleNamespace(codes=codes, start=lambda *a, **kw: None, alive=False)
                    static.realtime_manager = static.chart
                    static.rt_manager = static.chart
                    static.manager = static.chart
            else:
                log.warning("[_do_full_init] ⚠️ RealtimeManager 클래스 없음 — 더미로 대체")
                static.chart = SimpleNamespace(codes=codes, start=lambda *a, **kw: None, alive=False)
                static.realtime_manager = static.chart
                static.rt_manager = static.chart
                static.manager = static.chart
        except Exception:
            log.debug("[_do_full_init] RealtimeManager creation failed (continuing)", exc_info=True)

        # 심볼 초기화
        try:
            from .core.symbol_loader import ensure_initial_symbols
            ensure_initial_symbols(static, log)
        except Exception:
            log.debug("[_do_full_init] ensure_initial_symbols failed", exc_info=True)

        # MongoDB 초기화
        try:
            from .core.db_initializer import init_mongodb
            init_mongodb(log)
        except Exception:
            log.debug("[_do_full_init] init_mongodb failed", exc_info=True)

        # DataManager / Pipeline 초기화
        try:
            from .core.db_initializer import init_data_manager, init_pipeline
            init_data_manager(static, log)
            init_pipeline(static, log)
        except Exception:
            log.debug("[_do_full_init] init_data_manager/init_pipeline failed", exc_info=True)

        # staging_candles flush
        try:
            from .core.db_initializer import flush_staging_candles_once
            log.info("[_do_full_init] staging_candles 초기 flush 시작...")
            flushed = flush_staging_candles_once(log)
            if flushed > 0:
                log.info("[_do_full_init] ✅ staging_candles 초기 flush 완료: %d건", flushed)
            else:
                log.debug("[_do_full_init] staging_candles 초기 flush: 처리할 데이터 없음 (또는 DB 미연결)")
        except Exception:
            log.debug("[_do_full_init] flush_staging_candles_once failed", exc_info=True)

        # GapFinder / Gap detection 같은 무거운 작업은 내부에서 비동기/스레드로 처리하도록 설계되어야 함.
        # runtime_loader 및 pipeline 초기화에서 내부적으로 GapFinder를 시작할 수 있음.

        # WebSocket 자동 시작 스케줄링 (T+10초)
        try:
            schedule_websocket_start(static, delay_seconds=10)
            log.info("[_do_full_init] ✅ WebSocket 자동 시작 스케줄 등록 (T+10초)")
        except Exception as e:
            log.warning("[_do_full_init] WebSocket 자동 시작 스케줄 등록 실패 (계속 진행): %s", e)

        log.info("[_do_full_init] full init finished")
    except Exception:
        log.exception("[_do_full_init] full init raised exception")


# ------------------- init / main -------------------
def init() -> bool:
    """앱 초기화 (경량화: GUI 모드이면 즉시 반환하고 백그라운드에서 전체 초기화 수행)"""
    try:
        log.info("=" * 60)
        log.info("Upbit Trader Initialization...")
        log.info("=" * 60)

        _nogui = ("--nogui" in os.sys.argv) or (os.getenv("NOGUI", "").lower() in ("1", "true", "yes"))

        if _nogui:
            # 노 GUI 모드: 기존 동기 동작 유지 (서버/배치 모드)
            log.info("[init] nogui mode detected — running full init synchronously")
            _do_full_init(sync_mode=True)
            return True

        # GUI 모드: 빠르게 반환하여 UI가 즉시 활성화되도록 함
        # 최소한의 로직: static.signal_queue 및 플랫폼 정책만 미리 적용
        try:
            # 최소 런타임 로더 호출을 지연시키고, 무거운 로드/초기화는 백그라운드에서 수행
            # (다만, 일부 매우 경량의 필수 구성은 여기서 설정)
            if not getattr(static, "signal_queue", None):
                static.signal_queue = Queue()
        except Exception:
            static.signal_queue = Queue()

        # 백그라운드에서 전체 초기화 실행
        t = threading.Thread(target=_do_full_init, daemon=True, name="bootstrap_full_init")
        t.start()
        log.info("[init] GUI 모드: 초기화 대부분을 백그라운드에서 실행합니다 (UI 우선).")

        return True
    except Exception:
        log.exception("[init] Initialization failed")
        return False


def main(gui: bool = True) -> None:
    """앱 메인 루프"""
    log.info("=" * 60)
    log.info("Starting Upbit Trader...")
    log.info("=" * 60)

    # 스케줄러 시작
    from .core.backfill_manager import start_scheduler
    start_scheduler(static, log)

    # GUI 시작
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


# 종료 시 정리
from .core.cleanup import cleanup_on_exit
atexit.register(lambda: cleanup_on_exit(static, log))