import sys, os, importlib, traceback
# src 경로를 sys.path 맨 앞에 추가 (main.py가 하던 방식과 동일)
src = os.path.abspath(os.path.join(os.getcwd(), "src"))
if src not in sys.path:
    sys.path.insert(0, src)

candidates = [
    "src.data_01.redis.health_check",
    "data_01.redis.health_check",
    "redis.health_check",
]

rh = None
for name in candidates:
    try:
        mod = importlib.import_module(name)
        print("import 성공:", name, "->", getattr(mod, "__file__", None))
        rh = mod
        break
    except Exception as e:
        print("import 실패:", name, ":", type(e).__name__, str(e))

if rh is None:
    print("모듈 로드 실패 - 아래 정보 확인 필요")
else:
    try:
        print("health_check() ->", rh.health_check())
    except Exception as e:
        print("health_check() 호출 실패:", type(e).__name__, e)
    try:
        print("check_redis_connection() ->", rh.check_redis_connection())
    except Exception as e:
        print("check_redis_connection() 호출 실패:", type(e).__name__, e)
    print("impl_name:", getattr(rh, "_impl_name", "<없음>"))

