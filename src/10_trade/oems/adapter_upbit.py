# -*- coding: utf-8 -*-
"""
Upbit 어댑터(POC)

목적:
- Upbit 거래소와의 기본적인 REST 주문 호출(비동기)을 PoC 수준으로 제공합니다.
- 운영용으로 사용하려면 키 관리(Vault), 요청/응답 검증, 재시도/백오프, 로깅/모니터링 보강 필요.
- 환경변수에 API 키가 없으면 '시뮬레이션 모드'로 동작하여 실제 요청을 수행하지 않고
  실행 결과를 시뮬레이트합니다(개발/테스트 편의).

지원 기능(POC)
- create_session(): aiohttp 세션 생성 유틸
- place_order(order): 주문 전송(실거래/시뮬)
- cancel_order(uuid/order_id): 주문 취소(실거래/시뮬)
- get_order(uuid/order_id): 주문 조회(실거래/시뮬)
- simple websocket placeholder (실제 구현은 별도)

환경변수
- UPBIT_ACCESS_KEY: (선택) 실거래용 액세스 키
- UPBIT_SECRET_KEY: (선택) 실거래용 시크릿 키
- UPBIT_API_URL: (선택) Upbit REST 엔드포인트 (기본: https://api.upbit.com)

주의
- JWT 서명 기능은 pyjwt가 설치된 경우에만 자동 사용됩니다. 설치되지 않았으면 실제 요청은 실패합니다.
- 이 파일은 단일 파일 작업 규칙에 따라 PoC 구현만 제공합니다.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

import orjson  # type: ignore

logger = logging.getLogger("oems.adapter_upbit")
logging.getLogger("oems.adapter_upbit").addHandler(logging.NullHandler())

# 환경 변수 읽기
UPBIT_ACCESS_KEY = os.environ.get("UPBIT_ACCESS_KEY", "")
UPBIT_SECRET_KEY = os.environ.get("UPBIT_SECRET_KEY", "")
UPBIT_API_URL = os.environ.get("UPBIT_API_URL", "https://api.upbit.com")

# 기본 엔드포인트 경로
_ORDERS_PATH = "/v1/orders"
_ORDER_CANCEL_PATH = "/v1/order"  # Upbit API 가이드에 따라 사용 (POC)
_ORDER_GET_PATH = "/v1/order"     # POc: 동일 엔드포인트 사용

# 시뮬레이션 모드 판단
SIMULATION_MODE = not (bool(UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY))


# ---------------------------
# 유틸: aiohttp 세션 생성
# ---------------------------
async def create_session(timeout: int = 15):
    """
    aiohttp ClientSession 생성 유틸.
    - aiohttp가 없으면 명확한 에러 메시지 발생.
    """
    try:
        import aiohttp  # type: ignore
    except ModuleNotFoundError:
        logger.exception("[adapter_upbit] aiohttp 모듈이 필요합니다. 설치: pip install aiohttp")
        raise

    # 기본 헤더
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "upbit-oems-poc/1.0",
    }
    timeout_obj = aiohttp.ClientTimeout(total=timeout)
    session = aiohttp.ClientSession(headers=headers, timeout=timeout_obj)
    return session


# ---------------------------
# 유틸: Authorization 헤더 생성 (JWT) - optional(pyjwt 필요)
# ---------------------------
def _make_auth_header(payload_body: Dict[str, Any]) -> Dict[str, str]:
    """
    Upbit API 인증용 JWT 생성(POC).
    - pyjwt 가 설치되어 있고 UPBIT_ACCESS_KEY/UPBIT_SECRET_KEY가 설정되어 있으면 시도.
    - pyjwt 미설치 또는 키 미설정 시 예외/빈 dict 반환.
    주의: 실제 운영에서는 nonce/iat, 쿼리/바디 서명 등을 Upbit 문서에 맞춰 정확히 구현해야 합니다.
    """
    if SIMULATION_MODE:
        return {}

    try:
        import jwt  # type: ignore
    except ModuleNotFoundError:
        logger.error("[adapter_upbit] pyjwt 미설치: 실제 Upbit 호출을 위해 'pyjwt' 설치 필요 (pip install pyjwt).")
        raise

    if not UPBIT_ACCESS_KEY or not UPBIT_SECRET_KEY:
        raise RuntimeError("UPBIT_ACCESS_KEY/UPBIT_SECRET_KEY 필요")

    # 간단 JWT 페이로드: access_key + nonce 형식 (Upbit 가이드에 따름)
    nonce = str(uuid.uuid4())
    payload = {"access_key": UPBIT_ACCESS_KEY, "nonce": nonce}
    # 만약 바디가 있으면 payload에 추가할 수 있음 (POC)
    # token 생성 (HS256)
    token = jwt.encode(payload, UPBIT_SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------
# 메인 기능: 주문 전송 / 취소 / 조회 (비동기)
# ---------------------------
async def place_order(order: Dict[str, Any], session: Optional[Any] = None) -> Dict[str, Any]:
    """
    주문 전송 (비동기).
    - order 구조(권장):
      {
        "client_oid": "...",
        "market": "KRW-BTC" or "KRW-BTC",
        "side": "bid" or "ask"  # Upbit naming: bid(매수), ask(매도)
        "ord_type": "limit" or "price" or "market" (Upbit 문서 참고)
        "price": "10000" (문자열/숫자),
        "volume": "0.001" (문자열/숫자),
        "metadata": {...}
      }
    - session: aiohttp.ClientSession 을 주입하면 재사용(권장)
    - 반환: Upbit 응답(JSON) 또는 시뮬 결과 dict
    """
    # 시뮬레이션 모드: 실제 호출 없이 성공 응답 반환
    if SIMULATION_MODE:
        fake_uuid = uuid.uuid4().hex
        logger.info("[adapter_upbit] 시뮬레이션 모드로 주문 시뮬레이트: client_oid=%s", order.get("client_oid"))
        return {
            "ok": True,
            "simulated": True,
            "client_oid": order.get("client_oid"),
            "uuid": fake_uuid,
            "market": order.get("market"),
            "side": order.get("side"),
            "ord_type": order.get("ord_type"),
            "price": order.get("price"),
            "volume": order.get("volume"),
            "result": "simulated",
        }

    # 실제 호출: aiohttp 사용
    created_local = False
    if session is None:
        session = await create_session()
        created_local = True

    url = UPBIT_API_URL.rstrip("/") + _ORDERS_PATH
    body = {
        "market": order.get("market") or order.get("symbol"),
        "side": order.get("side"),
        "ord_type": order.get("ord_type"),
    }
    # Upbit expects volume/price/price depending on ord_type
    if "volume" in order and order.get("volume") is not None:
        body["volume"] = str(order.get("volume"))
    if "price" in order and order.get("price") is not None:
        body["price"] = str(order.get("price"))
    # client_oid 사용
    if order.get("client_oid"):
        body["identifier"] = order.get("client_oid")  # Upbit uses client_oid or identifier in some APIs; PoC

    # Auth header
    try:
        auth = _make_auth_header(body)
    except Exception as e:
        if created_local:
            await _safe_close_session(session)
        raise

    headers = {}
    headers.update(auth)

    try:
        # POST 요청
        async with session.post(url, data=orjson.dumps(body), headers=headers) as resp:
            text = await resp.text()
            status = resp.status
            try:
                data = orjson.loads(text.encode("utf-8"))
            except Exception:
                data = {"raw": text}
            result = {"ok": status >= 200 and status < 300, "status": status, "data": data}
            logger.info("[adapter_upbit] place_order 응답: status=%d client_oid=%s", status, order.get("client_oid"))
            return result
    except Exception:
        logger.exception("[adapter_upbit] place_order 예외")
        raise
    finally:
        if created_local:
            await _safe_close_session(session)


async def cancel_order(order_uuid: str, session: Optional[Any] = None) -> Dict[str, Any]:
    """
    주문 취소 (비동기)
    - order_uuid: Upbit에서 사용하는 주문 식별자 (POC)
    - 반환: Upbit 응답(JSON) 또는 시뮬 결과
    """
    if SIMULATION_MODE:
        logger.info("[adapter_upbit] 시뮬레이션 모드로 주문 취소 시뮬레이트: uuid=%s", order_uuid)
        return {"ok": True, "simulated": True, "uuid": order_uuid, "result": "canceled"}

    created_local = False
    if session is None:
        session = await create_session()
        created_local = True

    url = UPBIT_API_URL.rstrip("/") + _ORDER_CANCEL_PATH
    body = {"uuid": order_uuid}
    try:
        auth = _make_auth_header(body)
    except Exception:
        if created_local:
            await _safe_close_session(session)
        raise
    headers = {}
    headers.update(auth)

    try:
        async with session.delete(url, data=orjson.dumps(body), headers=headers) as resp:
            text = await resp.text()
            try:
                data = orjson.loads(text.encode("utf-8"))
            except Exception:
                data = {"raw": text}
            return {"ok": resp.status >= 200 and resp.status < 300, "status": resp.status, "data": data}
    except Exception:
        logger.exception("[adapter_upbit] cancel_order 예외")
        raise
    finally:
        if created_local:
            await _safe_close_session(session)


async def get_order(order_uuid: str, session: Optional[Any] = None) -> Dict[str, Any]:
    """
    주문 조회 (비동기)
    """
    if SIMULATION_MODE:
        logger.info("[adapter_upbit] 시뮬레이션 모드로 주문 조회 시뮬레이트: uuid=%s", order_uuid)
        return {"ok": True, "simulated": True, "uuid": order_uuid, "status": "done", "filled_amount": "0.001"}

    created_local = False
    if session is None:
        session = await create_session()
        created_local = True

    url = UPBIT_API_URL.rstrip("/") + _ORDER_GET_PATH
    params = {"uuid": order_uuid}
    try:
        auth = _make_auth_header(params)
    except Exception:
        if created_local:
            await _safe_close_session(session)
        raise
    headers = {}
    headers.update(auth)

    try:
        import yarl  # type: ignore
        # GET 요청 with querystring
        q = "?" + "&".join([f"{k}={v}" for k, v in params.items()])
        async with session.get(url + q, headers=headers) as resp:
            text = await resp.text()
            try:
                data = orjson.loads(text.encode("utf-8"))
            except Exception:
                data = {"raw": text}
            return {"ok": resp.status >= 200 and resp.status < 300, "status": resp.status, "data": data}
    except Exception:
        logger.exception("[adapter_upbit] get_order 예외")
        raise
    finally:
        if created_local:
            await _safe_close_session(session)


async def _safe_close_session(session: Any):
    """
    aiohttp session 안전 종료(aclose/close)
    """
    try:
        if hasattr(session, "aclose"):
            res = session.aclose()
            if asyncio.iscoroutine(res):
                await res
            return
        if hasattr(session, "close"):
            res = session.close()
            if asyncio.iscoroutine(res):
                await res
    except Exception:
        logger.debug("[adapter_upbit] 세션 안전종료 중 예외", exc_info=True)


# ---------------------------
# WebSocket placeholder (POC)
# ---------------------------
async def websocket_subscribe(markets: Optional[list] = None):
    """
    WebSocket 구독 자리표시자 - 실제 구현은 Upbit WebSocket spec에 맞춰 작성 필요.
    이 함수는 예제 목적이며 실제 사용시 별도 모듈로 분리 권장.
    """
    logger.info("[adapter_upbit] websocket_subscribe placeholder 호출 (markets=%s)", markets)
    # 실제 구현에서는 wss://api.upbit.com/websocket/v1 을 사용하고
    # subscription format 및 인증을 구현해야 함.
    await asyncio.sleep(0.1)
    return {"ok": True, "msg": "websocket placeholder - not implemented"}


# ---------------------------
# 단독 실행(빠른 수동 테스트 PoC)
# ---------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Upbit adapter PoC test")
    parser.add_argument("--sim", action="store_true", help="시뮬레이션 모드로 테스트")
    parser.add_argument("--place", action="store_true", help="샘플 주문 전송")
    parser.add_argument("--cancel", action="store_true", help="샘플 주문 취소")
    args = parser.parse_args()

    async def _main():
        # 강제 시뮬레이션 모드로 동작시키려면 환경변수 UPBIT_ACCESS_KEY/SECRET 를 비워두세요.
        sample_order = {
            "client_oid": f"cli-{uuid.uuid4().hex[:8]}",
            "market": "KRW-BTC",
            "symbol": "KRW-BTC",
            "side": "bid",  # Upbit: bid/ask
            "ord_type": "limit",
            "price": "50000",
            "volume": "0.001",
            "metadata": {"test": True},
        }
        if args.place:
            res = await place_order(sample_order)
            print("place res:", res)
        if args.cancel:
            # cancel with fake uuid
            res = await cancel_order("fake-uuid-123")
            print("cancel res:", res)

    asyncio.run(_main())