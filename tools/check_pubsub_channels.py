import os, sys
try:
    import redis
except Exception as e:
    print("ERROR: redis 라이브러리 필요 (pip install redis). 상세:", e, file=sys.stderr)
    sys.exit(2)

url = os.getenv("REDIS_URL")
if url:
    cli = redis.from_url(url, decode_responses=True)
else:
    host = os.getenv("REDIS_HOST", "127.0.0.1")
    port = int(os.getenv("REDIS_PORT", "6379"))
    pwd = os.getenv("REDIS_PASSWORD", None)
    cli = redis.Redis(host=host, port=port, password=pwd, decode_responses=True)

def safe(cmd, *args):
    try:
        return cli.execute_command(cmd, *args)
    except Exception as e:
        return f"ERROR: {e}"

print("PUBSUB CHANNELS market.ticker.*")
print(safe("PUBSUB", "CHANNELS", "market.ticker.*"))
print()
print("PUBSUB CHANNELS ticker:*")
print(safe("PUBSUB", "CHANNELS", "ticker:*"))
print()
# Optional: list ALL active channels (may be large)
print("PUBSUB CHANNELS *  (first 200 items shown if many)")
res = safe("PUBSUB", "CHANNELS", "*")
# normalize output
if isinstance(res, list):
    print(res[:200])
else:
    print(res)
