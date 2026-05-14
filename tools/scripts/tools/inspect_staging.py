#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inspect staging_candles: list columns, counts, status distribution, recent rows.
Prints human-readable summary to stdout. Read-only.
"""
import importlib.util
import os
import sys
import asyncio
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

# tools/ 디렉토리를 sys.path에 추가하여 _env_loader 접근 가능하게 함
_TOOLS_DIR = str(Path(__file__).parents[2])
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
from _env_loader import load_env
load_env()

# constants.py 로드
_ROOT = str(Path(__file__).parents[3])
_CONST_PATH = os.path.join(_ROOT, "src", "01_core", "config", "constants.py")
_spec = importlib.util.spec_from_file_location("_inspect_stg_consts", _CONST_PATH)
if _spec and _spec.loader:
    _consts = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_consts)  # type: ignore[union-attr]
else:
    _consts = None

_DEFAULT_TIMESCALE_HOST: str = getattr(_consts, "DEFAULT_TIMESCALE_HOST", "127.0.0.1")
_DEFAULT_TIMESCALE_PORT: int = getattr(_consts, "DEFAULT_TIMESCALE_PORT", 58529)
_DEFAULT_TIMESCALE_USER: str = getattr(_consts, "DEFAULT_TIMESCALE_USER", "postgres")
_DEFAULT_TIMESCALE_DB: str = getattr(_consts, "DEFAULT_TIMESCALE_DB", "upbit_trader")

try:
    import asyncpg
except Exception as e:
    raise RuntimeError("asyncpg required") from e

async def get_columns(conn, table: str) -> List[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = $1
        ORDER BY ordinal_position
        """,
        table,
    )
    return [r["column_name"] for r in rows]

async def get_count(conn, table: str) -> int:
    r = await conn.fetchrow(f"SELECT COUNT(*) AS cnt FROM {table}")
    return r["cnt"] if r else 0

async def get_status_counts(conn, table: str, col: str) -> Optional[Dict[str, int]]:
    # returns counts grouped by given column if it exists
    try:
        rows = await conn.fetch(f"SELECT {col}::text AS val, COUNT(*) AS cnt FROM {table} GROUP BY {col} ORDER BY val NULLS LAST")
        return {r["val"]: r["cnt"] for r in rows}
    except Exception:
        return None

async def get_recent(conn, table: str, limit: int = 50):
    # fetch recent rows by time if exists, else by ctid
    cols = await get_columns(conn, table)
    order_by = "time DESC" if "time" in cols else "ctid DESC"
    select_cols = cols if len(cols) <= 20 else cols[:20]
    q = f"SELECT {', '.join(select_cols)} FROM {table} ORDER BY {order_by} LIMIT $1"
    rows = await conn.fetch(q, limit)
    result = [dict(r) for r in rows]
    # isoformat times
    for r in result:
        if "time" in r and r["time"] is not None:
            try:
                r["time"] = r["time"].isoformat()
            except Exception:
                pass
        if "received_at" in r and r["received_at"] is not None:
            try:
                r["received_at"] = r["received_at"].isoformat()
            except Exception:
                pass
    return result

async def main():
    pg_host = (
        os.getenv("TIMESCALE_HOST")
        or os.getenv("POSTGRES_HOST")
        or _DEFAULT_TIMESCALE_HOST
    )
    pg_port = int(
        os.getenv("TIMESCALE_PORT")
        or os.getenv("POSTGRES_PORT")
        or str(_DEFAULT_TIMESCALE_PORT)
    )
    pg_db = (
        os.getenv("TIMESCALE_DB")
        or os.getenv("POSTGRES_DB")
        or _DEFAULT_TIMESCALE_DB
    )
    pg_user = (
        os.getenv("TIMESCALE_USER")
        or os.getenv("POSTGRES_USER")
        or _DEFAULT_TIMESCALE_USER
    )
    pg_pass = (
        os.getenv("TIMESCALE_PASSWORD")
        or os.getenv("POSTGRES_PASSWORD")
        or ""
    )

    dsn = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=3)
    try:
        async with pool.acquire() as conn:
            table = "staging_candles"
            print(f"Connecting to {pg_host}:{pg_port}/{pg_db} as {pg_user}")
            cols = await get_columns(conn, table)
            print(f"\nCOLUMNS ({len(cols)}):")
            print(", ".join(cols) if cols else "(no columns / table missing)")

            total = await get_count(conn, table)
            print(f"\nTOTAL ROWS in {table}: {total}")

            # status columns to probe
            for status_col in ("validated", "processed", "isolated"):
                if status_col in cols:
                    dist = await get_status_counts(conn, table, status_col)
                    print(f"\nDistribution for '{status_col}':")
                    print(json.dumps(dist, ensure_ascii=False, indent=2))
                else:
                    print(f"\nColumn '{status_col}' not present")

            # optionally check for non-null raw_data count
            if "raw_data" in cols:
                rawcnt = await conn.fetchrow(f"SELECT count(*) AS cnt FROM {table} WHERE raw_data IS NOT NULL")
                print(f"\nraw_data NOT NULL count: {rawcnt['cnt'] if rawcnt else 0}")

            recent = await get_recent(conn, table, limit=50)
            print(f"\nRecent {len(recent)} rows (sample):")
            print(json.dumps(recent, default=str, ensure_ascii=False, indent=2))

    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(main())