#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run validator on most recent N rows from staging_candles (ignores processed/validated flags).
Prints validation summary and lists identifiers of failed/outlier rows.

Usage:
  python tools/scripts/tools/run_validator_on_recent.py [limit]

Default limit: 500
"""
from __future__ import annotations

import os
import asyncio
import json
import importlib.util
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# tools/ 디렉토리를 sys.path에 추가하여 _env_loader 접근 가능하게 함
_TOOLS_DIR = str(Path(__file__).parents[2])
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
from _env_loader import load_env
load_env()

# constants.py 로드
_ROOT = str(Path(__file__).parents[3])
_CONST_PATH = os.path.join(_ROOT, "src", "01_core", "config", "constants.py")
_spec = importlib.util.spec_from_file_location("_run_val_rec_consts", _CONST_PATH)
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

# --- load validator (robust, avoid package __init__ side-effects) ---
def _load_validator_batch():
    # try package-relative first
    try:
        from src.data.validator import validate_candles_from_dicts  # type: ignore
        return validate_candles_from_dicts
    except Exception:
        # fallback load by path
        cur_dir = os.path.join(os.path.dirname(__file__))
        validator_path = os.path.join(cur_dir, "validator.py")
        if not os.path.exists(validator_path):
            raise RuntimeError(f"validator.py not found at {validator_path}")
        spec = importlib.util.spec_from_file_location("local_validator", validator_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)  # type: ignore
        if hasattr(mod, "validate_candles_from_dicts"):
            return getattr(mod, "validate_candles_from_dicts")
        raise RuntimeError("validate_candles_from_dicts not found")

_validate_batch = _load_validator_batch()

# === DB helpers ===
async def get_recent_rows(pool, limit: int = 500) -> Tuple[List[Dict[str, Any]], str]:
    async with pool.acquire() as conn:
        # determine row id expr
        pk_row = await conn.fetchrow(
            """
            SELECT a.attname AS col
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = 'staging_candles'::regclass AND i.indisprimary
            LIMIT 1
            """
        )
        if pk_row and pk_row.get("col"):
            id_expr = pk_row["col"]
            id_alias = pk_row["col"]
        else:
            # prefer id column
            id_exists = await conn.fetchrow(
                "SELECT column_name FROM information_schema.columns WHERE table_name='staging_candles' AND column_name='id' LIMIT 1"
            )
            if id_exists:
                id_expr = "id"
                id_alias = "id"
            else:
                id_expr = "ctid::text"
                id_alias = "ctid"

        # select available columns (safe subset)
        cols_rows = await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='staging_candles' ORDER BY ordinal_position"
        )
        cols = [r["column_name"] for r in cols_rows]
        desired = ["time","symbol","timeframe","open","high","low","close","volume","seq","received_at","raw_data","processed","isolated","validated"]
        select_cols = [c for c in desired if c in cols]
        select_clause = ", ".join([f"{id_expr} AS row_id"] + select_cols)
        q = f"SELECT {select_clause} FROM staging_candles ORDER BY time DESC NULLS LAST LIMIT $1"
        rows = await conn.fetch(q, limit)
        result = []
        for r in rows:
            d = dict(r)
            if "time" in d and d["time"] is not None:
                try:
                    d["time"] = d["time"].isoformat()
                except Exception:
                    pass
            if "received_at" in d and d["received_at"] is not None:
                try:
                    d["received_at"] = d["received_at"].isoformat()
                except Exception:
                    pass
            result.append(d)
        return result, id_alias

# === main ===
async def main(dsn: Optional[str] = None, limit: int = 500):
    if dsn is None:
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

    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
    try:
        rows, id_alias = await get_recent_rows(pool, limit=limit)
        print(f"FETCHED_RECENT: {len(rows)} rows (limit={limit}), id_alias={id_alias}")
        if not rows:
            return

        summary = await _validate_batch(rows, zscore_threshold=float(os.getenv("VALIDATOR_ZSCORE","3.0")))
        print("VALIDATION_SUMMARY:")
        print(json.dumps(summary, default=str, ensure_ascii=False, indent=2))

        # collect failed/outlier row_ids
        isolate_ids = set()
        failed = summary.get("failed_candles", [])
        for f in failed:
            idx = f.get("index")
            if idx is not None and 0 <= idx < len(rows):
                isolate_ids.add(rows[idx]["row_id"])
        outliers = summary.get("outliers", [])
        if isinstance(outliers, list):
            for o in outliers:
                idx = o.get("index")
                if idx is not None and 0 <= idx < len(rows):
                    isolate_ids.add(rows[idx]["row_id"])
        elif isinstance(outliers, dict):
            for k in outliers.keys():
                try:
                    idx = int(k)
                    if 0 <= idx < len(rows):
                        isolate_ids.add(rows[idx]["row_id"])
                except Exception:
                    pass

        print(f"ISOLATE_COUNT: {len(isolate_ids)}")
        if isolate_ids:
            print("ISOLATE_IDS_SAMPLE:", sorted(list(isolate_ids))[:200])
            # print sample rows for first 10 isolate ids
            sample = []
            for r in rows:
                if r["row_id"] in isolate_ids and len(sample) < 10:
                    sample.append(r)
            print("ISOLATE_SAMPLE_ROWS:")
            print(json.dumps(sample, default=str, ensure_ascii=False, indent=2))

    finally:
        await pool.close()

if __name__ == "__main__":
    import sys
    limit = 500
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except Exception:
            pass
    asyncio.run(main(limit=limit))