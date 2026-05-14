import faulthandler, sys, runpy, traceback

# 5초 ���에 모든 스레드 스택 덤프를 출력합니다.
faulthandler.dump_traceback_later(5, repeat=False)

# src를 모듈 경로에 추가
sys.path.insert(0, "src")

# main.py 실행 (예외가 있으면 전체 traceback 출력)
try:
    runpy.run_path("src/app/main.py", run_name="__main__")
except Exception:
    traceback.print_exc()
