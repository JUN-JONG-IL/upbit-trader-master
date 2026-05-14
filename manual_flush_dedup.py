# manual_flush_dedup.py
import psycopg2

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 58529,
    "database": "upbit_trader",
    "user": "postgres",
    "password": "postgres"
}

def manual_flush_dedup():
    """중복 제거 후 staging → candles 이동"""
    print("🔄 수동 flush 시작 (중복 제거)...")
    
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    try:
        # 1. Staging 건수 확인
        cur.execute("SELECT COUNT(*) FROM staging_candles")
        staging_count = cur.fetchone()[0]
        print(f"✅ Staging 총 건수: {staging_count}개")
        
        if staging_count == 0:
            print("❌ 이동할 데이터 없음")
            return
        
        # 2. 중복 확인
        cur.execute("""
            SELECT symbol, timeframe, time, COUNT(*)
            FROM staging_candles
            GROUP BY symbol, timeframe, time
            HAVING COUNT(*) > 1
            LIMIT 10
        """)
        
        duplicates = cur.fetchall()
        if duplicates:
            print(f"\n⚠️ 중복 발견: {len(duplicates)}개 그룹")
            for dup in duplicates[:5]:
                print(f"   {dup[0]} {dup[1]} {dup[2]} → {dup[3]}개")
        
        # 3. 중복 제거된 데이터를 DISTINCT로 이동
        print(f"\n🔄 중복 제거 후 이동 시작...")
        
        move_sql = """
            INSERT INTO candles (
                symbol, timeframe, exchange, time,
                open, high, low, close,
                volume, quote_volume,
                trade_count, is_complete, seq
            )
            SELECT DISTINCT ON (symbol, timeframe, time)
                symbol, timeframe, exchange, time,
                open, high, low, close,
                volume, quote_volume,
                trade_count, is_complete, seq
            FROM staging_candles
            ORDER BY symbol, timeframe, time, inserted_at DESC
            LIMIT 1000
            ON CONFLICT (symbol, timeframe, time) 
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                quote_volume = EXCLUDED.quote_volume,
                trade_count = EXCLUDED.trade_count,
                is_complete = EXCLUDED.is_complete,
                seq = EXCLUDED.seq
        """
        
        cur.execute(move_sql)
        moved = cur.rowcount
        print(f"✅ Candles 이동: {moved}개 (중복 제거됨)")
        
        # 4. 이동된 데이터 삭제
        if moved > 0:
            delete_sql = """
                DELETE FROM staging_candles
                WHERE (symbol, timeframe, time) IN (
                    SELECT DISTINCT symbol, timeframe, time
                    FROM staging_candles
                    ORDER BY time ASC
                    LIMIT 1000
                )
            """
            cur.execute(delete_sql)
            deleted = cur.rowcount
            print(f"✅ Staging 삭제: {deleted}개")
        
        conn.commit()
        
        # 5. 최종 확인
        cur.execute("SELECT COUNT(*) FROM staging_candles")
        staging_after = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM candles")
        candles_after = cur.fetchone()[0]
        
        # 6. 남은 중복 확인
        cur.execute("""
            SELECT COUNT(*)
            FROM (
                SELECT symbol, timeframe, time, COUNT(*)
                FROM staging_candles
                GROUP BY symbol, timeframe, time
                HAVING COUNT(*) > 1
            ) AS dups
        """)
        remaining_dups = cur.fetchone()[0]
        
        print(f"\n🎉 완료!")
        print(f"   Staging: {staging_after}개 (남은 중복: {remaining_dups}개 그룹)")
        print(f"   Candles: {candles_after}개")
        
        if remaining_dups > 0:
            print(f"\n💡 Tip: 다시 실행하면 남은 중복도 처리됩니다")
        
    except Exception as e:
        print(f"\n❌ 에러: {e}")
        conn.rollback()
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    manual_flush_dedup()