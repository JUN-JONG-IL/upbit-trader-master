"""
pytest conftest for scanner.

Sets up sys.path and stubs heavy dependencies (PyQt5, aiopyupbit, server.static)
BEFORE any scanner subpackage is imported.
"""
import sys
import os
import types


# ---------------------------------------------------------------------------
# Minimal Qt base classes so `class X(QThread)` etc. works without PyQt5
# ---------------------------------------------------------------------------

class _QThread:
    """Minimal QThread stub for testing."""
    def __init__(self, parent=None):
        pass
    def start(self): pass
    def quit(self): pass
    def wait(self): pass


class _QObject:
    def __init__(self, parent=None):
        pass


def _pyqt_signal(*args, **kwargs):
    """pyqtSignal stub - returns a no-op descriptor."""
    class _Sig:
        def connect(self, *a, **kw): pass
        def emit(self, *a, **kw): pass
        def disconnect(self, *a, **kw): pass
        def __get__(self, obj, objtype=None):
            return self
    return _Sig()


class _Qt:
    """Qt namespace stub."""
    AlignLeft = 1
    AlignRight = 2
    AlignCenter = 4
    DisplayRole = 0
    UserRole = 256


class _QWidget:
    def __init__(self, parent=None): pass
    def setupUi(self, *a, **kw): pass


class _QDialog(_QWidget):
    def exec_(self): return 0
    def show(self): pass


class _QApplication:
    def __init__(self, *a): pass


def _stub_module(name: str) -> types.ModuleType:
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
    return sys.modules[name]


def _setattr_safe(mod, name, val):
    try:
        setattr(mod, name, val)
    except (TypeError, AttributeError):
        pass


# --- PyQt5 family ---
_pyqt5 = _stub_module("PyQt5")
_qtcore = _stub_module("PyQt5.QtCore")
_qtwidgets = _stub_module("PyQt5.QtWidgets")
_qtgui = _stub_module("PyQt5.QtGui")
_qtchart = _stub_module("PyQt5.QtChart")

for _attr, _val in (
    ("QThread", _QThread), ("QObject", _QObject),
    ("pyqtSignal", _pyqt_signal), ("Qt", _Qt),
    ("QTimer", _QObject),
):
    _setattr_safe(_qtcore, _attr, _val)

for _attr, _val in (
    ("QWidget", _QWidget), ("QDialog", _QDialog),
    ("QApplication", _QApplication),
    ("QTableWidgetItem", _QObject), ("QLabel", _QWidget),
    ("QPushButton", _QWidget), ("QComboBox", _QWidget),
    ("QLineEdit", _QWidget), ("QCheckBox", _QWidget),
    ("QVBoxLayout", _QObject), ("QHBoxLayout", _QObject),
    ("QTableWidget", _QWidget), ("QAbstractItemView", _QWidget),
    ("QHeaderView", _QWidget),
):
    _setattr_safe(_qtwidgets, _attr, _val)

_pyqt5_uic = _stub_module("PyQt5.uic")
_setattr_safe(_pyqt5, "QtCore", _qtcore)
_setattr_safe(_pyqt5, "QtWidgets", _qtwidgets)
_setattr_safe(_pyqt5, "QtGui", _qtgui)
_setattr_safe(_pyqt5, "uic", _pyqt5_uic)

# --- aiopyupbit / talib stubs ---
_stub_module("aiopyupbit")
_stub_module("talib")

# --- server.static stub ---
_server_mod = _stub_module("server")
_static_mod = _stub_module("server.static")
_setattr_safe(_static_mod, "chart", types.SimpleNamespace(coins={}))
_log = types.SimpleNamespace(
    info=lambda *a, **kw: None,
    warning=lambda *a, **kw: None,
    error=lambda *a, **kw: None,
    debug=lambda *a, **kw: None,
)
_setattr_safe(_static_mod, "log", _log)
_setattr_safe(_server_mod, "static", _static_mod)

# --- utils / utils.qt_stub stubs ---
_utils_mod = _stub_module("utils")
_qt_stub_mod = _stub_module("utils.qt_stub")
_setattr_safe(_qt_stub_mod, "QtCore", types.SimpleNamespace(
    QThread=_QThread, pyqtSignal=_pyqt_signal, Qt=_Qt, QTimer=_QObject,
))
_setattr_safe(_qt_stub_mod, "QtWidgets", types.SimpleNamespace(
    QWidget=_QWidget, QDialog=_QDialog,
    QTableWidgetItem=_QObject, QApplication=_QApplication,
    QLabel=_QWidget, QPushButton=_QWidget, QComboBox=_QWidget,
    QLineEdit=_QWidget, QCheckBox=_QWidget,
    QVBoxLayout=_QObject, QHBoxLayout=_QObject,
    QTableWidget=_QWidget, QAbstractItemView=_QWidget,
    QHeaderView=_QWidget,
))
_setattr_safe(_qt_stub_mod, "QtGui", types.SimpleNamespace())
_setattr_safe(_qt_stub_mod, "uic", None)
_setattr_safe(_utils_mod, "qt_stub", _qt_stub_mod)

# --- Add src/scanner to sys.path for direct `engine.*` imports ---
_scanner_root = os.path.abspath(os.path.dirname(__file__))
if _scanner_root not in sys.path:
    sys.path.insert(0, _scanner_root)
