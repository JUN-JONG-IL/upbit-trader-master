# timescale_auto_controller.py
from __future__ import annotations
import logging
from typing import Callable, Optional
from PyQt5.QtCore import QTimer

logger = logging.getLogger("data.timescale.auto_controller")

class AutoController:
    """
    Encapsulates automatic periodic refresh behaviour.
    Keeps logic out of the dialog to reduce size.
    Dialog provides:
      - dsn_builder()
      - on_rows_callback(symbol, tf, rows)
      - get_current_symbol_and_tf()
    """

    def __init__(self, parent, dsn_builder: Callable[[], str], on_rows_cb: Callable, get_current_cb: Callable):
        self.parent = parent
        self._dsn_builder = dsn_builder
        self._on_rows_cb = on_rows_cb
        self._get_current_cb = get_current_cb
        self._timer: Optional[QTimer] = None
        self._running = False
        self.interval_ms = 30_000

    def start(self, interval_ms: int = 30000):
        if self._timer is None:
            self._timer = QTimer(self.parent)
            self._timer.timeout.connect(self._on_tick)
        self.interval_ms = interval_ms
        self._timer.setInterval(self.interval_ms)
        self._timer.start()
        self._running = True
        logger.info("AutoController: started interval %sms", self.interval_ms)

    def stop(self):
        if self._timer is not None and self._timer.isActive():
            self._timer.stop()
        self._running = False
        logger.info("AutoController: stopped")

    def pause(self):
        if self._timer and self._timer.isActive():
            self._timer.stop()
        self._running = False
        logger.info("AutoController: paused")

    def resume(self):
        if self._timer is None:
            self._timer = QTimer(self.parent)
            self._timer.timeout.connect(self._on_tick)
        if not self._timer.isActive():
            self._timer.start()
        self._running = True
        logger.info("AutoController: resumed")
        # immediate tick
        self._on_tick()

    def is_running(self) -> bool:
        return self._running

    def _on_tick(self):
        try:
            symbol, tf = self._get_current_cb()
            if not symbol:
                logger.debug("AutoController: no symbol selected")
                return
            self._fetch_incremental(symbol, tf)
        except Exception:
            logger.exception("AutoController _on_tick failed")

    def _fetch_incremental(self, symbol, tf):
        # build worker here (dialog will attach result handlers)
        dsn = self._dsn_builder()
        from .timescale_worker import timescale_ConnectorWorker  # local import to avoid circular at module load
        w = timescale_ConnectorWorker(dsn)
        # caller expects results via on_rows_cb; worker will call that when rows arrive
        # choose select_since if we had last timestamp attached by dialog; keep simple: ask for recent
        w.result.connect(lambda rows, s=symbol, t=tf: self._on_worker_rows(s, t, rows))
        w.error.connect(lambda e: logger.error("AutoController worker error: %s", e))
        w.run_action("select_recent", symbol, tf, 500)
        # note: dialog should keep list of pending workers if desired

    def _on_worker_rows(self, symbol, tf, rows):
        try:
            if rows:
                self._on_rows_cb(symbol, tf, rows)
        except Exception:
            logger.exception("AutoController _on_worker_rows failed")