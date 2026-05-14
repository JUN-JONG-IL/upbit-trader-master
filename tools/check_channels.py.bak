import importlib, json, traceback
try:
    m = importlib.import_module('src.02_data.timescale.timescale_redis')
    cli = m.get_client(timeout=2)
    channels = m.list_pubsub_channels(cli) if cli else []
    print(json.dumps(channels, ensure_ascii=False))
    print('HAS_md:last:KRW-BTC:ticker', 'md:last:KRW-BTC:ticker' in channels)
except Exception:
    traceback.print_exc()
