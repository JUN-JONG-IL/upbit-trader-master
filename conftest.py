"""
Repository root conftest.

Stubs the `src` package so that test collection inside src/ subdirectories
doesn't fail due to missing optional dependencies (PyQt5, server, etc.)
in the top-level src/__init__.py.

Only stubs are installed here; the actual test-specific stubs (PyQt5, aiopyupbit,
server.static, etc.) are set up in src/07_scanner/conftest.py.
"""
import sys
import types


def _stub_module(name: str, **attrs) -> types.ModuleType:
    """Register a lightweight stub module if not already present."""
    if name not in sys.modules:
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod
    return sys.modules[name]


# Stub src.component so src/__init__.py can be imported without the full app
_stub_module("src.component",
             RealtimeManager=object, Account=object, Coin=object)
_stub_module("src.prompt", prompt_main=lambda *a, **kw: None)
_stub_module("src.static",
             MIN_TRADE_PRICE=0, FEES=0.0, FIAT="KRW", BASE_TIME_FORMAT="",
             UPBIT_TIME_FORMAT="", STRATEGY_DAILY_FINISH_TIME="",
             EXTERNAL_TIMEOUT=30, INTERNAL_TIMEOUT=5,
             REQUEST_LIMIT=10, PING_INTERVAL=30,
             config=None, log=types.SimpleNamespace(
                 info=lambda *a, **kw: None, warning=lambda *a, **kw: None,
                 error=lambda *a, **kw: None, debug=lambda *a, **kw: None,
             ),
             upbit=None, chart=None, account=None,
             signal_manager=None, signal_queue=None,
             strategy=None, data_manager=None, settings_start=None)
_stub_module("src.userinfo", UserinfoWidget=object, PieChartWidget=object)
_stub_module("src.strategy",
             SignalManager=object,
             VolatilityBreakoutStrategy=object,
             VariousIndicatorStrategy=object)
