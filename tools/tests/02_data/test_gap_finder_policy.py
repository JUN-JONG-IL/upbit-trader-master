# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src", "02_data"))

gap_finder = pytest.importorskip("timescale.operations.gap_finder")


def test_lookback_days_from_policy_uses_tf_limit() -> None:
    policy = {"limit_1m": 1440, "limit_1h": 240}
    assert gap_finder._lookback_days_from_policy(policy, "1m") == 1
    assert gap_finder._lookback_days_from_policy(policy, "1h") == 10


def test_detect_all_and_enqueue_uses_collection_policy(monkeypatch) -> None:
    calls = []

    class _FakeFinder:
        def __init__(self, logger=None):
            self.max_lookback_days = 7

        def _load_gap_settings_from_mongo(self) -> None:
            return None

        def detect_and_enqueue(self, symbols=None, interval="1m") -> bool:
            calls.append((interval, self.max_lookback_days, symbols))
            return True

    monkeypatch.setattr(
        gap_finder,
        "_load_collection_policy_from_mongo",
        lambda: {"timeframes": ["1m", "5m"], "limit_1m": 2880, "limit_5m": 2880},
    )
    monkeypatch.setattr(gap_finder, "GapFinder", _FakeFinder)

    assert gap_finder.detect_all_and_enqueue() is True
    assert calls == [("1m", 2, None), ("5m", 10, None)]
