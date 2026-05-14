#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
우선순위 서비스 모듈

각 심볼의 우선순위 점수를 계산하고 설정을 DB/파일로 관리합니다.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

try:
    from .upbit_data_provider import UpbitDataProvider
except ImportError:
    # Fallback: module loaded directly (not as part of a package, e.g. via importlib shim)
    import importlib.util as _ilu
    import os as _os
    _udp_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "upbit_data_provider.py")
    _udp_spec = _ilu.spec_from_file_location("_upbit_data_provider_direct", _udp_path)
    _udp_mod = _ilu.module_from_spec(_udp_spec)
    _udp_spec.loader.exec_module(_udp_mod)  # type: ignore[union-attr]
    UpbitDataProvider = _udp_mod.UpbitDataProvider

logger = logging.getLogger(__name__)


class PriorityService:
    """우선순위 점수 계산 및 설정 관리 서비스"""

    def __init__(self, db=None) -> None:
        """
        Args:
            db: 데이터베이스 세션 (SQLAlchemy Session 또는 None).
                None이면 외부 데이터 없이 더미 점수를 반환합니다.
        """
        self.db = db
        self.data_provider = UpbitDataProvider()

    # ------------------------------------------------------------------
    # 점수 계산
    # ------------------------------------------------------------------

    async def calculate_volume_score(
        self, symbol: str, exchange: str = "upbit"
    ) -> float:
        """거래량 점수 계산 (0-100)"""
        try:
            volume_data = await self._get_volume_data(symbol, exchange)
            if not volume_data:
                return 0.0
            all_volumes = await self._get_all_volumes(exchange)
            rank = self._calculate_rank(volume_data.get("volume", 0), all_volumes)
            return min(100.0, rank * 100)
        except Exception as exc:
            logger.error("거래량 점수 계산 오류: %s", exc)
            return 0.0

    async def calculate_market_cap_score(
        self, symbol: str, exchange: str = "upbit"
    ) -> float:
        """시가총액 점수 계산 (0-100)"""
        try:
            data = await self._get_market_cap_data(symbol, exchange)
            if not data:
                return 0.0
            all_caps = await self._get_all_market_caps(exchange)
            rank = self._calculate_rank(data.get("market_cap", 0), all_caps)
            return min(100.0, rank * 100)
        except Exception as exc:
            logger.error("시가총액 점수 계산 오류: %s", exc)
            return 0.0

    async def calculate_popularity_score(
        self, symbol: str, exchange: str = "upbit"
    ) -> float:
        """인기 점수 계산 (0-100)"""
        try:
            data = await self._get_popularity_data(symbol, exchange)
            if not data:
                return 0.0
            all_pop = await self._get_all_popularities(exchange)
            rank = self._calculate_rank(data.get("trade_count", 0), all_pop)
            return min(100.0, rank * 100)
        except Exception as exc:
            logger.error("인기 점수 계산 오류: %s", exc)
            return 0.0

    async def calculate_new_listing_score(
        self, symbol: str, exchange: str = "upbit"
    ) -> float:
        """신규 상장 점수 계산 (0-100, 최근 상장일수록 높음)"""
        try:
            data = await self._get_listing_data(symbol, exchange)
            if not data:
                return 0.0
            days_since_listing = data.get("days_since_listing", 365)
            # 30일 이내: 100점, 90일 이내: 50점, 이후: 0점
            if days_since_listing <= 30:
                return 100.0
            elif days_since_listing <= 90:
                return max(0.0, 100.0 - (days_since_listing - 30) * (50.0 / 60))
            return 0.0
        except Exception as exc:
            logger.error("신규 상장 점수 계산 오류: %s", exc)
            return 0.0

    async def calculate_volatility_score(
        self, symbol: str, exchange: str = "upbit"
    ) -> float:
        """변동성 점수 계산 (0-100)"""
        try:
            price_data = await self._get_price_data(symbol, exchange, hours=24)
            if not price_data or len(price_data) < 2:
                return 0.0
            prices = [d["close"] for d in price_data]
            mean_price = sum(prices) / len(prices)
            if mean_price == 0:
                return 0.0
            variance = sum((p - mean_price) ** 2 for p in prices) / len(prices)
            volatility = (variance ** 0.5) / mean_price * 100
            all_vols = await self._get_all_volatilities(exchange)
            rank = self._calculate_rank(volatility, all_vols)
            return min(100.0, rank * 100)
        except Exception as exc:
            logger.error("변동성 점수 계산 오류: %s", exc)
            return 0.0

    async def calculate_price_change_score(
        self, symbol: str, exchange: str = "upbit"
    ) -> float:
        """급등/급락 점수 계산 (0-100, 절대 변동폭 기준)"""
        try:
            data = await self._get_price_change_data(symbol, exchange)
            if not data:
                return 0.0
            change_pct = abs(data.get("change_rate", 0))
            all_changes = await self._get_all_price_changes(exchange)
            rank = self._calculate_rank(change_pct, all_changes)
            return min(100.0, rank * 100)
        except Exception as exc:
            logger.error("급등/급락 점수 계산 오류: %s", exc)
            return 0.0

    async def calculate_pattern_score(
        self, symbol: str, exchange: str = "upbit"
    ) -> float:
        """패턴 감지 점수 계산 (0-100)"""
        try:
            data = await self._get_pattern_data(symbol, exchange)
            if not data:
                return 0.0
            return float(min(100.0, data.get("pattern_strength", 0)))
        except Exception as exc:
            logger.error("패턴 점수 계산 오류: %s", exc)
            return 0.0

    async def calculate_social_score(
        self, symbol: str, exchange: str = "upbit"
    ) -> float:
        """소셜 멘션 점수 계산 (0-100)"""
        try:
            data = await self._get_social_data(symbol, exchange)
            if not data:
                return 0.0
            all_mentions = await self._get_all_social_mentions(exchange)
            rank = self._calculate_rank(data.get("mention_count", 0), all_mentions)
            return min(100.0, rank * 100)
        except Exception as exc:
            logger.error("소셜 점수 계산 오류: %s", exc)
            return 0.0

    async def calculate_all_scores(
        self,
        symbol: str,
        exchange: str = "upbit",
        enabled_items: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """활성화된 모든 항목의 점수를 계산하여 딕셔너리로 반환합니다."""
        score_funcs = {
            "volume": self.calculate_volume_score,
            "market_cap": self.calculate_market_cap_score,
            "popularity": self.calculate_popularity_score,
            "new_listings": self.calculate_new_listing_score,
            "volatility": self.calculate_volatility_score,
            "price_change": self.calculate_price_change_score,
            "pattern_detection": self.calculate_pattern_score,
            "social_mentions": self.calculate_social_score,
        }
        if enabled_items is None:
            enabled_items = list(score_funcs.keys())

        scores: Dict[str, float] = {}
        for key in enabled_items:
            if key in score_funcs:
                scores[key] = await score_funcs[key](symbol, exchange)
        return scores

    def apply_priority_weights(
        self,
        scores: Dict[str, float],
        priority_order: List[str],
        logic_type: str = "OR",
    ) -> float:
        """우선순위 순서와 로직에 따라 가중 점수를 반환합니다.

        Args:
            scores: 항목별 점수 딕셔너리.
            priority_order: 우선순위 순서 (앞일수록 가중치 높음).
            logic_type: 'OR' 또는 'AND'.

        Returns:
            가중 합산 점수 (float).
        """
        if not scores or not priority_order:
            return 0.0

        if logic_type == "AND":
            # AND 모드: 비활성 항목이 하나라도 있으면 0
            if any(scores.get(k, 0) == 0 for k in priority_order):
                return 0.0

        total = 0.0
        for i, key in enumerate(priority_order):
            weight = max(0.1, 1.0 - i * 0.15)
            total += scores.get(key, 0.0) * weight
        return total

    # ------------------------------------------------------------------
    # 순위 계산 헬퍼
    # ------------------------------------------------------------------

    def _calculate_rank(self, value: float, all_values: List[float]) -> float:
        """상대적 순위를 0~1 사이 값으로 반환합니다."""
        if not all_values or value is None:
            return 0.0
        count_higher = sum(1 for v in all_values if v > value)
        return 1.0 - (count_higher / len(all_values))

    # ------------------------------------------------------------------
    # 데이터 조회 (UpbitDataProvider 연동)
    # ------------------------------------------------------------------

    async def _get_volume_data(self, symbol: str, exchange: str) -> dict:
        """실제 24시간 거래량 조회"""
        volume = await self.data_provider.get_volume_24h(symbol)
        if not volume:
            return {}
        return {"volume": volume}

    async def _get_all_volumes(self, exchange: str) -> List[float]:
        """전체 심볼 거래량 조회 (상위 50개)"""
        all_symbols = await self.data_provider.get_all_tickers()
        volumes: List[float] = []
        for sym in all_symbols[:50]:
            try:
                vol = await self.data_provider.get_volume_24h(sym)
                if vol:
                    volumes.append(vol)
            except Exception:
                continue
        return volumes

    async def _get_market_cap_data(self, symbol: str, exchange: str) -> dict:
        """실제 시가총액 조회"""
        cap = await self.data_provider.get_market_cap(symbol)
        if not cap:
            return {}
        return {"market_cap": cap}

    async def _get_all_market_caps(self, exchange: str) -> List[float]:
        """전체 심볼 시가총액 조회 (상위 50개)"""
        all_symbols = await self.data_provider.get_all_tickers()
        caps: List[float] = []
        for sym in all_symbols[:50]:
            try:
                cap = await self.data_provider.get_market_cap(sym)
                if cap:
                    caps.append(cap)
            except Exception:
                continue
        return caps

    async def _get_popularity_data(self, symbol: str, exchange: str) -> dict:
        """인기 데이터 — 24시간 거래량을 거래 건수 대용으로 사용"""
        volume = await self.data_provider.get_volume_24h(symbol)
        if not volume:
            return {}
        return {"trade_count": volume}

    async def _get_all_popularities(self, exchange: str) -> List[float]:
        """전체 심볼 인기 수치 조회"""
        return await self._get_all_volumes(exchange)

    async def _get_listing_data(self, symbol: str, exchange: str) -> dict:
        """신규 상장 데이터 — 조회 가능한 최초 캔들 날짜로 추정"""
        ohlcv = await self.data_provider.get_ohlcv(symbol, interval="day", count=200)
        if not ohlcv:
            return {}
        try:
            from datetime import datetime as dt
            first_date = ohlcv[0].get("date")
            if first_date is None:
                return {}
            if not hasattr(first_date, "date"):
                first_date = dt.fromisoformat(str(first_date))
            days_since = (dt.now() - first_date.replace(tzinfo=None)).days
            return {"days_since_listing": days_since}
        except Exception:
            return {}

    async def _get_price_data(
        self, symbol: str, exchange: str, hours: int = 24
    ) -> List[dict]:
        """실제 가격 데이터 조회"""
        if hours <= 24:
            return await self.data_provider.get_ohlcv(
                symbol, interval="minute60", count=hours
            )
        return await self.data_provider.get_ohlcv(
            symbol, interval="day", count=hours // 24
        )

    async def _get_all_volatilities(self, exchange: str) -> List[float]:
        """전체 심볼 변동성 수치 조회 (성능 최적화: 상위 30개)"""
        all_symbols = await self.data_provider.get_all_tickers()
        vols: List[float] = []
        for sym in all_symbols[:30]:
            try:
                price_data = await self.data_provider.get_ohlcv(
                    sym, interval="minute60", count=24
                )
                if len(price_data) < 2:
                    continue
                prices = [d["close"] for d in price_data if d.get("close")]
                if not prices:
                    continue
                mean = sum(prices) / len(prices)
                if mean == 0:
                    continue
                variance = sum((p - mean) ** 2 for p in prices) / len(prices)
                vols.append((variance ** 0.5) / mean * 100)
            except Exception:
                continue
        return vols

    async def _get_price_change_data(self, symbol: str, exchange: str) -> dict:
        """실제 가격 변화율 계산"""
        rate = await self.data_provider.get_price_change_rate(symbol)
        if rate is None:
            return {}
        return {"change_rate": rate}

    async def _get_all_price_changes(self, exchange: str) -> List[float]:
        """전체 심볼 가격 변화율 조회 (상위 30개)"""
        all_symbols = await self.data_provider.get_all_tickers()
        changes: List[float] = []
        for sym in all_symbols[:30]:
            try:
                rate = await self.data_provider.get_price_change_rate(sym)
                if rate is not None:
                    changes.append(abs(rate))
            except Exception:
                continue
        return changes

    async def _get_pattern_data(self, symbol: str, exchange: str) -> dict:
        """패턴 감지 데이터 — 현재는 빈 딕셔너리 반환 (외부 패턴 분석 모듈 연동 필요)"""
        return {}

    async def _get_social_data(self, symbol: str, exchange: str) -> dict:
        """소셜 멘션 데이터 — 현재는 빈 딕셔너리 반환 (소셜 API 연동 필요)"""
        return {}

    async def _get_all_social_mentions(self, exchange: str) -> List[float]:
        """전체 심볼 소셜 멘션 수치 — 현재는 빈 목록 반환"""
        return []
