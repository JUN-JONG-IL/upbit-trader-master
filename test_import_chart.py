import importlib.util, traceback
from pathlib import Path
p = Path("src/04_chart/ui/widget_chart.py").resolve()
print("CHECK PATH:", p)
spec = importlib.util.spec_from_file_location("test_chart", str(p))
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    print("module loaded:", getattr(mod, "__file__", None))
    cls = getattr(mod, "ChartWidget", None)
    print("ChartWidget found:", bool(cls))
    if cls:
        try:
            # 안전한 생성 시도 (인자 없는 생성자 가정)
            inst = cls()
            print("ChartWidget instantiated OK")
        except Exception:
            print("ChartWidget instantiation failed:")
            traceback.print_exc()
except Exception:
    print("module load failed:")
    traceback.print_exc()
