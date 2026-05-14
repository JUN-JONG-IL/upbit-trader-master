import importlib.util, sys, traceback
from pathlib import Path
p = Path("src/11_server/settings/ui/widget_settings.py").resolve()
print("CHECK PATH:", p)
if not p.exists():
    print("FILE NOT FOUND")
    sys.exit(0)
spec = importlib.util.spec_from_file_location("test_settings_module", str(p))
mod = importlib.util.module_from_spec(spec)
try:
    # 모듈 로드만 시도 (QWidget 인스턴스화는 하지 않음 — QApplication 필요할 수 있음)
    spec.loader.exec_module(mod)
    print("module loaded:", getattr(mod, "__file__", None))
    print("HAS SettingsWidget attribute:", hasattr(mod, "SettingsWidget"))
    # 추가 정보: PyQt / pymongo 사용 여부 플래그 확인
    print("module._HAS_QT:", getattr(mod, "_HAS_QT", "<no attr>"))
    print("module._HAS_PYMONGO:", getattr(mod, "_HAS_PYMONGO", "<no attr>"))
except Exception:
    print("module load failed:")
    traceback.print_exc()
