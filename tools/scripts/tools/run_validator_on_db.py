#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Read unvalidated staging_candles and run validator.validate_candles on them (read-only).
This version auto-detects available columns and builds WHERE clause accordingly
to avoid UndefinedColumnError for validated/isolated/processed columns.
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
_spec = importlib.util.spec_from_file_location("_run_val_db_consts", _CONST_PATH)
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

# --- robust import of validator utilities ---
_validate_batch = None  # async function
# Try relative import first
try:
    from .validator import validate_candles_from_dicts  # type: ignore
    _validate_batch = validate_candles_from_dicts  # type: ignore
except Exception:
    # Fallback: load validator.py by path
    cur_dir = os.path.dirname(__file__)
    validator_path = os.path.join(cur_dir, "validator.py")
    if not os.path.exists(validator_path):
        raise RuntimeError(f"validator.py not found at expected path: {validator_path}")
    spec = importlib.util.spec_from_file_location("local_validator", validator_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to create spec for validator.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore
    if hasattr(mod, "validate_candles_from_dicts"):
        _validate_batch = getattr(mod, "validate_candles_from_dicts")
    else:
        raise RuntimeError("validator.validate_candles_from_dicts not found in validator.py")

# === helper: determine identifier column and available columns for staging_candles ===
async def _get_table_columns(conn, table_name: str) -> List[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = $1
        ORDER BY ordinal_position
        """,
        table_name,
    )
    return [r["column_name"] for r in rows] if rows else []

async def _find_row_identifier_and_columns(conn) -> Tuple[str, str, List[str]]:
    """
    Return (id_expr, id_alias, available_columns)
    Prefer primary key -> id column -> ctid::text
    """
    col_names = await _get_table_columns(conn, "staging_candles")

    # primary key
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
        return pk_row["col"], pk_row["col"], col_names

    if "id" in col_names:
        return "id", "id", col_names

    return "ctid::text", "ctid", col_names

def _build_where_clause(available_cols: List[str]) -> str:
    """
    Build WHERE clause conditions depending on available flag columns.
    Priority:
      - if 'validated' exists: use validated IS DISTINCT FROM TRUE
      - else if 'processed' exists: use processed IS DISTINCT FROM TRUE
      - else: no processed/validated filter (select all rows) -- but include isolated if present
    Also include isolated IS DISTINCT FROM TRUE if 'isolated' exists.
    """
    clauses = []
    if "validated" in available_cols:
        clauses.append("(validated IS DISTINCT FROM TRUE)")
    elif "processed" in available_cols:
        # use processed as proxy for "not yet finalized/validated"
        clauses.append("(processed IS DISTINCT FROM TRUE)")
    # include isolated if present
    if "isolated" in available_cols:
        clauses.append("(isolated IS DISTINCT FROM TRUE)")
    # default: if no processed/validated and no isolated, select all rows
    if clauses:
        return " AND ".join(clauses)
    return "TRUE"

async def fetch_unvalidated(pool, limit: int = 1000) -> (List[Dict[str, Any]], str):
    async with pool.acquire() as conn:
        id_expr, id_alias, available_cols = await _find_row_identifier_and_columns(conn)

        # desired columns we can use; only include those present
        desired = ["time", "symbol", "timeframe", "open", "high", "low", "close", "volume", "seq", "received_at", "raw_data"]
        select_cols = [c for c in desired if c in available_cols]

        select_clause = ", ".join([f"{id_expr} AS row_id"] + select_cols) if select_cols else f"{id_expr} AS row_id"

        where_clause = _build_where_clause(available_cols)

        order_clause = "time NULLS LAST" if "time" in available_cols else "row_id"

        q = f"""
            SELECT {select_clause}
            FROM staging_candles
            WHERE {where_clause}
            ORDER BY {order_clause}
            LIMIT $1
        """
        rows = await conn.fetch(q, limit)
        result = []
        for r in rows:
            d = dict(r)
            if "time" in d and d.get("time") is not None:
                try:
                    d["time"] = d["time"].isoformat()
                except Exception:
                    pass
            if "received_at" in d and d.get("received_at") is not None:
                try:
                    d["received_at"] = d["received_at"].isoformat()
                except Exception:
                    pass
            result.append(d)
        return result, id_alias

# === main flow ===
async def main(dsn: Optional[str] = None, limit: int = 1000):
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
        rows, id_alias = await fetch_unvalidated(pool, limit=limit)
        print(f"FETCHED: {len(rows)} staging rows (limit={limit}), id_alias={id_alias}")
        if not rows:
            return

        # Run validator (batch)
        summary = await _validate_batch(rows, zscore_threshold=float(os.getenv("VALIDATOR_ZSCORE", "3.0")))
        print("VALIDATION_SUMMARY:")
        print(json.dumps(summary, default=str, ensure_ascii=False, indent=2))

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

        validated_ids = [r["row_id"] for r in rows if r["row_id"] not in isolate_ids]

        print(f"ISOLATE_COUNT: {len(isolate_ids)}")
        if isolate_ids:
            print("ISOLATE_IDS_SAMPLE:", sorted(list(isolate_ids))[:200])
        print(f"VALIDATED_COUNT (candidates): {len(validated_ids)}")
        if validated_ids:
            print("VALIDATED_IDS_SAMPLE:", sorted(validated_ids)[:200])

    finally:
        await pool.close()

if __name__ == "__main__":
    import sys
    limit = 1000
    dsn = None
    if len(sys.argv) > 1:
        dsn = sys.argv[1]
    if len(sys.argv) > 2:
        try:
            limit = int(sys.argv[2])
        except Exception:
            pass
    asyncio.run(main(dsn=dsn, limit=limit))