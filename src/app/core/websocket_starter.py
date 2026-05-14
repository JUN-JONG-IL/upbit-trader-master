# -*- coding: utf-8 -*-
"""
WebSocket + REST API 자동 시작 헬퍼 (독립 스레드 완전 격리 버전)

[Changes]
- 2026-04-20: REST API 1분 캔들 수집기 추가 (Ticker 무시)
"""
from __future__ import annotations

import asyncio as aio
import os
import threading
import time
from types import SimpleNamespace

from .logger import SafeLogger, create_safe_logger
from .module_loader import try_import_names

log = create_safe_logger("websocket_starter")

try:
    import aiopyupbit
except ImportError:
    aiopyupbit = None


def _load_symbol_limits() -> dict:
    """config.yaml에서 심볼 수 제한 설정 로드.
    실패 시 기본값 반환."""
    from pathlib import Path
    _defaults = {
        "max_subscribe": 300,
        "mongo_fallback_limit": 300,
        "rest_collector_limit": 100,
        "ui_display_limit": 10_000,
        "db_fallback_limit": 300,
    }
    try:
        import yaml  # type: ignore
        # src/app/core/ → parents[2] = src/ → src/01_core/config/config.yaml
        search_paths = [
            Path(__file__).parents[2] / "01_core" / "config" / "config.yaml",
            Path(__file__).parents[3] / "config.yaml",
        ]
        for p in search_paths:
            if p.exists():
                with open(p, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                sym = data.get("symbols", {})
                if isinstance(sym, dict):
                    return {
                        "max_subscribe": int(sym.get("max_subscribe", _defaults["max_subscribe"])),
                        "mongo_fallback_limit": int(sym.get("mongo_fallback_limit", _defaults["mongo_fallback_limit"])),
                        "rest_collector_limit": int(sym.get("rest_collector_limit", _defaults["rest_collector_limit"])),
                        "ui_display_limit": int(sym.get("ui_display_limit", _defaults["ui_display_limit"])),
                        "db_fallback_limit": int(sym.get("db_fallback_limit", _defaults["db_fallback_limit"])),
                    }
    except Exception:
        pass
    return _defaults


def _normalize_timeframes(settings_doc: dict) -> list[str]:
    """MongoDB 수집 설정에서 활성 타임프레임 목록을 읽습니다."""
    raw = (
        settings_doc.get("collection_settings", {}).get("timeframes")
        or settings_doc.get("collection_settings", {}).get("collected_timeframes")
        or ["1m"]
    )
    allowed = {"1m", "3m", "5m", "10m", "15m", "30m", "1h", "4h", "1d"}
    result: list[str] = []
    for tf in raw if isinstance(raw, list) else [raw]:
        tf = str(tf).strip()
        if tf in allowed and tf not in result:
            result.append(tf)
    return result or ["1m"]


async def start_websocket_auto(static: SimpleNamespace):
    """WebSocket + REST API 자동 연결 및 구독"""
    try:
        log.info("[WebSocket] T+10초: WebSocket + REST API 자동 시작")
        
        # 1. MongoDB 설정 로드
        try:
            from pymongo import MongoClient
            mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/upbit_trader")
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
            db = client.upbit_trader
            settings_doc = db.ui_settings.find_one({"user_id": "default"})
            
            if not settings_doc:
                settings_doc = {
                    "smart_scanner": {"all_symbols": True},
                    "collection_settings": {"timeframes": ["1m"]}
                }
        except Exception as e:
            log.warning("[WebSocket] MongoDB 연결 실패 — 기본값 사용: %s", e)
            settings_doc = {
                "smart_scanner": {"all_symbols": True},
                "collection_settings": {"timeframes": ["1m"]}
            }
        
        # 2. 종목 목록 결정
        all_symbols = settings_doc.get("smart_scanner", {}).get("all_symbols", True)
        
        # 심볼 수 제한 설정 로드
        _sym_limits = _load_symbol_limits()
        _max_subscribe = _sym_limits["max_subscribe"]
        _mongo_limit = _sym_limits["mongo_fallback_limit"]
        
        if all_symbols:
            try:
                if aiopyupbit is not None:
                    codes = await aiopyupbit.get_tickers(fiat="KRW", contain_name=True)
                    # max_subscribe == 0 이면 전체 사용, 그 외 슬라이싱
                    _codes_sliced = codes if _max_subscribe == 0 else codes[:_max_subscribe]
                    priority_symbols = [
                        item.get("market") if isinstance(item, dict) else str(item)
                        for item in _codes_sliced
                        if item
                    ]
                    log.info("[WebSocket] Upbit API에서 %d개 심볼 로드", len(priority_symbols))
                else:
                    raise ImportError("aiopyupbit 없음")
            except Exception:
                priority_symbols = [
                    doc.get("market")
                    for doc in db.metadata.find({}, {"market": 1}).limit(_mongo_limit)
                    if doc.get("market")
                ]
                log.info("[WebSocket] MongoDB metadata에서 %d개 심볼 로드", len(priority_symbols))
        else:
            priority_symbols = ["KRW-BTC", "KRW-ETH"]
        
        if not priority_symbols:
            log.error("[WebSocket] 종목 목록이 비어있음")
            return
        
        timeframes = _normalize_timeframes(settings_doc)

        # 3. WebSocketManager 생성
        try:
            ws_manager_mod, _ = try_import_names((
                "data_01.collectors.websocket_manager",
                "src.data_01.collectors.websocket_manager",
            ))
            
            if not ws_manager_mod:
                log.error("[WebSocket] websocket_manager 모듈 없음")
                return
            
            WebSocketManager = getattr(ws_manager_mod, "WebSocketManager", None)
            if not WebSocketManager:
                log.error("[WebSocket] WebSocketManager 클래스 없음")
                return
            
            redis_client = getattr(static, "redis_client", None)
            mongo_db = getattr(static, "mongo_db", None)
            
            ws_manager = WebSocketManager(redis_client=redis_client, mongo_db=mongo_db)
            if hasattr(ws_manager, "set_collected_timeframes"):
                ws_manager.set_collected_timeframes(timeframes)

            # ✅ WebSocket ticker/trade를 Pipeline에도 연결 (실시간 처리량 개선)
            try:
                processor = getattr(static, "processor", None)
                if processor is not None:
                    if hasattr(processor, "enqueue"):
                        ws_manager.set_pipeline_callback(processor.enqueue)
                        log.info("[WebSocket] ✅ Pipeline 콜백 연결 (WebSocket → enqueue)")
                    elif hasattr(processor, "process_candle_sync"):
                        ws_manager.set_pipeline_callback(processor.process_candle_sync)
                        log.info("[WebSocket] ✅ Pipeline 콜백 연결 (WebSocket → 동기)")
                    elif hasattr(processor, "process_candle"):
                        ws_manager.set_pipeline_callback(processor.process_candle)
                        log.info("[WebSocket] ✅ Pipeline 콜백 연결 (WebSocket → 비동기)")
            except Exception as exc:
                log.warning("[WebSocket] Pipeline 콜백 연결 실패(계속 진행): %s", exc)
            
            # ✅ 수정: WebSocket 전체 수명주기를 독립 스레드에서 실행
            def _run_websocket_forever():
                """독립 이벤트 루프에서 WebSocket 전체 수명주기 실행"""
                try:
                    loop = aio.new_event_loop()
                    aio.set_event_loop(loop)
                    
                    log.info("[WebSocket] ✅ WebSocket 스레드 시작 (독립 이벤트 루프)")
                    
                    # ✅ 연결 + 구독 + 수신을 모두 같은 루프에서 실행
                    async def _websocket_lifecycle():
                        await ws_manager.connect()
                        await ws_manager.subscribe(priority_symbols)
                        await ws_manager.start_listening()
                    
                    loop.run_until_complete(_websocket_lifecycle())
                    
                except Exception as exc:
                    log.error("[WebSocket] ❌ WebSocket 스레드 종료: %s", exc, exc_info=True)
                finally:
                    loop.close()
            
            listening_thread = threading.Thread(
                target=_run_websocket_forever,
                daemon=True,
                name="websocket_listening"
            )
            listening_thread.start()
            
            static.websocket_manager = ws_manager
            static.websocket_listening_thread = listening_thread
            
            log.info("[WebSocket] ✅ WebSocket 시작 완료 (%d개 심볼)", len(priority_symbols))
            
        except Exception as e:
            log.exception("[WebSocket] WebSocketManager 생성 실패: %s", e)
        
        # ========================================
        # ✅ 4. REST API 캔들 수집기 시작
        # ========================================
        try:
            rest_collector_mod, _ = try_import_names((
                "data_01.collectors.rest_candle_collector",
                "src.data_01.collectors.rest_candle_collector",
            ))
            
            if not rest_collector_mod:
                log.warning("[RestCollector] rest_candle_collector 모듈 없음 — 생성하세요")
                return
            
            RestCandleCollector = getattr(rest_collector_mod, "RestCandleCollector", None)
            if not RestCandleCollector:
                log.error("[RestCollector] RestCandleCollector 클래스 없음")
                return
            
            _rest_limit = _sym_limits.get("rest_collector_limit", 100)
            # rest_collector_limit == 0 이면 전체 사용, 그 외 슬라이싱
            _symbols_for_rest = priority_symbols if _rest_limit == 0 else priority_symbols[:_rest_limit]
            _rest_interval_sec = int(os.getenv("REST_COLLECTOR_INTERVAL_SECONDS", "15"))
            rest_collector = RestCandleCollector(
                symbols=_symbols_for_rest,
                interval_seconds=_rest_interval_sec,
                timeframes=timeframes,
            )
            
            # Pipeline 콜백 연결
            try:
                processor = getattr(static, "processor", None)
                if processor is not None:
                    if hasattr(processor, "enqueue"):
                        rest_collector.set_pipeline_callback(processor.enqueue)
                        log.info("[RestCollector] ✅ Pipeline 콜백 연결 (enqueue)")
                    elif hasattr(processor, "process_candle_sync"):
                        rest_collector.set_pipeline_callback(processor.process_candle_sync)
                        log.info("[RestCollector] ✅ Pipeline 콜백 연결 (동기)")
                    elif hasattr(processor, "process_candle"):
                        rest_collector.set_pipeline_callback(processor.process_candle)
                        log.info("[RestCollector] ✅ Pipeline 콜백 연결 (비동기)")
            except Exception as exc:
                log.error("[RestCollector] Pipeline 콜백 연결 실패: %s", exc)
            
            # ✅ REST 수집기 독립 스레드에서 실행
            def _run_rest_collector_forever():
                """독립 이벤트 루프에서 REST 수집기 실행"""
                try:
                    loop = aio.new_event_loop()
                    aio.set_event_loop(loop)
                    
                    log.info("[RestCollector] ✅ REST 수집 스레드 시작 (독립 이벤트 루프)")
                    loop.run_until_complete(rest_collector.start())
                    
                    # 무한 대기 (백그라운드 태스크 유지)
                    loop.run_forever()
                    
                except Exception as exc:
                    log.error("[RestCollector] ❌ REST 수집 스레드 종료: %s", exc, exc_info=True)
                finally:
                    loop.close()
            
            rest_thread = threading.Thread(
                target=_run_rest_collector_forever,
                daemon=True,
                name="rest_candle_collector"
            )
            rest_thread.start()
            
            static.rest_collector = rest_collector
            static.rest_collector_thread = rest_thread
            
            log.info(
                "[RestCollector] ✅ REST API 캔들 수집 시작 (%d초 주기, %d개 심볼, TF=%s)",
                _rest_interval_sec,
                len(_symbols_for_rest),
                ",".join(timeframes),
            )
            
        except Exception as e:
            log.exception("[RestCollector] REST 수집기 시작 실패: %s", e)
        
    except Exception as e:
        log.exception("[WebSocket] 자동 시작 실패: %s", e)


def schedule_websocket_start(static: SimpleNamespace, delay_seconds: int = 10):
    """T+delay_seconds 후 WebSocket + REST API 자동 시작"""
    async def _delayed_start():
        await aio.sleep(delay_seconds)
        try:
            log.info("[WebSocket] T+%d초: WebSocket + REST API 자동 시작 시도", delay_seconds)
            await start_websocket_auto(static)
        except Exception as e:
            log.error("[WebSocket] 자동 시작 실패: %s", e)
    
    try:
        loop = aio.get_running_loop()
        loop.create_task(_delayed_start())
    except RuntimeError:
        log.info("[WebSocket] 이벤트 루프 미실행 — 폴백 스레드로 실행")
        
        def _delayed_start_sync():
            time.sleep(delay_seconds)
            try:
                log.info("[WebSocket] T+%d초: WebSocket + REST API 자동 시작 시도 (폴백)", delay_seconds)
                aio.run(start_websocket_auto(static))
            except Exception as e:
                log.error("[WebSocket] 자동 시작 실패: %s", e)
        
        t = threading.Thread(target=_delayed_start_sync, daemon=True, name="websocket_auto_start")
        t.start()
