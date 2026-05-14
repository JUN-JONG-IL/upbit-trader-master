import psycopg2

conn = psycopg2.connect(
    "postgresql://postgres:postgres@127.0.0.1:58529/upbit_trader"
)

cursor = conn.cursor()

try:
    # 1. staging_candles 현재 데이터 확인
    print("\n=== staging_candles 현재 데이터 (최근 10개) ===\n")
    cursor.execute("""
        SELECT 
            time,
            symbol,
            timeframe,
            exchange,
            open,
            high,
            low,
            close,
            volume,
            processed,
            inserted_at
        FROM staging_candles
        ORDER BY inserted_at DESC
        LIMIT 10;
    """)
    
    rows = cursor.fetchall()
    if not rows:
        print("❌ staging_candles 비어있음")
    else:
        for row in rows:
            print(f"시간: {row[0]} | 심볼: {row[1]} | 타임프레임: {row[2]}")
            print(f"  거래소: {row[3]}")
            print(f"  OHLCV: {row[4]} / {row[5]} / {row[6]} / {row[7]} / {row[8]}")
            print(f"  처리됨: {row[9]} | 삽입시간: {row[10]}\n")
    
    # 2. staging_candles 통계
    print("\n=== staging_candles 통계 ===\n")
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN processed = true THEN 1 END) as processed_count,
            COUNT(CASE WHEN processed = false THEN 1 END) as unprocessed_count
        FROM staging_candles;
    """)
    
    row = cursor.fetchone()
    print(f"총 개수: {row[0]:,}건")
    print(f"처리 완료: {row[1]:,}건")
    print(f"미처리: {row[2]:,}건")
    
    # 3. candles 테이블에 최근 1시간 데이터 확인
    print("\n=== candles 테이블 (최근 1시간) ===\n")
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM candles
        WHERE time >= NOW() - INTERVAL '1 hour';
    """)
    
    recent_count = cursor.fetchone()[0]
    print(f"최근 1시간 캔들: {recent_count:,}건")
    
    # 4. 전체 통계
    print("\n=== 전체 통계 ===\n")
    
    cursor.execute("SELECT COUNT(*) FROM candles;")
    candles_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM staging_candles;")
    staging_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM isolated_candles;")
    isolated_count = cursor.fetchone()[0]
    
    print(f"✅ candles 테이블: {candles_count:,}건")
    print(f"⏳ staging_candles: {staging_count:,}건")
    print(f"❌ isolated_candles: {isolated_count:,}건")
    print(f"📊 총 처리: {candles_count + staging_count + isolated_count:,}건")
    
    # 5. REST API 캔들 추적 (최근 10분)
    print("\n=== REST API 캔들 추적 (최근 10분) ===\n")
    
    # candles 테이블
    cursor.execute("""
        SELECT COUNT(*) 
        FROM candles
        WHERE exchange = 'upbit' 
          AND timeframe = '1m'
          AND time >= NOW() - INTERVAL '10 minutes';
    """)
    rest_in_candles = cursor.fetchone()[0]
    print(f"candles 테이블: {rest_in_candles}건")
    
    # staging_candles
    cursor.execute("""
        SELECT COUNT(*) 
        FROM staging_candles
        WHERE exchange = 'upbit' 
          AND timeframe = '1m'
          AND inserted_at >= NOW() - INTERVAL '10 minutes';
    """)
    rest_in_staging = cursor.fetchone()[0]
    print(f"staging_candles: {rest_in_staging}건")
    
    # isolated_candles (REST API만 - type이 없는 것)
    cursor.execute("""
        SELECT COUNT(*) 
        FROM isolated_candles
        WHERE exchange = 'upbit' 
          AND timeframe = '1m'
          AND isolated_at >= NOW() - INTERVAL '10 minutes'
          AND (raw_data->>'type' IS NULL OR raw_data->>'type' NOT IN ('ticker', 'trade'));
    """)
    rest_in_isolated = cursor.fetchone()[0]
    print(f"isolated_candles: {rest_in_isolated}건")
    
    print(f"\n총 REST API 캔들: {rest_in_candles + rest_in_staging + rest_in_isolated}건")
    
    # 6. 최근 처리된 데이터 시간대 확인
    print("\n=== 최근 처리 시간대 ===\n")
    
    cursor.execute("SELECT MAX(time) FROM candles;")
    max_candle_time = cursor.fetchone()[0]
    print(f"candles 최신 시간: {max_candle_time}")
    
    cursor.execute("SELECT MAX(inserted_at) FROM staging_candles;")
    max_staging_time = cursor.fetchone()[0]
    print(f"staging_candles 최신 삽입: {max_staging_time}")
    
    cursor.execute("SELECT MAX(isolated_at) FROM isolated_candles;")
    max_isolated_time = cursor.fetchone()[0]
    print(f"isolated_candles 최신 격리: {max_isolated_time}")

except Exception as e:
    print(f"\n❌ 에러 발생: {e}")
    import traceback
    traceback.print_exc()

finally:
    cursor.close()
    conn.close()
    print("\n✅ 조회 완료")