import sys, json, traceback
from pathlib import Path
import importlib.util

try:
    repo = Path(__file__).resolve().parents[1]
    mod_path = repo / 'src' / '02_data' / 'timescale' / 'timescale_redis.py'
    print('MODULE_PATH:', mod_path)
    spec = importlib.util.spec_from_file_location('timescale_redis_mod', str(mod_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    cli = mod.get_client(timeout=2)
    channels = mod.list_pubsub_channels(cli) if cli else []
    print(json.dumps(channels, ensure_ascii=False))
    print('HAS_md:last:KRW-BTC:ticker', 'md:last:KRW-BTC:ticker' in channels)
except Exception:
    traceback.print_exc()
