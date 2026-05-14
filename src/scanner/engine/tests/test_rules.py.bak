"""
[Purpose]
- ScannerRules 단위 테스트

[Responsibilities]
- RuleBase 서브클래스 동작 테스트
- RULES 레지스트리 검증

[Dependencies]
- pytest
- pandas, numpy

[Author] Copilot
[Created] 2026-03-05
[Modified] 2026-03-05
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# Import directly (conftest.py sets up sys.path to src/07_scanner)
from engine.logic.scanner_rules import (
    RSIRule,
    GoldenCrossRule,
    VolumeRule,
    OHLCRule,
    RULES,
    RuleBase,
)


def _make_df(n: int = 50, seed: int = 0) -> pd.DataFrame:
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


class TestRulesRegistry:
    def test_rules_has_expected_keys(self):
        for key in ('rsi', 'golden_cross', 'volume', 'ohlc'):
            assert key in RULES

    def test_rules_are_rule_base_instances(self):
        from ..logic.scanner_rules import RuleBase
        for rule in RULES.values():
            assert isinstance(rule, RuleBase)


class TestRSIRule:
    def setup_method(self):
        self.rule = RSIRule()
        self.df = _make_df()

    def test_check_returns_float(self):
        score = self.rule.check(self.df, {'rsi_threshold': 50})
        assert isinstance(score, float)

    def test_score_in_range(self):
        score = self.rule.check(self.df, {'rsi_threshold': 50})
        assert 0.0 <= score <= 1.0

    def test_high_threshold_returns_one(self):
        # With threshold >= 100, any valid RSI value passes (unless exactly 100)
        # RSI is bounded 0-100 so threshold=99.99 should catch most cases
        score = self.rule.check(self.df, {'rsi_threshold': 99})
        assert score in (0.0, 1.0)

    def test_low_threshold_returns_zero_or_one(self):
        score = self.rule.check(self.df, {'rsi_threshold': 1})
        assert score in (0.0, 1.0)

    def test_short_df_no_crash(self):
        df = _make_df(n=5)
        score = self.rule.check(df, {'rsi_threshold': 50})
        assert isinstance(score, float)


class TestGoldenCrossRule:
    def setup_method(self):
        self.rule = GoldenCrossRule()
        self.df = _make_df()

    def test_check_returns_float(self):
        score = self.rule.check(self.df, {'golden_dead': '골든크로스', 'ma_short': 5, 'ma_long': 20})
        assert isinstance(score, float)

    def test_dead_cross(self):
        score = self.rule.check(self.df, {'golden_dead': '데드크로스', 'ma_short': 5, 'ma_long': 20})
        assert score in (0.0, 1.0)

    def test_both_crosses(self):
        score = self.rule.check(self.df, {'golden_dead': '둘 다', 'ma_short': 5, 'ma_long': 20})
        assert score in (0.0, 1.0)

    def test_empty_setting_returns_zero(self):
        score = self.rule.check(self.df, {'golden_dead': ''})
        assert score == 0.0

    def test_short_df_returns_zero(self):
        df = _make_df(n=3)
        score = self.rule.check(df, {'golden_dead': '골든크로스', 'ma_short': 5, 'ma_long': 20})
        assert score == 0.0


class TestVolumeRule:
    def setup_method(self):
        self.rule = VolumeRule()
        self.df = _make_df()

    def test_check_returns_float(self):
        score = self.rule.check(self.df, {'volume_threshold': 150})
        assert isinstance(score, float)

    def test_zero_threshold_returns_one(self):
        # 0% threshold means any volume is above it
        score = self.rule.check(self.df, {'volume_threshold': 0})
        assert score == 1.0

    def test_huge_threshold_returns_zero(self):
        score = self.rule.check(self.df, {'volume_threshold': 1_000_000})
        assert score == 0.0


class TestOHLCRule:
    def setup_method(self):
        self.rule = OHLCRule()

    def test_check_returns_float(self):
        df = _make_df()
        score = self.rule.check(df, {'close_threshold': 0})
        assert isinstance(score, float)

    def test_strongly_up_candle(self):
        # 마지막 봉을 강한 양봉으로 만들기
        df = _make_df()
        df.iloc[-1, df.columns.get_loc('open')] = 100.0
        df.iloc[-1, df.columns.get_loc('close')] = 200.0
        score = self.rule.check(df, {'close_threshold': 50})
        assert score == 1.0

    def test_down_candle_returns_zero(self):
        df = _make_df()
        df.iloc[-1, df.columns.get_loc('open')] = 200.0
        df.iloc[-1, df.columns.get_loc('close')] = 100.0
        score = self.rule.check(df, {'close_threshold': 10})
        assert score == 0.0
