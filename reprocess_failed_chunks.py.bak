#!/usr/bin/env python3
# reprocess_failed_chunks.py
import argparse
import glob
import json
import os
import importlib
import traceback

def main(limit=None):
    base = os.path.abspath(".")
    isol_dir = os.path.join(base, "stager_isolated")
    if not os.path.isdir(isol_dir):
        print("stager_isolated 디렉터리가 없습니다. 작업할 실패 청크가 없습니다.")
        return

    files = sorted(glob.glob(os.path.join(isol_dir, "failed_chunk_*.jsonl")), key=os.path.getmtime)
    if not files:
        print("재처리할 실패 청크 파일 없음")
        return

    if limit:
        files = files[:limit]

    print(f"처리할 파일 수: {len(files)} (디렉터리: {isol_dir})")

    # 1) timescale writer 가져오기 시도
    connector = None
    try:
        ts_mod = importlib.import_module("02_data.timescale.timescale_db")
        get_conn = getattr(ts_mod, "get_timescale_connector", None)
        if callable(get_conn):
            connector = get_conn()
    except Exception as e:
        print("timescale_db 모듈/connector 로드 실패:", e)
        connector = None

    # try to import CandleWriter (preferred)
    CandleWriter = None
    try:
        cw_mod = importlib.import_module("02_data.timescale.operations.candle_writer")
        CandleWriter = getattr(cw_mod, "CandleWriter", None) or getattr(cw_mod, "TimescaleCandleWriter", None)
    except Exception:
        CandleWriter = None

    writer = None
    if CandleWriter is not None and connector is not None:
        try:
            writer = CandleWriter(pool=connector)
            print("CandleWriter 인스턴스 생성 성공:", type(writer).__name__)
        except Exception as e:
            print("CandleWriter 생성 실패, fallback to direct connector.executemany:", e)
            writer = None

    # If no writer, try to get executemany API from connector
    executemany_fn = None
    if writer is None and connector is not None:
        executemany_fn = getattr(connector, "executemany", None)
        if not callable(executemany_fn):
            executemany_fn = None

    # IMPORTANT: If neither writer nor executemany available, abort
    if writer is None and executemany_fn is None:
        print("CandleWriter / connector.executemany 모두 사용 불가 — 수동 조치 필요")
        return

    # Process files one by one
    for fpath in files:
        print("==> 처리 중:", fpath)
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                lines = [line.strip() for line in fh if line.strip()]
            rows = [json.loads(l) for l in lines]

            done = False
            if writer is not None:
                for candidate in ("write_candles", "write", "write_rows", "flush_rows"):
                    fn = getattr(writer, candidate, None)
                    if callable(fn):
                        print(f"writer.{candidate} 호출 (rows={len(rows)}) ...")
                        fn(rows)
                        done = True
                        break
                if not done:
                    fn_any = getattr(writer, "executemany", None) or getattr(writer, "execute", None)
                    if callable(fn_any):
                        print("writer.executemany 또는 execute 호출 시도")
                        fn_any(rows)
                        done = True

            if not done and executemany_fn is not None:
                # NOTE: 사용자가 아래 insert_sql을 candle_writer.py의 실제 SQL로 교체해야 함.
                insert_sql = "<PUT_INSERT_SQL_HERE>"
                if "<PUT_INSERT_SQL_HERE>" in insert_sql:
                    raise RuntimeError("executemany 경로 사용 시 insert_sql 값을 스크립트에 채워 넣어야 합니다 (candle_writer.py 참조)")
                print(f"connector.executemany 호출 (rows={len(rows)}) ...")
                executemany_fn(insert_sql, rows)

            print("성공: 파일 삭제", fpath)
            os.remove(fpath)
        except Exception as e:
            print("오류 발생:", e)
            traceback.print_exc()
            print("이 파일은 유지됩니다:", fpath)
            continue

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="최대 처리할 실패 청크 수 (테스트용)")
    args = ap.parse_args()
    main(limit=args.limit)
