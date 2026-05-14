# -*- coding: utf-8 -*-
"""
OEMS 리스크 모듈 (PoC)

기능 요약:
- 주문 전(Pre-trade) 원자적 리스크 검사 및 금액 예약(reservation)
  - Redis Lua를 사용하여 사용자 잔고(available)에서 주문금액만큼 차감하고 locked에 적재(원자적)
- 예약 해제(release) 및 예약 확정(finalize) 함수 제공
- 멱등성: client_oid(또는 order['client_oid'])를 사용해 동일 주문 중복 처리 방지
- Redis 클라이언트 호환: redis.asyncio 우선, aioredis fallback
- 모든 주석/로그는 한글

중요(제한):
- PoC 수준이며 실제 운영에서는 아래 보완 필요:
  - 가격 결정/슬리피지/수수료 반영 로직
  - DB(원장)와의 트랜잭션 연동으로 최종 체결 시 원장 동기화
  - Vault/Secrets로 민감정보 관리
  - 단위/통합 테스트 보강

사용 예(비동기):
    import asyncio
    from src.trade.oems.risk import check_order, release_reservation, finalize_reservation, init_redis, close_redis

    async def run():
        redis = await init_redis("redis://:dummy@127.0.0.1:58530/0")
        order = {
            "client_oid": "test-oid-1",
            "user_id": "user_123",
            "symbol": "KRW-BTC",
            "side": "buy",
            "order_type": "limit",
            "price": "50000",      # 문자열 허용 (Decimal 파싱)
            "quantity": "0.001",
            "metadata": {}
        }
        res = await check_order(order, redis)
        print(res)
        # 처리 실패 시 예약 해제
        if not res["ok"]:
            await close_redis(redis)
            return
        # 주문 취소 시
        await release_reservation(order["client_oid"], order["user_id"], redis)
        # 주문 체결/전송 확정 시
        # await finalize_reservation(order["client_oid"], order["user_id"], redis)
        await close_redis(redis)

    asyncio.run(run())

환경변수:
- REDIS_URL: Redis 연결 URL (기본: config.yaml REDIS 섹션, fallback: redis://:dummy@127.0.0.1:58530/0)

주의:
- 이 파일은 한 번에 한 파일 작업 원칙에 맞춰 PoC 구현만 제공합니다.
"""

from __future__ import annotations

import asyncio
import logging
import os
import decimal
from decimal import Decimal
from typing import Any, Dict, Optional

import orjson  # type: ignore

logger = logging.getLogger("oems.risk")
logging.getLogger("oems.risk").addHandler(logging.NullHandler())

# Redis 관련 기본값 / 키패턴
REDIS_URL_ENV = "REDIS_URL"


def _get_default_redis_url() -> str:
    """config.yaml 기반 Redis URL 반환 (fallback: 포트 58530, password=dummy)"""
    redis_url = os.getenv(REDIS_URL_ENV)
    if redis_url:
        return redis_url
    try:
        import importlib.util as _ilu
        import pathlib as _pl
        _factory_path = _pl.Path(__file__).resolve().parents[2] / "core" / "database" / "redis_factory.py"
        _spec = _ilu.spec_from_file_location("_redis_factory_risk", str(_factory_path))
        _factory_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_factory_mod)  # type: ignore[union-attr]
        return _factory_mod.get_redis_url()
    except Exception:
        return "redis://:dummy@127.0.0.1:58530/0"
USER_BALANCE_KEY = "user:balance:{user_id}"        # hash: available, locked
RESERVATION_KEY = "order:reservation:{client_oid}"  # string: JSON {user_id, amount, timestamp}
RESERVATION_TTL = 60 * 60  # 1시간 기본 TTL

# Lua 스크립트: 원자적 검사 및 예약 (available >= amount 이면 available -= amount; locked += amount; return 1)
_LUA_CHECK_AND_RESERVE = """
local user_key = KEYS[1]
local amount = tonumber(ARGV[1])
-- 현재 available 조회
local avail_raw = redis.call('HGET', user_key, 'available')
local avail = 0.0
if avail_raw then
  avail = tonumber(avail_raw)
end
if avail >= amount then
  -- 가용금 감소 및 locked 증가
  redis.call('HINCRBYFLOAT', user_key, 'available', -amount)
  redis.call('HINCRBYFLOAT', user_key, 'locked', amount)
  return 1
end
return 0
"""

