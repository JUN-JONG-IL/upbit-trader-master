"""
conftest.py for tools/tests/data_01

Adds src/data_01 to sys.path so that test modules can import from
'mongodb', 'redis', 'timescale', etc. without needing numeric-prefixed package names.
"""
import sys
import os

_data_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src", "data_01")
if _data_path not in sys.path:
    sys.path.insert(0, os.path.abspath(_data_path))

