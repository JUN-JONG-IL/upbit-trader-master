# pytest 간단 통합 테스트
# 주의: 실제 TimescaleDB가 동작해야 하며 테스트는 DB에 쓰기를 수행합니다.
import os
import time
from data.timescale_db import TimescaleConnector

def gen_rows(n, symbol="PYTEST-TEST", timeframe="1m", exchange="upbit"):
    import random
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

def test_insert_bulk_small():
    conn = TimescaleConnector()
    assert conn.connect(), "DB에 연결할 수 없습니다"
    rows = gen_rows(50, symbol="PYTEST-TEST")
    ok = conn.insert_candles_bulk(rows)
    conn.close()
    assert ok is True