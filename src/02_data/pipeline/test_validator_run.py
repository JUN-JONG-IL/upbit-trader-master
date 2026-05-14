import importlib.util, os, sys, asyncio, logging
from datetime import datetime, timezone

# 로깅 파일 설정 (콘솔 + 파일)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("upbit-trader.log", encoding="utf-8")]
)

# repo_root: 이 스크립트(src/02_data/pipeline/test_validator_run.py) 기준으로 상위 3단계가 프로젝트 루트
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
validator_path = os.path.join(repo_root, "src", "02_data", "pipeline", "validator.py")

print("repo_root =", repo_root)
print("validator.py 경로 =", validator_path)

if not os.path.exists(validator_path):
    raise FileNotFoundError(f"validator 파일을 찾을 수 없습니다: {validator_path}")

spec = importlib.util.spec_from_file_location("validator_mod", validator_path)
validator_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator_mod)

CandleValidator = getattr(validator_mod, "CandleValidator")

async def main():
    validator = CandleValidator()
    now = datetime.now(timezone.utc)

    good = {
        "symbol": "KRW-BTC",
        "timeframe": "1m",
        "time": now,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1.23,
        "quote_volume": 123.45,
    }

    bad = {
        "symbol": "KRW-BTC",
        "timeframe": "1m",
        "time": now,
        "open": 100.0,
        "high": 98.0,
        "low": 99.0,
        "close": 98.5,
        "volume": -1.0,
        "quote_volume": -10.0,
    }

    print("=== 정상 캔들 is_valid ===")
    ok, msg = await asyncio.get_event_loop().run_in_executor(None, validator.is_valid, good, None)
    print("is_valid:", ok, "msg:", msg)
    try:
        await asyncio.get_event_loop().run_in_executor(None, validator.validate, good, None)
        print("validate 성공 (정상)")
    except Exception as e:
        print("validate 예외 (정상 케이스):", e)

    print("=== 이상 캔들 is_valid ===")
    ok2, msg2 = await asyncio.get_event_loop().run_in_executor(None, validator.is_valid, bad, None)
    print("is_valid:", ok2, "msg:", msg2)
    try:
        await asyncio.get_event_loop().run_in_executor(None, validator.validate, bad, None)
        print("validate 성공 (이상 케이스) - 예상치 못함")
    except Exception as e:
        print("validate 예외 (이상 케이스):", e)

if __name__ == '__main__':
    asyncio.run(main())
