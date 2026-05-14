"""
[Purpose]
- 스캔 결과 필터 엔진 - 가격/시총/시간/블랙리스트 등 후처리 필터 적용

[Responsibilities]
- 스캔 결과 리스트에 복합 필터 적용
- 가격 범위 필터
- 시간대 필터 (거래 시간, 주말 제외)
- 즐겨찾기/블랙리스트 필터
- 변동률 필터

[Dependencies]
- scanner.models.scan_result (ScanResult)

[Author] Copilot
[Created] 2026-03-05
[Modified] 2026-03-05
"""
from __future__ import annotations

import re
from datetime import datetime, time
from typing import Any, Dict, List, Optional, Set

from ..models.scan_result import ScanResult


class FilterEngine:
    """
    스캔 결과 후처리 필터 엔진.

    Args:
        settings: 스캐너 설정 딕셔너리

    Attributes:
        settings: 필터 설정

    Examples:
        >>> engine = FilterEngine(settings)
        >>> filtered = engine.apply(results)
    """

    def __init__(self, settings: Dict[str, Any]) -> None:
        self.settings = settings
        self._blacklist: Set[str] = self._parse_blacklist(settings)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(self, results: List[ScanResult]) -> List[ScanResult]:
        """
        전체 필터 파이프라인 적용.

        Args:
            results: 원본 스캔 결과 리스트

        Returns:
            필터 적용된 결과 리스트
        """
        filtered = results
        filtered = self._filter_blacklist(filtered)
        filtered = self._filter_price(filtered)
        filtered = self._filter_time(filtered)
        filtered = self._filter_top_market_cap(filtered)
        filtered = self._filter_top_volume(filtered)
        return filtered

    # ------------------------------------------------------------------
    # Individual filters
    # ------------------------------------------------------------------

    def _filter_blacklist(self, results: List[ScanResult]) -> List[ScanResult]:
        """블랙리스트 종목 제거."""
        if not self._blacklist:
            return results
        return [r for r in results if r.symbol not in self._blacklist]

    def _filter_price(self, results: List[ScanResult]) -> List[ScanResult]:
        """
        가격 범위 필터.

        indicators에 'close' 키가 있을 때만 적용.
        """
        min_price = float(self.settings.get('min_price', 0) or 0)
        max_price = float(self.settings.get('max_price', 0) or 0)
        if min_price == 0 and max_price == 0:
            return results

        filtered = []
        for r in results:
            price = r.indicators.get('close')
            if price is None:
                filtered.append(r)
                continue
            if min_price > 0 and price < min_price:
                continue
            if max_price > 0 and price > max_price:
                continue
            filtered.append(r)
        return filtered

    def _filter_time(self, results: List[ScanResult]) -> List[ScanResult]:
        """
        시간대 필터 (use_time_range 활성화 시 적용).
        """
        if not self.settings.get('use_time_range', False):
            return results

        now = datetime.now().time()
        start_str = self.settings.get('start_time', '09:00')
        end_str = self.settings.get('end_time', '18:00')

        try:
            sh, sm = map(int, start_str.split(':'))
            eh, em = map(int, end_str.split(':'))
            start = time(sh, sm)
            end = time(eh, em)
        except (ValueError, AttributeError):
            return results

        if not (start <= now <= end):
            return []

        if self.settings.get('exclude_weekend', False):
            if datetime.now().weekday() >= 5:  # 토(5), 일(6)
                return []

        return results

    def _filter_top_market_cap(self, results: List[ScanResult]) -> List[ScanResult]:
        """시총 상위 N개 필터 (indicators에 'market_cap' 키가 있을 때만)."""
        if not self.settings.get('top_market_cap', False):
            return results
        count = int(self.settings.get('top_market_cap_count', 50) or 50)
        with_cap = [r for r in results if 'market_cap' in r.indicators]
        without_cap = [r for r in results if 'market_cap' not in r.indicators]
        with_cap.sort(key=lambda r: r.indicators.get('market_cap', 0), reverse=True)
        return with_cap[:count] + without_cap

    def _filter_top_volume(self, results: List[ScanResult]) -> List[ScanResult]:
        """거래량 상위 N개 필터 (indicators에 'volume' 키가 있을 때만)."""
        if not self.settings.get('top_volume', False):
            return results
        count = int(self.settings.get('top_volume_count', 50) or 50)
        with_vol = [r for r in results if 'volume' in r.indicators]
        without_vol = [r for r in results if 'volume' not in r.indicators]
        with_vol.sort(key=lambda r: r.indicators.get('volume', 0), reverse=True)
        return with_vol[:count] + without_vol

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_blacklist(settings: Dict[str, Any]) -> Set[str]:
        """블랙리스트 문자열 파싱 (쉼표/줄바꿈 구분)."""
        raw = settings.get('blacklist', '') or ''
        tokens = re.split(r'[,\n\s]+', raw.strip().upper())
        return {t for t in tokens if t}
