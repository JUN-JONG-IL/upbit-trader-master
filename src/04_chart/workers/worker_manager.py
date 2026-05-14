"""
Worker manager: small wrapper to manage CandleFetchWorker lifecycle and connections.
"""
from .candle_worker import CandleFetchWorker


def start_worker(parent, on_data_fetched, on_realtime_candle):
    w = CandleFetchWorker(parent)
    if on_data_fetched:
        w.data_fetched.connect(on_data_fetched)
    if on_realtime_candle:
        w.realtime_candle.connect(on_realtime_candle)
    w.start()
    return w


def stop_worker(worker):
    try:
        if worker:
            worker.close()
    except Exception:
        pass