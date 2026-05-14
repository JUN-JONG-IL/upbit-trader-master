import sys
import os
import importlib

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("src"))

from datetime import datetime, timezone

# 1. Static 모듈에서 Processor 찾기
processor = None

print("🔍 Processor 찾는 중...\n")

# 시도 1: 11_server.app.static
try:
    static_module = importlib.import_module("11_server.app.static")
    processor = getattr(static_module, "processor", None)
    if processor:
        print(f"✅ [11_server.app.static] Processor 발견!")
        print(f"   타입: {type(processor)}")
        if hasattr(processor, '_running'):
            print(f"   실행 중: {processor._running}")
except Exception as e:
    print(f"❌ [11_server.app.static] 실패: {e}")

# 시도 2: src 루트에서 찾기
if not processor:
    try:
        # src/__init__.py에서 processor 찾기
        import src
        processor = getattr(src, "processor", None)
        if processor:
            print(f"✅ [src] Processor 발견!")
    except Exception as e:
        print(f"❌ [src] 실패: {e}")

# 시도 3: PipelineProcessor 클래스 import
if not processor:
    try:
        processor_module = importlib.import_module("data_01.pipeline.processor")
        PipelineProcessor = getattr(processor_module, "PipelineProcessor", None)
        print(f"⚠️ PipelineProcessor 클래스만 발견 (인스턴스 없음)")
        print(f"   클래스: {PipelineProcessor}")
    except Exception as e:
        print(f"❌ [PipelineProcessor] 실패: {e}")

# 2. 테스트 캔들 생성
test_candle = {
    "symbol": "KRW-BTC",
    "timeframe": "1m",
    "time": datetime.now(timezone.utc),
    "open": 145000000.0,
    "high": 145200000.0,
    "low": 144900000.0,
    "close": 145100000.0,
    "volume": 123.45,
    "quote_volume": 17900000000.0,
    "exchange": "upbit",
    "received_at": datetime.now(timezone.utc).isoformat(),
}

print(f"\n📦 테스트 캔들:")
print(f"  심볼: {test_candle['symbol']} {test_candle['timeframe']}")
print(f"  시간: {test_candle['time']}")
print(f"  Close: {test_candle['close']:,.0f} KRW")

# 3. enqueue 호출 시도
if processor and hasattr(processor, 'enqueue'):
    try:
        print(f"\n🚀 enqueue() 호출 중...")
        result = processor.enqueue(test_candle)
        print(f"✅ enqueue() 성공! 반환값: {result}")
        
        # 통계 확인
        import time
        print(f"⏳ 2초 대기 후 통계 확인...")
        time.sleep(2)
        
        if hasattr(processor, 'get_stats'):
            stats = processor.get_stats()
            print(f"\n📊 Pipeline 통계:")
            for key, value in stats.items():
                print(f"  {key}: {value:,}" if isinstance(value, int) else f"  {key}: {value}")
        else:
            print(f"⚠️ get_stats() 메서드 없음")
        
        # 큐 상태 확인
        if hasattr(processor, '_queue'):
            print(f"\n📦 큐 상태:")
            print(f"  크기: {processor._queue.qsize()}")
        
    except Exception as e:
        print(f"\n❌ enqueue() 실패: {e}")
        import traceback
        traceback.print_exc()
else:
    print("\n" + "="*60)
    print("❌ Processor 인스턴스를 찾을 수 없습니다!")
    print("="*60)
    print("\n💡 해결 방법:")
    print("  1. 먼저 앱을 시작하세요:")
    print("     python src/app/main.py")
    print("\n  2. 앱이 실행된 상태에서 REST API 캔들 수집 로그 확인:")
    print("     [RestCandleCollector] 수집 완료: 100개 캔들")
    print("\n  3. 로그에서 Pipeline 처리 여부 확인:")
    print("     [Pipeline] 누적 수신: XXX개")
    print("\n📌 현재 이 스크립트는 독립 실행이므로 Processor가 없는 것이 정상입니다.")
