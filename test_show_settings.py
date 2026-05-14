import sys, os, traceback
# repo/src를 import 경로에 추가 (프로젝트 구조에 따라 src가 루트이면 0번째로)
sys.path.insert(0, os.path.abspath("src"))

try:
    # 모듈 자체를 import(모듈 레벨 변수 접근)
    import importlib
    wf_mod = importlib.import_module("app.ui.managers.widget_factory")
    mapping = getattr(wf_mod, "_WIDGET_PATHS", {})
    rel, cls_name = mapping.get("SettingsWidget", ("11_server/ui/settings/widget_server_settings.py","SettingsWidget"))
    print("Using rel path:", rel, "class name:", cls_name)
    # 로드 시도
    cls = wf_mod.WidgetFactory._load_widget_class(rel, cls_name)
    print("Loaded class object:", cls)
    from PyQt5.QtWidgets import QApplication
    app = QApplication([])
    w = cls() if cls else None
    print("Widget instance:", w)
    if w:
        w.show()
        app.exec_()
except Exception:
    traceback.print_exc()
