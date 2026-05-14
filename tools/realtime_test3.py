import sys, json, time, traceback
from pathlib import Path
import importlib.util

try:
    repo = Path(__file__).resolve().parents[1]
    comp_path = repo / 'src' / '11_server' / 'component' / 'component.py'
    print('COMPONENT_PATH:', comp_path)
    spec = importlib.util.spec_from_file_location('component_mod', str(comp_path))
    mod = importlib.util.module_from_spec(spec)
    # register module before exec to satisfy dataclass internals
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    print('MODULE_LOADED:', hasattr(mod, 'RealtimeManager'))
    mgr = mod.RealtimeManager(codes=[{'market':'KRW-BTC'}], ping_interval=60, redis_enabled=True)
    print('MGR_CREATED')
    mgr.start()
    time.sleep(0.5)
    fake = {'ty':'ticker','cd':'KRW-BTC','tp':123456,'tv':1,'tdt':'20260321','ttm':'170000','ttms':int(time.time()*1000)}
    print('PUTTING_FAKE:', json.dumps(fake, ensure_ascii=False))
    mgr._queue.put(fake)
    time.sleep(1.5)
    mgr.stop()
    print('MGR_STOPPED')
except Exception:
    print('ERROR')
    traceback.print_exc()