# Lua 스크립트: 예약 취소 (locked -= amount; available += amount)
_LUA_RELEASE = """
local user_key = KEYS[1]
local amount = tonumber(ARGV[1])
-- locked 감소 및 available 증가
redis.call('HINCRBYFLOAT', user_key, 'locked', -amount)
redis.call('HINCRBYFLOAT', user_key, 'available', amount)
return 1
"""

# Lua 스크립트: 예약 확정(locked에서 제거, 실제 소모는 원장에 의해 수행됨)
_LUA_FINALIZE = """
local user_key = KEYS[1]
local amount = tonumber(ARGV[1])
-- locked 감소 (체결로 인한 실제 차감; 이미 available은 예약 시 차감됨)
redis.call('HINCRBYFLOAT', user_key, 'locked', -amount)
return 1
"""


# ---------------------------
# Redis 초기화 / 종료 유틸
# ---------------------------
async def init_redis(url: Optional[str] = None) -> Any:
    """
    redis.asyncio 우선 시도, 없으면 aioredis 사용.
    반환: redis client
    """
    if url is None:
        url = os.environ.get(REDIS_URL_ENV) or _get_default_redis_url()
    try:
        import importlib

        try:
            mod = importlib.import_module("redis.asyncio")
            Redis = getattr(mod, "Redis")
            client = Redis.from_url(url, decode_responses=False)
            await client.ping()
            logger.debug("[risk] redis.asyncio 클라이언트 연결 성공")
            return client
        except Exception:
            mod2 = importlib.import_module("aioredis")
            client2 = getattr(mod2, "from_url")(url)
            await client2.ping()
            logger.debug("[risk] aioredis 클라이언트 연결 성공")
            return client2
    except ModuleNotFoundError:
        logger.exception("[risk] Redis 클라이언트 모듈 없음 (redis.asyncio 또는 aioredis 필요)")
        raise


async def close_redis(client: Any) -> None:
    """
    Redis 클라이언트 안전 종료: aclose -> close 순으로 시도
    """
    if client is None:
        return
    try:
        if hasattr(client, "aclose"):
            res = client.aclose()
            if asyncio.iscoroutine(res):
                await res
            return
        if hasattr(client, "close"):
            res = client.close()
            if asyncio.iscoroutine(res):
                await res
    except Exception:
        logger.debug("[risk] Redis 안전종료 중 예외", exc_info=True)


# ---------------------------
# 내부 유틸
# ---------------------------
def _to_decimal(value: Any) -> Decimal:
    """
    입력값을 Decimal로 안전 변환 (문자열, float, Decimal 허용)
    """
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


async def _run_lua(client: Any, script: str, keys: list, args: list) -> Any:
    """
    Lua 스크립트 실행 유틸: 다양한 redis client 호환 처리
    """
    try:
        # redis-py async/redis.asyncio 모두 .eval or .evalsha exists
        # 우선 EVAL 직접 호출
        if hasattr(client, "eval"):
            # redis.asyncio: await client.eval(script, len(keys), *keys, *args)
            return await client.eval(script, len(keys), *keys, *args)
        else:
            # aioredis 혹은 다른 클라이언트: try execute_command
            return await client.execute_command("EVAL", script, len(keys), *keys, *args)
    except Exception:
        logger.exception("[risk] Lua 실행 실패")
        raise


