"""
conftest.py for tools/tests/01_core

Adds src/01_core to sys.path so that test modules can import from
'events', 'di', etc. without needing numeric-prefixed package names.
"""
import sys
import os

# Add src/01_core so submodules are importable as top-level names
# e.g. `from events import EventBus` instead of `from src.01_core.events import EventBus`
_core_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src", "01_core")
if _core_path not in sys.path:
    sys.path.insert(0, os.path.abspath(_core_path))
