# manual_flush_fixed.py
import psycopg2

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 58529,
    "database": "upbit_trader",
    "user": "postgres",
    "password": "postgres"
}

def manual_flush():
    """수동으로 staging → candles 이동 (스키마 자동 감지)"""
    print("🔄 수동 flush 시작...")
    
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    try:
        # 1. Staging 건수 확인
        cur.execute("SELECT COUNT(*) FROM staging_candles")
        staging_count = cur.fetchone()[0]
        print(f"✅ Staging: {staging_count}개")
        
        if staging_count == 0:
            print("❌ 이동할 데이터 없음")
            return
        
        # 2. Candles 테이블 컬럼 확인
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'candles'
            ORDER BY ordinal_position
        """)
        
        candles_columns = [row[0] for row in cur.fetchall()]
        print(f"✅ Candles 컬럼: {', '.join(candles_columns)}")
        
        # 3. Staging 테이블 컬럼 확인
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'staging_candles'
            ORDER BY ordinal_position
        """)
        
        staging_columns = [row[0] for row in cur.fetchall()]
        print(f"✅ Staging 컬럼: {', '.join(staging_columns)}")
        
        # 4. 공통 컬럼 찾기 (id, symbol_full 제외)
        exclude = {'id', 'symbol_full', 'received_at', 'processed'}
        common_columns = [
            col for col in staging_columns 
            if col in candles_columns and col not in exclude
        ]
        
        print(f"✅ 이동할 컬럼: {', '.join(common_columns)}")
        
        # 5. 동적 SQL 생성
        columns_str = ', '.join(common_columns)
        
        move_sql = f"""
            INSERT INTO candles ({columns_str})
            SELECT {columns_str}
            FROM staging_candles
            ORDER BY time ASC
            LIMIT 1000
            ON CONFLICT (symbol, timeframe, time) 
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume
        """
        
        print(f"\n📝 실행 SQL:")
        print(move_sql[:200] + "...")
        
        cur.execute(move_sql)
        moved = cur.rowcount
        print(f"\n✅ Candles 이동: {moved}개")
        
        # 6. 이동된 데이터 삭제 (상위 1000개)
        if moved > 0:
            delete_sql = """
                DELETE FROM staging_candles
                WHERE ctid IN (
                    SELECT ctid FROM staging_candles
                    ORDER BY time ASC
                    LIMIT %s
                )
            """
            cur.execute(delete_sql, (moved,))
            deleted = cur.rowcount
            print(f"✅ Staging 삭제: {deleted}개")
        
        conn.commit()
        
        # 7. 최종 확인
        cur.execute("SELECT COUNT(*) FROM staging_candles")
        staging_after = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM candles")
        candles_after = cur.fetchone()[0]
        
        print(f"\n🎉 완료!")
        print(f"   Staging: {staging_after}개")
        print(f"   Candles: {candles_after}개")
        
    except Exception as e:
        print(f"\n❌ 에러: {e}")
        conn.rollback()
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    manual_flush()