import importlib.util, os, traceback
p = os.path.abspath("src/11_server/ui/settings/widget_server_settings.py")
print("wrapper path:", p, "exists:", os.path.exists(p))
if not os.path.exists(p):
    print("FILE NOT FOUND")
    raise SystemExit(0)
try:
    spec = importlib.util.spec_from_file_location("ws_wrapper", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print("wrapper loaded. has SettingsWidget:", hasattr(mod, "SettingsWidget"), "has create_widget:", hasattr(mod, "create_widget"))
except Exception:
    traceback.print_exc()
