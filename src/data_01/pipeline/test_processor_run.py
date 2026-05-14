import importlib.util, os, sys, asyncio, logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler("upbit-trader.log", encoding="utf-8")])

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
processor_path = os.path.join(repo_root, "src", "data_01", "pipeline", "processor.py")

print("processor.py 경로 =", processor_path)
spec = importlib.util.spec_from_file_location("pipeline_processor_test", processor_path)
processor_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(processor_mod)

PipelineProcessor = getattr(processor_mod, "PipelineProcessor")

async def main():
    proc = PipelineProcessor(concurrency=4, publish_to_redis=False, publish_to_kafka=False)
    await proc.start()

    now = datetime.now(timezone.utc)
    good = {
        "symbol": "KRW-BTC", "timeframe": "1m", "time": now,
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
        "volume": 1.0, "quote_volume": 100.0, "trade_count": 1
    }
    bad = {
        "symbol": "KRW-BTC", "timeframe": "1m", "time": now,
        "open": 100.0, "high": 98.0, "low": 99.0, "close": 98.5,
        "volume": -1.0, "quote_volume": -10.0, "trade_count": 0
    }

    print('처리: 정상 캔들')
    await proc.process_candle(good)
    await asyncio.sleep(1)

    print('처리: 이상 캔들')
    await proc.process_candle(bad)
    await asyncio.sleep(1)

    await proc.stop()
    print('테스트 종료')

if __name__ == "__main__":
    asyncio.run(main())