# ---------------------------
# 공개 API: check_order / release_reservation / finalize_reservation
# ---------------------------
async def check_order(order: Dict[str, Any], redis_client: Optional[Any] = None) -> Dict[str, Any]:
    """
    주문 전 검사 및 예약(원자적)
    - order: dict 형태로 최소 필드 필요: client_oid, user_id, quantity, price (price는 market일 경우 None 허용)
    - redis_client: 이미 초기화된 클라이언트를 주입하면 재사용 가능. 없으면 내부에서 init_redis 호출(그리고 자동 종료).
    반환:
      {
        "ok": True/False,
        "reason": "거절 사유 또는 빈 문자열",
        "reserved": {"amount": "123.45"},
        "client_oid": "...",
      }
    """
    internal_client = None
    used_client = redis_client
    try:
        # 필수 필드 검사
        client_oid = order.get("client_oid")
        user_id = order.get("user_id")
        qty = _to_decimal(order.get("quantity"))
        price = order.get("price")
        price_dec = _to_decimal(price) if price is not None else None

        if not client_oid:
            return {"ok": False, "reason": "client_oid 필요", "reserved": {}, "client_oid": None}
        if not user_id:
            return {"ok": False, "reason": "user_id 필요", "reserved": {}, "client_oid": client_oid}
        if qty <= 0:
            return {"ok": False, "reason": "quantity 유효하지 않음", "reserved": {}, "client_oid": client_oid}

        # 주문금액 계산: limit/market 구별 없음(PoC) - price가 없으면 quantity 기본 사용
        if price_dec is None:
            amount = qty  # 예: 시장가 토큰 수용, 실제 환경에서는 별도 로직 필요
        else:
            amount = (price_dec * qty).quantize(Decimal("0.00000001"))  # 정밀도 예시

        # Redis 준비
        if used_client is None:
            internal_client = await init_redis(None)
            used_client = internal_client

        # 멱등성 검사: 이미 reservation 존재하면 중복처리로 간주
        res_key = RESERVATION_KEY.format(client_oid=client_oid)
        existing = None
        try:
            existing = await used_client.get(res_key)  # bytes or None
        except Exception:
            # 일부 클라이언트는 decode_responses=False 이므로 bytes 반환
            try:
                existing = await used_client.get(res_key)
            except Exception:
                existing = None

        if existing:
            # 이미 예약 존재함 - 파싱 후 멱등성 판단
            try:
                if isinstance(existing, (bytes, bytearray)):
                    existing = existing.decode("utf-8")
                payload = orjson.loads(existing)
                # 이미 같은 user/amount이면 ok로 처리
                if payload.get("user_id") == user_id and Decimal(str(payload.get("amount"))) == amount:
                    return {"ok": True, "reason": "이미 예약됨(멱등성)", "reserved": {"amount": str(amount)}, "client_oid": client_oid}
                else:
                    return {"ok": False, "reason": "이미 다른 예약 존재", "reserved": {}, "client_oid": client_oid}
            except Exception:
                # 파싱 실패 시 진행
                pass

        # 원자적 검사/예약: Lua 실행
        user_key = USER_BALANCE_KEY.format(user_id=user_id)
        try:
            ok = await _run_lua(used_client, _LUA_CHECK_AND_RESERVE, [user_key], [str(float(amount))])
        except Exception:
            return {"ok": False, "reason": "Redis Lua 실행 실패", "reserved": {}, "client_oid": client_oid}

        if int(ok) == 1:
            # 예약 성공: reservation key에 메타 저장 (JSON)
            job = {
                "client_oid": client_oid,
                "user_id": user_id,
                "amount": str(amount),
            }
            try:
                raw = orjson.dumps(job).decode("utf-8")
                await used_client.set(res_key, raw, ex=RESERVATION_TTL)
            except Exception:
                # set 실패시 롤백: release via Lua
                try:
                    await _run_lua(used_client, _LUA_RELEASE, [user_key], [str(float(amount))])
                except Exception:
                    logger.exception("[risk] 예약 저장 실패 및 롤백 실패")
                return {"ok": False, "reason": "예약 저장 실패", "reserved": {}, "client_oid": client_oid}

            logger.info("[risk] 예약 성공: client_oid=%s user=%s amount=%s", client_oid, user_id, str(amount))
            return {"ok": True, "reason": "", "reserved": {"amount": str(amount)}, "client_oid": client_oid}
        else:
            # 가용 금액 부족
            logger.info("[risk] 예약 거절(잔고부족): client_oid=%s user=%s amount=%s", client_oid, user_id, str(amount))
            return {"ok": False, "reason": "잔액 부족", "reserved": {}, "client_oid": client_oid}
    finally:
        if internal_client is not None:
            await close_redis(internal_client)


