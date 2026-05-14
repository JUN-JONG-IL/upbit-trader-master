# -*- coding: utf-8 -*-
"""
OEMS 원장(ledger) 모듈 - PoC (metadata 직렬화 수정판)

설명:
- asyncpg에 dict 타입을 직접 넘길 때 타입 불일치 에러가 발생하여(metadata에 dict 전달 시
  asyncpg.exceptions.DataError: expected str, got dict), metadata를 JSON 문자열로 직렬화하여
  전달하도록 수정했습니다.
- 이 파일은 이전 PoC와 동일한 책임을 유지하되 metadata 처리만 보강합니다.
- 모든 주석은 한글로 작성되어 있습니다.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
import json
from decimal import Decimal
from typing import Any, Dict, Optional

logger = logging.getLogger("oems.ledger")
logging.getLogger("oems.ledger").addHandler(logging.NullHandler())

# 환경변수로 DSN을 읽을 수 있게 함
TIMESCALE_DSN_ENV = "TIMESCALE_DSN"


# ---------------------------
# asyncpg pool 헬퍼
# ---------------------------
async def create_pool(dsn: Optional[str] = None):
    """
    asyncpg 풀 생성 유틸. dsn이 None이면 환경변수 TIMESCALE_DSN 사용.
    """
    if dsn is None:
        dsn = os.environ.get(TIMESCALE_DSN_ENV)
    if not dsn:
        logger.warning("[ledger] Timescale DSN 없음 - DB 연동 없이 동작 (테스트 전용)")
        return None
    try:
        import asyncpg  # type: ignore
        pool = await asyncpg.create_pool(dsn)
        logger.info("[ledger] asyncpg pool 생성 성공")
        return pool
    except Exception:
        logger.exception("[ledger] asyncpg 풀 생성 실패")
        return None


async def close_pool(pool: Any):
    """
    asyncpg pool 안전 종료
    """
    if pool is None:
        return
    try:
        await pool.close()
    except Exception:
        logger.debug("[ledger] pool 종료 중 예외", exc_info=True)


# ---------------------------
# 테이블 초기화 (개발/테스트용)
# ---------------------------
async def init_ledger_table(pool: Any) -> bool:
    """
    개발/테스트용으로 orders_ledger 테이블을 생성합니다.
    - pool: asyncpg pool (필수)
    반환: True 성공, False 실패 또는 pool 없음
    """
    if pool is None:
        logger.warning("[ledger] init_ledger_table: pool이 없습니다")
        return False
    sql = """
    CREATE TABLE IF NOT EXISTS orders_ledger (
      order_id TEXT PRIMARY KEY,
      client_oid TEXT UNIQUE,
      trace_id TEXT,
      user_id TEXT,
      symbol TEXT,
      side TEXT,
      order_type TEXT,
      price NUMERIC,
      quantity NUMERIC,
      status TEXT,
      metadata JSONB,
      created_at TIMESTAMPTZ DEFAULT now(),
      updated_at TIMESTAMPTZ DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_orders_ledger_user_id ON orders_ledger (user_id);
    CREATE INDEX IF NOT EXISTS idx_orders_ledger_symbol ON orders_ledger (symbol);
    """
    try:
        async with pool.acquire() as conn:
            await conn.execute(sql)
        logger.info("[ledger] orders_ledger 테이블 초기화 완료")
        return True
    except Exception:
        logger.exception("[ledger] orders_ledger 테이블 생성 실패")
        return False


# ---------------------------
# 내부 유틸: metadata 직렬화
# ---------------------------
def _serialize_metadata(metadata: Any) -> str:
    """
    metadata를 DB에 넘기기 전에 JSON 문자열로 직렬화합니다.
    - asyncpg는 JSONB 파라미터로 문자열을 기대하는 환경이 있으므로 안전하게 str로 전달합니다.
    """
    if metadata is None:
        return "{}"
    if isinstance(metadata, str):
        # 이미 문자열이면 그대로 반환(전형적으로 JSON 문자열 가능)
        return metadata
    try:
        return json.dumps(metadata, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        logger.exception("[ledger] metadata 직렬화 실패, 빈 객체 사용")
        return "{}"


# ---------------------------
# 핵심 기능: idempotent 기록
# ---------------------------
async def record_order(pool: Any, order: Dict[str, Any]) -> Dict[str, Any]:
    """
    주문을 원장에 idempotent 하게 기록합니다.
    - pool: asyncpg pool (권장). None이면 파일 수준 에러 반환(테스트 전용).
    - order: dict, 권장 필드: client_oid, trace_id, user_id, symbol, side, order_type, price, quantity, metadata
    반환:
      {
        "ok": True/False,
        "order_id": "...",
        "inserted": True/False,  # True: 신규 삽입, False: 이미 존재하여 삽입되지 않음
        "reason": "..."  # 실패 사유
      }
    """
    if pool is None:
        logger.warning("[ledger] record_order: DB pool 없음 - 동작 불가")
        return {"ok": False, "order_id": None, "inserted": False, "reason": "DB pool 없음"}

    client_oid = order.get("client_oid") or str(uuid.uuid4())
    trace_id = order.get("trace_id")
    user_id = order.get("user_id")
    symbol = order.get("symbol")
    side = order.get("side")
    order_type = order.get("order_type")
    price = order.get("price")
    quantity = order.get("quantity")
    metadata = order.get("metadata") or {}
    status = order.get("status") or "created"

    # 정밀도: Decimal로 변환
    try:
        price_val = Decimal(str(price)) if price is not None else None
    except Exception:
        price_val = None
    try:
        qty_val = Decimal(str(quantity)) if quantity is not None else None
    except Exception:
        qty_val = None

    # metadata 직렬화 (JSON 문자열)
    metadata_json = _serialize_metadata(metadata)

    order_id = str(uuid.uuid4())

    sql = """
    INSERT INTO orders_ledger (
      order_id, client_oid, trace_id, user_id, symbol, side, order_type, price, quantity, status, metadata
    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
    ON CONFLICT (client_oid) DO NOTHING
    RETURNING order_id;
    """

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, order_id, client_oid, trace_id, user_id, symbol, side, order_type, price_val, qty_val, status, metadata_json)
            if row and row.get("order_id"):
                # 신규 삽입 성공
                logger.info("[ledger] 주문 기록(신규): client_oid=%s order_id=%s user=%s symbol=%s qty=%s", client_oid, row["order_id"], user_id, symbol, qty_val)
                return {"ok": True, "order_id": row["order_id"], "inserted": True, "reason": ""}
            else:
                # 이미 존재: 조회해서 existing id 반환
                existing = await conn.fetchrow("SELECT order_id FROM orders_ledger WHERE client_oid = $1", client_oid)
                existing_id = existing["order_id"] if existing else None
                logger.info("[ledger] 주문 중복: client_oid=%s existing_order_id=%s", client_oid, existing_id)
                return {"ok": True, "order_id": existing_id, "inserted": False, "reason": "duplicate"}
    except Exception:
        logger.exception("[ledger] record_order 예외")
        return {"ok": False, "order_id": None, "inserted": False, "reason": "db error"}


async def upsert_order(pool: Any, order: Dict[str, Any], update_on_conflict: bool = True) -> Dict[str, Any]:
    """
    이미 존재하는 주문을 업데이트(선택적)하거나 없으면 삽입합니다.
    - update_on_conflict True이면 ON CONFLICT (client_oid) DO UPDATE SET ... 로 업데이트 수행
    - 반환값 형식은 record_order와 동일하게 order_id 및 inserted 플래그 제공
    """
    if pool is None:
        logger.warning("[ledger] upsert_order: DB pool 없음")
        return {"ok": False, "order_id": None, "inserted": False, "reason": "DB pool 없음"}

    client_oid = order.get("client_oid") or str(uuid.uuid4())
    trace_id = order.get("trace_id")
    user_id = order.get("user_id")
    symbol = order.get("symbol")
    side = order.get("side")
    order_type = order.get("order_type")
    price = order.get("price")
    quantity = order.get("quantity")
    metadata = order.get("metadata") or {}
    status = order.get("status") or "created"

    try:
        price_val = Decimal(str(price)) if price is not None else None
    except Exception:
        price_val = None
    try:
        qty_val = Decimal(str(quantity)) if quantity is not None else None
    except Exception:
        qty_val = None

    # metadata 직렬화
    metadata_json = _serialize_metadata(metadata)

    order_id = str(uuid.uuid4())

    if update_on_conflict:
        sql = """
        INSERT INTO orders_ledger (
          order_id, client_oid, trace_id, user_id, symbol, side, order_type, price, quantity, status, metadata, updated_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11, now())
        ON CONFLICT (client_oid) DO UPDATE
          SET trace_id = EXCLUDED.trace_id,
              user_id = EXCLUDED.user_id,
              symbol = EXCLUDED.symbol,
              side = EXCLUDED.side,
              order_type = EXCLUDED.order_type,
              price = EXCLUDED.price,
              quantity = EXCLUDED.quantity,
              status = EXCLUDED.status,
              metadata = EXCLUDED.metadata,
              updated_at = now()
        RETURNING order_id;
        """
    else:
        # conflict 시 아무 것도 하지 않음
        sql = """
        INSERT INTO orders_ledger (
          order_id, client_oid, trace_id, user_id, symbol, side, order_type, price, quantity, status, metadata
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        ON CONFLICT (client_oid) DO NOTHING
        RETURNING order_id;
        """

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, order_id, client_oid, trace_id, user_id, symbol, side, order_type, price_val, qty_val, status, metadata_json)
            if row and row.get("order_id"):
                return {"ok": True, "order_id": row["order_id"], "inserted": True, "reason": ""}
            else:
                existing = await conn.fetchrow("SELECT order_id FROM orders_ledger WHERE client_oid = $1", client_oid)
                existing_id = existing["order_id"] if existing else None
                return {"ok": True, "order_id": existing_id, "inserted": False, "reason": "duplicate"}
    except Exception:
        logger.exception("[ledger] upsert_order 예외")
        return {"ok": False, "order_id": None, "inserted": False, "reason": "db error"}


# ---------------------------
# 조회 유틸
# ---------------------------
async def get_order_by_client_oid(pool: Any, client_oid: str) -> Optional[Dict[str, Any]]:
    """
    client_oid로 원장에 저장된 주문을 조회해서 dict로 반환
    """
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM orders_ledger WHERE client_oid = $1", client_oid)
            if not row:
                return None
            # asyncpg.Record -> dict 변환
            return dict(row)
    except Exception:
        logger.exception("[ledger] get_order_by_client_oid 예외")
        return None


# ---------------------------
# 단독 실행 테스트(개발용)
# ---------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ledger PoC test")
    parser.add_argument("--timescale-dsn", type=str, default=os.environ.get(TIMESCALE_DSN_ENV, ""), help="Timescale/Postgres DSN")
    parser.add_argument("--init", action="store_true", help="테이블 초기화")
    parser.add_argument("--test-insert", action="store_true", help="샘플 주문 삽입")
    args = parser.parse_args()

    async def _main():
        pool = await create_pool(args.timescale_dsn)
        if args.init:
            ok = await init_ledger_table(pool)
            print("init:", ok)
        if args.test_insert:
            sample = {
                "client_oid": "test-client-oid-1",
                "trace_id": "trace-xyz",
                "user_id": "user_1",
                "symbol": "KRW-BTC",
                "side": "buy",
                "order_type": "limit",
                "price": "50000",
                "quantity": "0.001",
                "metadata": {"note": "test"}
            }
            res = await record_order(pool, sample)
            print("record:", res)
            fetched = await get_order_by_client_oid(pool, sample["client_oid"])
            print("fetched:", fetched)
        if pool:
            await close_pool(pool)

    asyncio.run(_main())