#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bulk insert 성능/동작 테스트 스크립트
경로: src/data/scripts/test_bulk_insert.py

사용법:
    cd <repo_root>
    # 필요한 환경변수 설정 (또는 .env 사용)
    export POSTGRES_HOST=localhost
    export POSTGRES_DB=upbit_trader
    export POSTGRES_USER=app_user
    export POSTGRES_PASSWORD=AppUser!2026Example

    python -m src.data.scripts.test_bulk_insert --rows 5000

주의:
- TimescaleDB 컨테이너가 기동 중이어야 합니다.
- 이 스크립트는 실제 DB에 데이터를 삽입합니다. 테스트용 심볼을 사용하세요.
"""
from __future__ import annotations
import os
import time
import random
import argparse
from data.timescale_db import TimescaleConnector

def gen_rows(n, symbol="TEST-BTC", timeframe="1m", exchange="upbit"):
    rows = []
    base_ts = int(time.time())
    for i in range(n):
        ts = base_ts - i * 60
        time_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
        open_v = round(random.uniform(10000, 11000), 2)
        high_v = open_v + round(random.uniform(0, 100),2)
        low_v = open_v - round(random.uniform(0, 100),2)
        close_v = round(random.uniform(low_v, high_v),2)
        vol = round(random.uniform(0, 10),4)
        trade_count = random.randint(1, 10)
        is_closed = True
        ts_millis = int(ts * 1000)
        rows.append((exchange, symbol, timeframe, time_iso, open_v, high_v, low_v, close_v, vol, trade_count, is_closed, ts_millis))
    return rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--symbol", type=str, default="TEST-BTC")
    parser.add_argument("--timeframe", type=str, default="1m")
    args = parser.parse_args()

    conn = TimescaleConnector()
    if not conn.connect():
        print("DB 연결 실패")
        return
    print("Connected to DB")
    rows = gen_rows(args.rows, symbol=args.symbol, timeframe=args.timeframe)
    t0 = time.time()
    ok = conn.insert_candles_bulk(rows)
    t1 = time.time()
    print(f"insert result: {ok}, time: {t1-t0:.2f}s for {args.rows} rows")
    conn.close()

if __name__ == "__main__":
    main()