# tools/timescale/inspect_market_ticks.py
# -*- coding: utf-8 -*-
"""
Timescale market_ticks 점검 스크립트
- 기능: DB 연결(환경변수 이용) → market_ticks 존재/스키마/통계/샘플 출력
- 사용법:
  1) 레포 루트에서 실행:
     cd C:/Users/jji24/anaconda3/envs/py311/trade/upbit-trader-master
     C:/Users/jji24/anaconda3/envs/py311/python.exe tools/timescale/inspect_market_ticks.py
- 출력 결과를 복사하여 챗에 붙여 주세요.
- 모든 주석은 한국어입니다.
"""
from __future__ import annotations
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Dict

# tools/ 디렉토리를 sys.path에 추가하여 _env_loader 접근 가능하게 함
_TOOLS_DIR = str(Path(__file__).parents[1])
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
from _env_loader import load_env
load_env()

# constants.py 로드
_ROOT = str(Path(__file__).parents[2])
_CONST_PATH = os.path.join(_ROOT, "src", "01_core", "config", "constants.py")
_spec = importlib.util.spec_from_file_location("_imt_consts", _CONST_PATH)
if _spec and _spec.loader:
    _consts = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_consts)  # type: ignore[union-attr]
else:
    _consts = None

_DEFAULT_TIMESCALE_HOST: str = getattr(_consts, "DEFAULT_TIMESCALE_HOST", "127.0.0.1")
_DEFAULT_TIMESCALE_PORT: int = getattr(_consts, "DEFAULT_TIMESCALE_PORT", 58529)
_DEFAULT_TIMESCALE_USER: str = getattr(_consts, "DEFAULT_TIMESCALE_USER", "postgres")
_DEFAULT_TIMESCALE_DB: str = getattr(_consts, "DEFAULT_TIMESCALE_DB", "upbit_trader")


def get_cfg() -> Dict[str, Any]:
    """환경변수 기반 DB 접속 정보 생성(앱과 동일한 환경변수 사용)"""
    return {
        "host": (
            os.getenv("TIMESCALE_HOST")
            or os.getenv("POSTGRES_HOST")
            or os.getenv("DB_HOST")
            or _DEFAULT_TIMESCALE_HOST
        ),
        "port": int(
            os.getenv("TIMESCALE_PORT")
            or os.getenv("POSTGRES_PORT")
            or os.getenv("DB_PORT")
            or str(_DEFAULT_TIMESCALE_PORT)
        ),
        "dbname": (
            os.getenv("TIMESCALE_DB")
            or os.getenv("POSTGRES_DB")
            or os.getenv("DB_NAME")
            or _DEFAULT_TIMESCALE_DB
        ),
        "user": (
            os.getenv("TIMESCALE_USER")
            or os.getenv("POSTGRES_USER")
            or os.getenv("DB_USER")
            or _DEFAULT_TIMESCALE_USER
        ),
        "password": (
            os.getenv("TIMESCALE_PASSWORD")
            or os.getenv("POSTGRES_PASSWORD")
            or os.getenv("DB_PASS")
            or ""
        ),
    }

def main():
    cfg = get_cfg()
    print("DB 접속 정보 (비밀번호 숨김):", cfg["host"], cfg["port"], cfg["dbname"], cfg["user"])
    try:
        import psycopg2
    except Exception as e:
        print("psycopg2 import 실패:", e)
        sys.exit(1)

    conn = None
    try:
        conn = psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            dbname=cfg["dbname"],
            user=cfg["user"],
            password=cfg["password"],
            connect_timeout=5,
        )
    except Exception as e:
        print("DB 연결 실패:", e)
        sys.exit(1)

    try:
        cur = conn.cursor()
        # 테이블 존재 확인
        cur.execute("SELECT to_regclass('public.market_ticks');")
        reg = cur.fetchone()
        print("to_regclass('public.market_ticks') =", reg[0])

        if reg[0] is None:
            print("market_ticks 테이블이 존재하지 않습니다. (테이블명/스키마 확인 필요)")
            cur.close()
            return

        # 스키마(컬럼) 조회 (information_schema 사용)
        cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'market_ticks'
            ORDER BY ordinal_position;
        """)
        cols = cur.fetchall()
        print("\n-- market_ticks 스키마 (컬럼, 타입, nullable, default) --")
        for c in cols:
            print(f"{c[0]:30} | {c[1]:20} | nullable={c[2]:5} | default={c[3]}")

        # 통계: 총행수, distinct symbols
        cur.execute("SELECT count(*) FROM public.market_ticks;")
        total_rows = cur.fetchone()[0]
        cur.execute("SELECT count(DISTINCT symbol) FROM public.market_ticks;")
        distinct_symbols = cur.fetchone()[0]
        print("\n총 행수:", total_rows)
        print("distinct symbols:", distinct_symbols)

        # 최근 심볼별 최신 타임스탬프 상위 50
        cur.execute("""
            SELECT symbol, max(exchange_ts) AS last_ts, count(*) AS cnt
            FROM public.market_ticks
            GROUP BY symbol
            ORDER BY max(exchange_ts) DESC
            LIMIT 50;
        """)
        samples = cur.fetchall()
        print("\n-- 최근 심볼별 최신 타임스탬프 (최대 50) --")
        for s in samples:
            print(f"symbol={s[0]:15} last_ts={s[1]} count={s[2]}")

        # 최근 raw 50행 샘플
        cur.execute("SELECT * FROM public.market_ticks ORDER BY exchange_ts DESC LIMIT 50;")
        raw = cur.fetchall()
        print(f"\n-- 최근 raw {len(raw)}행 (열 순서는 위 스키마 참고) --")
        for r in raw[:20]:
            print(r)
        if len(raw) > 20:
            print(f"... ({len(raw)-20} more rows omitted)")

        cur.close()
    except Exception as e:
        print("쿼리 실행 중 예외:", type(e), e)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()