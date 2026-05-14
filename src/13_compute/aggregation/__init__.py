"""
데이터 집계 모듈

[목적]
틱 데이터를 초/분/시/일/주/월/년 캔들로 롤업하는 집계 로직을 제공합니다.

[주요 클래스]
- TickAggregator   : 틱 → 초 단위 캔들 집계
- OHLCVAggregator  : OHLCV 데이터 상위 단위 롤업
- VolumeAggregator : 거래량 집계
"""

__all__ = ['TickAggregator', 'OHLCVAggregator', 'VolumeAggregator']
