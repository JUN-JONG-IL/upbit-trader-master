#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Userinfo widget + worker (headless-safe)

- Displays account summary (cash, evaluate, pnl, yield).
- UserinfoWorker updates UI periodically (0.5s) using QThread or threading fallback.
- Headless-safe: if PyQt5 missing, minimal placeholders are used so module import doesn't fail.
"""
from __future__ import annotations

import asyncio as aio
import math
import logging
import threading
from typing import Optional, Any

try:
    from app import static
except ImportError:
    try:
        import importlib as _il
        static = _il.import_module("src.11_server.app").static  # type: ignore[assignment]
    except Exception:
        static = None  # type: ignore[assignment]

# Try to import Ui_Form; provide a safe placeholder if not available
try:
    from .ui_userinfo import Ui_Form
except Exception:
    logging.warning("Ui_Form import failed; using lightweight placeholder Ui_Form.")
    class Ui_Form:
        def setupUi(self, parent):
            class DummyLabel:
                def __init__(self):
                    self._text = ""
                def setText(self, *args, **kwargs):
                    try:
                        self._text = args[0] if args else ""
                    except Exception:
                        pass
                def setStyleSheet(self, *args, **kwargs):
                    pass
            # minimal attributes used by UserinfoWorker
            self.userdata1 = DummyLabel()
            self.userdata2 = DummyLabel()
            self.userdata3 = DummyLabel()
            self.userdata4 = DummyLabel()
            self.userdata5 = DummyLabel()
            self.userdata6 = DummyLabel()

# Qt fallbacks: try importing real PyQt5, otherwise provide safe stubs
_HAS_QT = False
try:
    from PyQt5 import QtGui
    from PyQt5.QtCore import QThread
    from PyQt5.QtWidgets import QWidget
    _HAS_QT = True
except Exception as _e:
    logging.warning("PyQt5 not available: %s -- using headless fallbacks", _e)
    _HAS_QT = False
    class QThread(threading.Thread):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.daemon = True
            self._alive = False
        def run(self):
            # threading.Thread.run will call the target or overridden run
            self._alive = True
            try:
                # If subclass overrides run, this will execute subclass run
                threading.Thread.run(self)
            finally:
                self._alive = False
        def terminate(self):
            self._alive = False
    class QWidget:
        def __init__(self, *args, **kwargs):
            pass
    class QtGui:
        class QCloseEvent:
            pass

logger = logging.getLogger(__name__)


class UserinfoWorker(QThread):
    """
    Worker to periodically update Ui_Form fields from static.account.
    """
    def __init__(self, view: Ui_Form):
        # Initialize parent (QThread or threading.Thread)
        try:
            super().__init__()
        except Exception:
            try:
                QThread.__init__(self)
            except Exception:
                pass
        self.alive = False
        self.view = view

    def run(self) -> None:
        """
        Try to run asynchronous loop; if that fails, fall back to a synchronous loop.
        """
        self.alive = True
        try:
            loop = aio.new_event_loop()
            aio.set_event_loop(loop)
            loop.run_until_complete(self._loop())
        except Exception:
            logger.exception("UserinfoWorker async loop failed; falling back to sync loop")
            self._sync_loop()

    def _sync_loop(self) -> None:
        import time
        while self.alive:
            try:
                self._do_update()
            except Exception:
                logger.exception("UserinfoWorker sync update failed")
            time.sleep(0.5)

    def stop(self) -> None:
        """Request the worker to stop."""
        self.alive = False

    async def _loop(self) -> None:
        while self.alive:
            try:
                await aio.sleep(0.5)
                self._do_update()
            except Exception:
                logger.exception("UserinfoWorker async update failed")
                continue

    def _do_update(self) -> None:
        account = getattr(static, "account", None)
        if account is None:
            return

        # accessors fallback with safe guards
        try:
            cash = float(account.get_cash()) if callable(getattr(account, "get_cash", None)) else float(getattr(account, "cash", 0))
        except Exception:
            cash = 0.0
        try:
            buy_price = float(account.get_buy_price()) if callable(getattr(account, "get_buy_price", None)) else float(getattr(account, "buy_price", 0))
        except Exception:
            buy_price = 0.0
        try:
            eval_price = float(account.get_evaluate_price()) if callable(getattr(account, "get_evaluate_price", None)) else float(getattr(account, "evaluate_price", 0))
        except Exception:
            eval_price = 0.0
        try:
            total_loss = float(account.get_total_loss()) if callable(getattr(account, "get_total_loss", None)) else float(getattr(account, "total_loss", 0))
        except Exception:
            total_loss = 0.0
        try:
            total_yield = float(account.get_total_yield()) if callable(getattr(account, "get_total_yield", None)) else float(getattr(account, "total_yield", 0))
        except Exception:
            total_yield = 0.0

        def safe_set(widget, text):
            try:
                if widget and hasattr(widget, "setText"):
                    widget.setText(text)
            except Exception:
                logger.exception("Failed to set text on widget")

        def safe_style(widget, style):
            try:
                if widget and hasattr(widget, "setStyleSheet"):
                    widget.setStyleSheet(style)
            except Exception:
                pass

        # Update UI fields safely
        safe_set(getattr(self.view, "userdata1", None), f"{int(cash):,}")
        safe_set(getattr(self.view, "userdata2", None), f"{math.ceil(buy_price):,}")
        safe_set(getattr(self.view, "userdata3", None), f"{math.floor(eval_price):,}")
        safe_set(getattr(self.view, "userdata4", None), f"{round(eval_price + cash):,}")
        safe_set(getattr(self.view, "userdata5", None), f"{round(total_loss):,}")
        safe_set(getattr(self.view, "userdata6", None), f"{total_yield:.2f}")

        # 색상 스타일링 (safe)
        try:
            if int(total_loss) < 0:
                safe_style(getattr(self.view, "userdata5", None), "color: #CF304A")
            elif int(total_loss) == 0:
                safe_style(getattr(self.view, "userdata5", None), "color: white")
            else:
                safe_style(getattr(self.view, "userdata5", None), "color: #02C076")
        except Exception:
            pass

        try:
            if total_yield < 0:
                safe_style(getattr(self.view, "userdata6", None), "color: #CF304A")
            elif total_yield == 0:
                safe_style(getattr(self.view, "userdata6", None), "color: white")
            else:
                safe_style(getattr(self.view, "userdata6", None), "color: #02C076")
        except Exception:
            pass


class UserinfoWidget(QWidget):
    def __init__(self, parent=None):
        try:
            super().__init__(parent)
        except Exception:
            try:
                QWidget.__init__(self, parent)
            except Exception:
                pass
        self.view = Ui_Form()
        try:
            self.view.setupUi(self)
        except Exception:
            logger.exception("Ui_Form.setupUi failed; using placeholder view")
        self.uw = UserinfoWorker(self.view)

    def start_worker(self):
        """Convenience to start the worker (useful from UI code)."""
        try:
            if hasattr(self.uw, "start"):
                self.uw.start()
            else:
                # fallback: run run() in a daemon thread
                t = threading.Thread(target=self.uw.run, daemon=True)
                t.start()
        except Exception:
            logger.exception("Failed to start UserinfoWorker")

    def closeEvent(self, a0: Optional[Any] = None) -> None:
        try:
            if self.uw is not None:
                self.uw.stop()
        except Exception:
            pass
        try:
            return super().closeEvent(a0)  # type: ignore
        except Exception:
            return None