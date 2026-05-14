# tools/timescale/diagnose_timescale.py
# 한글 설명: timescale_db.diagnose_data()를 호출하여 간단 진단 정보를 출력합니다.
from __future__ import annotations
import os, json, sys, importlib.util
from pathlib import Path

# tools/ 디렉토리를 sys.path에 추가하여 _env_loader 접근 가능하게 함
_TOOLS_DIR = str(Path(__file__).parents[1])
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
from _env_loader import load_env
load_env()

# 레포의 src를 import 가능하게 경로 추가 (tools에서 실행할 때 상대경로 보장)
ROOT = str(Path(__file__).parents[2])
SRC = os.path.join(ROOT, "src", "data_01", "timescale", "ui")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# constants.py 로드
_CONST_PATH = os.path.join(ROOT, "src", "01_core", "config", "constants.py")
_spec = importlib.util.spec_from_file_location("_diag_consts", _CONST_PATH)
if _spec and _spec.loader:
    _consts = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_consts)  # type: ignore[union-attr]
else:
    _consts = None

_DEFAULT_TIMESCALE_HOST: str = getattr(_consts, "DEFAULT_TIMESCALE_HOST", "127.0.0.1")
_DEFAULT_TIMESCALE_PORT: int = getattr(_consts, "DEFAULT_TIMESCALE_PORT", 58529)
_DEFAULT_TIMESCALE_USER: str = getattr(_consts, "DEFAULT_TIMESCALE_USER", "postgres")
_DEFAULT_TIMESCALE_DB: str = getattr(_consts, "DEFAULT_TIMESCALE_DB", "upbit_trader")

try:
    import timescale_db  # 모듈이 ui 폴더에 있어야 함
except Exception as e:
    print("timescale_db 모듈 import 실패:", e)
    raise

cfg = {
    "host": os.getenv("TIMESCALE_HOST") or os.getenv("POSTGRES_HOST") or _DEFAULT_TIMESCALE_HOST,
    "port": int(os.getenv("TIMESCALE_PORT") or os.getenv("POSTGRES_PORT") or str(_DEFAULT_TIMESCALE_PORT)),
    "dbname": os.getenv("TIMESCALE_DB") or os.getenv("POSTGRES_DB") or _DEFAULT_TIMESCALE_DB,
    "user": os.getenv("TIMESCALE_USER") or os.getenv("POSTGRES_USER") or _DEFAULT_TIMESCALE_USER,
    "password": os.getenv("TIMESCALE_PASSWORD") or os.getenv("POSTGRES_PASSWORD") or "",
}

print("Timescale DB 연결 정보:", cfg["host"], cfg["port"], cfg["dbname"])
res = timescale_db.diagnose_data(cfg, sample_limit=10)
print(json.dumps(res, ensure_ascii=False, indent=2))
