# name=src/utils/qt_stub.py
from __future__ import annotations
import threading
import sys
from typing import Any, Callable, List, Optional

class _BoundSignal:
    def __init__(self):
        self._slots: List[Callable[..., Any]] = []

    def connect(self, fn: Callable[..., Any]) -> None:
        if callable(fn):
            self._slots.append(fn)

    def emit(self, *args: Any, **kwargs: Any) -> None:
        for s in list(self._slots):
            try:
                s(*args, **kwargs)
            except Exception:
                try:
                    print(f"[qt_stub] signal handler error: {s}", file=sys.stderr)
                except Exception:
                    pass

class pyqtSignal:
    def __init__(self, *args, **kwargs):
        self._name: Optional[str] = None

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        attr = f"__pyqt_signal_{self._name}"
        bound = getattr(instance, attr, None)
        if bound is None:
            bound = _BoundSignal()
            setattr(instance, attr, bound)
        return bound

class QThread(threading.Thread):
    def __init__(self, parent: Any = None):
        super().__init__(daemon=True)
        self._running = False
        self._should_quit = threading.Event()
        self._parent = parent

    def start(self) -> None:
        if not self.is_alive():
            self._should_quit.clear()
            self._running = True
            super().start()

    def run(self) -> None:
        # If subclass overrides run(), that code will execute.
        try:
            pass
        finally:
            self._running = False

    def quit(self) -> None:
        self._should_quit.set()
        self._running = False

    def wait(self, msecs: int = 0) -> None:
        try:
            timeout = None if msecs <= 0 else (msecs / 1000.0)
            self.join(timeout)
        except RuntimeError:
            pass

    def isRunning(self) -> bool:
        return self.is_alive()

class QtCore:
    QThread = QThread
    pyqtSignal = pyqtSignal

__all__ = ["QtCore", "QThread", "pyqtSignal"]