async def release_reservation(client_oid: str, user_id: str, redis_client: Optional[Any] = None) -> Dict[str, Any]:
    """
    예약 해제: reservation key에서 amount 읽어 locked -> available로 반환
    - 예약이 없으면 ok로 처리(멱등성)
    반환: {"ok": True/False, "reason": ...}
    """
    internal_client = None
    used_client = redis_client
    try:
        if not client_oid or not user_id:
            return {"ok": False, "reason": "client_oid/user_id 필요"}
        if used_client is None:
            internal_client = await init_redis(None)
            used_client = internal_client

        res_key = RESERVATION_KEY.format(client_oid=client_oid)
        raw = await used_client.get(res_key)
        if not raw:
            # 이미 처리되었거나 없음
            logger.debug("[risk] 예약 ���음(해제 무시): client_oid=%s", client_oid)
            return {"ok": True, "reason": "예약 없음"}

        try:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            payload = orjson.loads(raw)
            amount = Decimal(str(payload.get("amount", "0")))
        except Exception:
            logger.exception("[risk] reservation 파싱 실패, 강제 해제 시도")
            amount = Decimal("0")

        user_key = USER_BALANCE_KEY.format(user_id=user_id)
        try:
            await _run_lua(used_client, _LUA_RELEASE, [user_key], [str(float(amount))])
        except Exception:
            logger.exception("[risk] release Lua 실패")
            return {"ok": False, "reason": "release 실패"}

        # reservation key 삭제
        try:
            await used_client.delete(res_key)
        except Exception:
            logger.debug("[risk] reservation key 삭제 실패(무시)", exc_info=True)

        logger.info("[risk] 예약 해제 완료: client_oid=%s user=%s amount=%s", client_oid, user_id, str(amount))
        return {"ok": True, "reason": ""}
    finally:
        if internal_client is not None:
            await close_redis(internal_client)


async def finalize_reservation(client_oid: str, user_id: str, redis_client: Optional[Any] = None) -> Dict[str, Any]:
    """
    예약 확정: 예약된 amount를 locked에서 제거하여 실제 지출(원장 기록 전용).
    - 실제로는 이 시점에 원장(ledger) 기록이 선행되어야 함.
    반환: {"ok": True/False, "reason": ...}
    """
    internal_client = None
    used_client = redis_client
    try:
        if not client_oid or not user_id:
            return {"ok": False, "reason": "client_oid/user_id 필요"}
        if used_client is None:
            internal_client = await init_redis(None)
            used_client = internal_client

        res_key = RESERVATION_KEY.format(client_oid=client_oid)
        raw = await used_client.get(res_key)
        if not raw:
            # 예약이 없으면 실패로 처리(또는 이미 확정되었을 수 있음)
            logger.warning("[risk] finalize: 예약 없음 client_oid=%s", client_oid)
            return {"ok": False, "reason": "예약 없음"}

        try:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            payload = orjson.loads(raw)
            amount = Decimal(str(payload.get("amount", "0")))
        except Exception:
            logger.exception("[risk] reservation 파싱 실패 in finalize")
            amount = Decimal("0")

        user_key = USER_BALANCE_KEY.format(user_id=user_id)
        try:
            await _run_lua(used_client, _LUA_FINALIZE, [user_key], [str(float(amount))])
        except Exception:
            logger.exception("[risk] finalize Lua 실패")
            return {"ok": False, "reason": "finalize 실패"}

        # reservation key 삭제
        try:
            await used_client.delete(res_key)
        except Exception:
            logger.debug("[risk] reservation key 삭제 실패(무시)", exc_info=True)

        logger.info("[risk] 예약 확정 완료: client_oid=%s user=%s amount=%s", client_oid, user_id, str(amount))
        return {"ok": True, "reason": ""}
    finally:
        if internal_client is not None:
            await close_redis(internal_client)