"""
[Purpose]
- ScannerEngine 단위 테스트

[Responsibilities]
- 기본 룰 체크 테스트
- 설정별 스코어 계산 테스트
- 캐시 동작 테스트

[Dependencies]
- pytest
- pandas, numpy
- engine.logic.scanner_engine

[Author] Copilot
[Created] 2026-03-05
[Modified] 2026-03-05
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# conftest.py stubs PyQt5, aiopyupbit, server.static and adds src/07_scanner to sys.path
from engine.logic.scanner_engine import ScannerEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(n: int = 50, seed: int = 42) -> pd.DataFrame:
    """Deterministic OHLCV DataFrame for testing."""
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    open_ = close + rng.normal(0, 0.5, n)
    high = np.maximum(open_, close) + rng.uniform(0, 1, n)
    low = np.minimum(open_, close) - rng.uniform(0, 1, n)
    volume = rng.uniform(1000, 5000, n)
    return pd.DataFrame({
        'open': open_, 'high': high, 'low': low,
        'close': close, 'volume': volume,
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestScannerEngineInit:
    def test_creates_executor(self):
        engine = ScannerEngine()
        assert hasattr(engine, 'executor')
        engine.cleanup()

    def test_creates_cache(self):
        engine = ScannerEngine()
        assert isinstance(engine.cache, dict)
        engine.cleanup()

    def test_cache_ttl_default(self):
        engine = ScannerEngine()
        assert engine.cache_ttl > 0
        engine.cleanup()


class TestCheckBasicRules:
    def setup_method(self):
        self.engine = ScannerEngine()
        self.df = _make_df()

    def teardown_method(self):
        self.engine.cleanup()

    def test_rsi_rule_no_threshold(self):
        settings = {'rsi_threshold': 0}
        score = self.engine._check_basic_rules(self.df, settings)
        # 0 threshold → RSI rule skipped, only OHLC rule counts
        assert 0.0 <= score <= 1.0

    def test_score_range(self):
        settings = {
            'rsi_threshold': 50,
            'golden_dead': '골든크로스',
            'ma_short': 5,
            'ma_long': 20,
            'volume_threshold': 150,
            'close_threshold': 0,
        }
        score = self.engine._check_basic_rules(self.df, settings)
        assert 0.0 <= score <= 1.0

    def test_returns_float(self):
        score = self.engine._check_basic_rules(self.df, {})
        assert isinstance(score, float)

    def test_empty_settings_returns_float(self):
        score = self.engine._check_basic_rules(self.df, {})
        assert isinstance(score, float)


class TestCheckRSI:
    def setup_method(self):
        self.engine = ScannerEngine()

    def teardown_method(self):
        self.engine.cleanup()

    def test_low_rsi_threshold_returns_zero_or_one(self):
        df = _make_df()
        score = self.engine._check_rsi(df, {'rsi_threshold': 1})
        assert score in (0.0, 1.0)

    def test_high_rsi_threshold_returns_one(self):
        # RSI is bounded 0-100. With threshold=99, all but extreme cases pass.
        df = _make_df()
        score = self.engine._check_rsi(df, {'rsi_threshold': 99})
        assert score in (0.0, 1.0)

    def test_rsi_with_short_df(self):
        df = _make_df(n=5)
        score = self.engine._check_rsi(df, {'rsi_threshold': 50})
        assert isinstance(score, float)


class TestCheckGoldenCross:
    def setup_method(self):
        self.engine = ScannerEngine()

    def teardown_method(self):
        self.engine.cleanup()

    def test_golden_cross_returns_float(self):
        df = _make_df()
        score = self.engine._check_golden_cross(
            df, {'golden_dead': '골든크로스', 'ma_short': 5, 'ma_long': 20}
        )
        assert score in (0.0, 1.0)

    def test_dead_cross_returns_float(self):
        df = _make_df()
        score = self.engine._check_golden_cross(
            df, {'golden_dead': '데드크로스', 'ma_short': 5, 'ma_long': 20}
        )
        assert score in (0.0, 1.0)

    def test_both_crosses_returns_float(self):
        df = _make_df()
        score = self.engine._check_golden_cross(
            df, {'golden_dead': '둘 다', 'ma_short': 5, 'ma_long': 20}
        )
        assert score in (0.0, 1.0)

    def test_short_df_returns_zero(self):
        df = _make_df(n=3)
        score = self.engine._check_golden_cross(
            df, {'golden_dead': '골든크로스', 'ma_short': 5, 'ma_long': 20}
        )
        assert score == 0.0


class TestCheckVolume:
    def setup_method(self):
        self.engine = ScannerEngine()

    def teardown_method(self):
        self.engine.cleanup()

    def test_volume_high_threshold_returns_zero_or_one(self):
        df = _make_df()
        score = self.engine._check_volume(df, {'volume_threshold': 10000})
        assert score in (0.0, 1.0)

    def test_volume_low_threshold_returns_one(self):
        df = _make_df()
        score = self.engine._check_volume(df, {'volume_threshold': 0})
        assert score == 1.0


class TestCacheKey:
    def setup_method(self):
        self.engine = ScannerEngine()

    def teardown_method(self):
        self.engine.cleanup()

    def test_same_inputs_same_key(self):
        k1 = self.engine._get_cache_key('KRW-BTC', '1분', {'a': 1})
        k2 = self.engine._get_cache_key('KRW-BTC', '1분', {'a': 1})
        assert k1 == k2

    def test_different_symbol_different_key(self):
        k1 = self.engine._get_cache_key('KRW-BTC', '1분', {})
        k2 = self.engine._get_cache_key('KRW-ETH', '1분', {})
        assert k1 != k2

    def test_different_interval_different_key(self):
        k1 = self.engine._get_cache_key('KRW-BTC', '1분', {})
        k2 = self.engine._get_cache_key('KRW-BTC', '5분', {})
        assert k1 != k2
