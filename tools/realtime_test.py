import importlib, time, json, traceback
try:
    comp = importlib.import_module('src.11_server.component.component')
    print('Imported RealtimeManager OK')
    mgr = comp.RealtimeManager(codes=[{'market':'KRW-BTC'}], ping_interval=60, redis_enabled=True)
    print('Manager created, starting...')
    mgr.start()
    time.sleep(0.5)
    fake = {'ty':'ticker','cd':'KRW-BTC','tp':123456,'tv':1,'tdt':'20260321','ttm':'170000','ttms':int(time.time()*1000)}
    print('Putting fake message to queue:', json.dumps(fake, ensure_ascii=False))
    mgr._queue.put(fake)
    time.sleep(1.5)
    mgr.stop()
    print('Manager stopped')
except Exception:
    print('ERROR', traceback.format_exc())
