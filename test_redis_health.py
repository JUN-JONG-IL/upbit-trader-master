import sys, os, traceback
# src 폴더를 sys.path 맨 앞에 넣음
src = os.path.abspath(os.path.join(os.getcwd(), "src"))
if src not in sys.path:
    sys.path.insert(0, src)

# 가능한 모듈 후보로 import 시도
candidates = [
    "redis.health_check",
    "src.02_data.redis.health_check",
    "02_data.redis.health_check",
    "src.redis.health_check",
]

for name in candidates:
    try:
        mod = __import__(name, fromlist=['*'])
        print("import 성공:", name, "->", getattr(mod, "__file__", None))
        rh = mod
        break
    except Exception as e:
        print("import 실패:", name, ":", type(e).__name__, str(e))

# rh 변수가 정의되었는지 확인
try:
    print("모듈 파일:", getattr(rh, "__file__", None))
    try:
        print("health_check() ->", rh.health_check())
    except Exception as e:
        print("health_check() 호출 실패:", type(e).__name__, e)
    try:
        print("check_redis_connection() ->", rh.check_redis_connection())
    except Exception as e:
        print("check_redis_connection() 호출 실패:", type(e).__name__, e)
    print("내부 impl_name:", getattr(rh, "_impl_name", "<없음>"))
except NameError:
    print("모듈이 로드되지 않았습니다.")
