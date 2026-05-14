#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket Manager - Upbit 실시간 데이터 수신 (최종 안정 버전)

[Changes]
- 2026-04-20: ✅ qasync 데드락 해결 (asyncio.sleep 직접 사용)
- 2026-04-20: ✅ 스냅샷 포함 (isOnlyRealtime=False) → 즉시 데이터 수신
- 2026-04-20: ✅ 터미널 로그 정리 (DEBUG/INFO → 레벨 조정)
- 2026-04-20: ✅ time 필드 추가 (Pipeline 검증 통과)
- 2026-04-20: ✅ timeframe 필드 추가 (Pipeline 에러 해결)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import websockets
    _HAS_WEBSOCKETS = True
except ImportError:
    _HAS_WEBSOCKETS = False

try:
    import redis.asyncio as aioredis
    _HAS_AIOREDIS = True
except ImportError:
    _HAS_AIOREDIS = False


class WebSocketManager:
    """Upbit WebSocket 연결 및 구독 관리."""

    UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"
    _TICKER_CACHE_TTL = 300
    _RECONNECT_DELAY = 5
    _MAX_RECONNECT_ATTEMPTS = 10
    _RECV_TIMEOUT = 120.0

    def __init__(self, redis_client=None, mongo_db=None) -> None:
        self._redis = redis_client
        self._mongo = mongo_db
        self._ws = None
        self._running: bool = False
        self._subscribed_symbols: List[str] = []
        self._collected_timeframes: List[str] = []
        self._pipeline_callback: Optional[Callable] = None
        
        self._stats = {
            "connected": False,
            "message_count": 0,
            "error_count": 0,
            "pipeline_sent": 0,
            "last_message_time": None,
            "avg_latency_ms": 0.0,
            "reconnect_count": 0,
        }
        self._latencies: List[float] = []
        self._last_symbol: str = ""

    def set_pipeline_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self._pipeline_callback = callback
        logger.info("[WebSocketManager] ✅ Pipeline 콜백 등록 완료")

    def set_collected_timeframes(self, timeframes: List[str]) -> None:
        allowed = {"1m", "3m", "5m", "10m", "15m", "30m", "1h", "4h", "1d"}
        self._collected_timeframes = [str(tf) for tf in timeframes if str(tf) in allowed] or ["1m"]

    async def connect(self) -> None:
        if not _HAS_WEBSOCKETS:
            logger.error("[WebSocketManager] websockets 패키지 미설치")
            return

        try:
            logger.info("[WebSocketManager] WebSocket 연결 시작: %s", self.UPBIT_WS_URL)
            self._ws = await websockets.connect(
                self.UPBIT_WS_URL,
                ping_interval=20,
                ping_timeout=10,
            )
            self._stats["connected"] = True
            logger.info("[WebSocketManager] ✅ WebSocket 연결 성공")
        except Exception as exc:
            self._stats["connected"] = False
            self._stats["error_count"] += 1
            logger.error("[WebSocketManager] ❌ WebSocket 연결 실패: %s", exc)
            raise

    async def stop(self) -> None:
        self._running = False
        self._stats["connected"] = False
        if self._ws is not None:
            try:
                await self._ws.close()
                logger.info("[WebSocketManager] WebSocket 연결 종료")
            except Exception as exc:
                logger.debug("[WebSocketManager] 연결 종료 중 오류: %s", exc)

    async def _reconnect(self) -> bool:
        for attempt in range(1, self._MAX_RECONNECT_ATTEMPTS + 1):
            try:
                logger.warning("[WebSocketManager] 재연결 시도 %d/%d", attempt, self._MAX_RECONNECT_ATTEMPTS)
                await asyncio.sleep(self._RECONNECT_DELAY)
                await self.connect()
                
                if self._subscribed_symbols:
                    await self.subscribe(self._subscribed_symbols)
                
                self._stats["reconnect_count"] += 1
                logger.info("[WebSocketManager] ✅ 재연결 성공")
                return True
            except Exception as exc:
                logger.error("[WebSocketManager] 재연결 실패: %s", exc)
                if attempt >= self._MAX_RECONNECT_ATTEMPTS:
                    return False
        return False

    async def load_collection_settings(self) -> Dict[str, Any]:
        if self._mongo is None:
            return {"collected_timeframes": ["1m"]}

        try:
            doc = self._mongo.ui_settings.find_one({"user_id": "default"})
            if doc and "collection_settings" in doc:
                settings = doc["collection_settings"]
                timeframes = settings.get("timeframes") or settings.get("collected_timeframes", ["1m"])
                self.set_collected_timeframes(timeframes if isinstance(timeframes, list) else ["1m"])
                return settings
            return {"collected_timeframes": ["1m"]}
        except Exception:
            return {"collected_timeframes": ["1m"]}

    async def subscribe(self, symbols: List[str]) -> None:
        if self._ws is None:
            logger.error("[WebSocketManager] WebSocket 미연결")
            return

        self._subscribed_symbols = symbols

        subscribe_message: List[Dict[str, Any]] = [
            {"ticket": str(uuid.uuid4())},
            {
                "type": "ticker",
                "codes": symbols,
                "isOnlyRealtime": False,  # ✅ 스냅샷 포함
            },
            {"type": "trade", "codes": symbols},
        ]

        priority_symbols = symbols[:10]
        if priority_symbols:
            subscribe_message.append({"type": "orderbook", "codes": priority_symbols})

        try:
            await self._ws.send(json.dumps(subscribe_message))
            logger.info("[WebSocketManager] ✅ 구독 완료: %d개 종목 (스냅샷 포함)", len(symbols))
            logger.debug("[WebSocketManager] 구독 메시지: %s", subscribe_message)
        except Exception as exc:
            self._stats["error_count"] += 1
            logger.error("[WebSocketManager] ❌ 구독 실패: %s", exc)

    async def start_listening(self) -> None:
        if self._ws is None:
            logger.error("[WebSocketManager] WebSocket 미연결")
            return

        self._running = True
        logger.info("[WebSocketManager] 실시간 데이터 수신 시작")
        logger.info("[WebSocketManager] ✅ WebSocket 수신 대기 시작 (recv() 루프)")
        
        logger.debug("[WebSocketManager] ⏰ 구독 처리 대기 (0.5초)...")
        await asyncio.sleep(0.5)
        logger.debug("[WebSocketManager] ✅ 구독 처리 대기 완료")

        try:
            message_count_local = 0
            
            while self._running:
                try:
                    logger.debug("[WebSocketManager] 🔄 recv() 호출 대기 ���...")
                    
                    message = await asyncio.wait_for(self._ws.recv(), timeout=self._RECV_TIMEOUT)
                    
                    message_count_local += 1
                    
                    if not self._running:
                        break
                    
                    logger.debug(
                        "[WebSocketManager] ✅ 메시지 수신 #%d (길이: %d bytes)",
                        message_count_local,
                        len(message)
                    )
                    
                    self._stats["message_count"] += 1
                    self._stats["last_message_time"] = datetime.now(timezone.utc)
                    
                    await self._process_message(message)
                    
                    if self._stats["message_count"] % 100 == 0:
                        logger.info(
                            "[WebSocketManager] 수신: %d개 (Pipeline: %d, 평균지연: %.2fms)",
                            self._stats["message_count"],
                            self._stats["pipeline_sent"],
                            self._stats["avg_latency_ms"],
                        )
                        await self._save_stats_to_redis()
                
                except asyncio.TimeoutError:
                    logger.debug("[WebSocketManager] ⏰ recv() 타임아웃 (120초) — 메시지 없음")
                    continue
                
                except websockets.exceptions.ConnectionClosed as exc:
                    logger.warning("[WebSocketManager] ❌ 연결 끊김 — 재연결 시도")
                    self._stats["connected"] = False
                    if self._running:
                        if not await self._reconnect():
                            break
                
                except Exception as exc:
                    self._stats["error_count"] += 1
                    logger.error("[WebSocketManager] ❌ 수신 오류: %s", exc, exc_info=True)
                    await asyncio.sleep(1)
        
        except Exception as exc:
            logger.exception("[WebSocketManager] ❌ start_listening 치명적 예외: %s", exc)
        
        finally:
            logger.info(
                "[WebSocketManager] 🛑 수신 종료 (총 %d개, Pipeline: %d, 에러 %d개)",
                self._stats["message_count"],
                self._stats["pipeline_sent"],
                self._stats["error_count"],
            )

    async def _process_message(self, message: bytes) -> None:
        start_time = time.perf_counter()
        
        try:
            data: Dict[str, Any] = json.loads(message)
            msg_type = data.get("type")

            logger.debug("[WebSocketManager] 파싱: type=%s", msg_type)

            if msg_type == "ticker":
                await self._handle_ticker(data)
            elif msg_type == "trade":
                await self._handle_trade(data)
            elif msg_type == "orderbook":
                await self._handle_orderbook(data)
            
            latency_ms = (time.perf_counter() - start_time) * 1000
            self._latencies.append(latency_ms)
            if len(self._latencies) > 100:
                self._latencies.pop(0)
            self._stats["avg_latency_ms"] = sum(self._latencies) / len(self._latencies)
        
        except json.JSONDecodeError as exc:
            self._stats["error_count"] += 1
            logger.error("[WebSocketManager] JSON 파싱 실패: %s", exc)
        except Exception as exc:
            self._stats["error_count"] += 1
            logger.error("[WebSocketManager] 처리 오류: %s", exc)

    async def _update_ws_recv_stats(self, symbol: str) -> None:
        """Redis에 WebSocket 수신 통계를 기록합니다.

        저장 키:
            ws:stats:{symbol}  — {"recv_count": N, "last_time": ISO, "status": "active"}
            ws:symbols         — 수신 중인 심볼 집합 (Set)
            ws:total_recv      — 누적 수신 건수 (INCR)
            ws:qps:{초}        — 초당 수신 건수 (INCR, EXPIRE 10초)
        """
        if self._redis is None:
            return
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            stats_key = f"ws:stats:{symbol}"

            # 기존 수신 건수 조회
            recv_count = 1
            try:
                raw = (
                    await self._redis.get(stats_key)
                    if _HAS_AIOREDIS and isinstance(self._redis, aioredis.Redis)
                    else self._redis.get(stats_key)
                )
                if raw:
                    prev = json.loads(raw)
                    recv_count = int(prev.get("recv_count", 0)) + 1
            except Exception:
                pass

            # Delta 압축률은 현재 미지원 — 항상 0.0 기록 (향후 확장 시 개선)
            stats_json = json.dumps(
                {"recv_count": recv_count, "last_time": now_iso, "status": "active", "compression_ratio": 0.0},
                ensure_ascii=False,
            )

            # 비동기/동기 모두 지원
            if _HAS_AIOREDIS and isinstance(self._redis, aioredis.Redis):
                await self._redis.set(stats_key, stats_json, ex=60)
                await self._redis.sadd("ws:symbols", symbol)
                await self._redis.incr("ws:total_recv")
                sec_key = f"ws:qps:{int(time.time())}"
                await self._redis.incr(sec_key)
                await self._redis.expire(sec_key, 10)
            else:
                self._redis.set(stats_key, stats_json, ex=60)
                self._redis.sadd("ws:symbols", symbol)
                self._redis.incr("ws:total_recv")
                sec_key = f"ws:qps:{int(time.time())}"
                self._redis.incr(sec_key)
                self._redis.expire(sec_key, 10)
        except Exception as exc:
            logger.debug("[WebSocketManager] ws stats Redis 기록 실패(무시): %s", exc)

    async def _handle_ticker(self, data: Dict[str, Any]) -> None:
        symbol = data.get("code")
        close = data.get("trade_price")
        timestamp = data.get("timestamp")  # 밀리초 단위
        
        if not symbol or close is None:
            return

        self._last_symbol = str(symbol)
        self._stats["last_symbol"] = str(symbol)

        # ✅ timestamp를 datetime으로 변환 (Pipeline 검증 통과)
        if timestamp:
            try:
                # Upbit timestamp는 밀리초 단위 (Unix timestamp * 1000)
                dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
            except Exception as exc:
                logger.debug("[WebSocketManager] timestamp 변환 실패: %s, 현재 시각 사용", exc)
                dt = datetime.now(timezone.utc)
        else:
            dt = datetime.now(timezone.utc)

        if self._pipeline_callback is not None and os.getenv("UPBIT_WS_PIPELINE_TICKS", "false").lower() in ("1", "true", "yes"):
            try:
                pipeline_data = {
                    "symbol": symbol,
                    "close": close,
                    "timestamp": timestamp,
                    "time": dt,  # ✅ datetime 객체 추가 (Pipeline 필수)
                    "timeframe": "1m",  # ✅ 추가: 기본 타임프레임
                    "type": "ticker",
                    "received_at": datetime.now(timezone.utc).isoformat(),
                }
                self._pipeline_callback(pipeline_data)
                self._stats["pipeline_sent"] += 1
            except Exception as exc:
                logger.error("[WebSocketManager] Pipeline 실패: %s", exc)

        # 수신 통계를 Redis에 기록 (WebSocket 탭 UI에서 사용)
        await self._update_ws_recv_stats(str(symbol))

        if self._redis is None:
            return

        cache_key = f"ticker:{symbol}"
        cache_data = json.dumps({
            "symbol": symbol,
            "close": close,
            "timestamp": timestamp,
            "time": dt.isoformat(),  # ✅ ISO 형식 문자열
            "timeframe": "1m",  # ✅ 추가
            "type": "ticker",
            "received_at": datetime.now(timezone.utc).isoformat(),
        })

        try:
            if _HAS_AIOREDIS and isinstance(self._redis, aioredis.Redis):
                await self._redis.setex(cache_key, self._TICKER_CACHE_TTL, cache_data)
                await self._redis.publish("candle:updates", cache_data)
            else:
                self._redis.setex(cache_key, self._TICKER_CACHE_TTL, cache_data)
                self._redis.publish("candle:updates", cache_data)
        except Exception as exc:
            logger.error("[WebSocketManager] Redis 실패: %s", exc)

    async def _handle_trade(self, data: Dict[str, Any]) -> None:
        symbol = data.get("code")
        if not symbol:
            return
        
        if self._pipeline_callback is not None:
            try:
                self._pipeline_callback({
                    "symbol": symbol,
                    "price": data.get("trade_price"),
                    "volume": data.get("trade_volume"),
                    "timestamp": data.get("timestamp"),
                    "type": "trade",
                })
                self._stats["pipeline_sent"] += 1
            except Exception as exc:
                logger.error("[WebSocketManager] Pipeline(trade) 실패: %s", exc)

    async def _handle_orderbook(self, data: Dict[str, Any]) -> None:
        pass

    async def _save_stats_to_redis(self) -> None:
        if self._redis is None:
            return
        
        stats_data = json.dumps({
            "connected": self._stats["connected"],
            "message_count": self._stats["message_count"],
            "pipeline_sent": self._stats["pipeline_sent"],
            "error_count": self._stats["error_count"],
            "avg_latency_ms": round(self._stats["avg_latency_ms"], 2),
        })
        
        try:
            if _HAS_AIOREDIS and isinstance(self._redis, aioredis.Redis):
                await self._redis.setex("websocket:stats", 300, stats_data)
            else:
                self._redis.setex("websocket:stats", 300, stats_data)
        except Exception:
            pass

    def _calculate_message_rate(self) -> float:
        return self._stats["message_count"] / max(60, 1)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "connection_status": "connected" if self._stats["connected"] else "disconnected",
            "subscribed_count": len(self._subscribed_symbols),
            "total_messages": self._stats["message_count"],
            "pipeline_sent": self._stats["pipeline_sent"],
            "total_errors": self._stats["error_count"],
        }

    @property
    def recv_count(self) -> int:
        """총 수신 건수"""
        return self._stats["message_count"]

    @property
    def last_symbol(self) -> str:
        """마지막 수신 심볼"""
        return self._last_symbol

    @property
    def avg_latency_ms(self) -> float:
        """평균 지연시간 (ms)"""
        return self._stats["avg_latency_ms"]

    @property
    def is_connected(self) -> bool:
        """WebSocket 연결 상태"""
        return bool(self._stats["connected"])
