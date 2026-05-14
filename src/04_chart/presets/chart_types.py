# -*- coding: utf-8 -*-
"""
Chart Types - 차트 타입 정의
다양한 차트 유형 구현
"""
from enum import Enum


class ChartType(Enum):
    """차트 타입 열거형"""
    CANDLESTICK = "candlestick"
    LINE = "line"
    BAR = "bar"
    AREA = "area"
    HEATMAP = "heatmap"
    HEIKIN_ASHI = "heikin_ashi"
    RENKO = "renko"


class ChartTypeConfig:
    """차트 타입별 설정"""
    
    @staticmethod
    def get_config(chart_type: ChartType):
        """
        차트 타입별 설정 가져오기
        
        Args:
            chart_type: 차트 타입
            
        Returns:
            dict: 차트 설정
        """
        configs = {
            ChartType.CANDLESTICK: {
                'name': '캔들스틱',
                'supports_volume': True,
                'supports_indicators': True,
                'min_data_points': 20,
                'recommended_timeframes': ['1m', '5m', '15m', '1h', '1d']
            },
            ChartType.LINE: {
                'name': '라인',
                'supports_volume': False,
                'supports_indicators': True,
                'min_data_points': 10,
                'recommended_timeframes': ['1m', '5m', '15m', '1h', '1d']
            },
            ChartType.BAR: {
                'name': '바',
                'supports_volume': True,
                'supports_indicators': True,
                'min_data_points': 20,
                'recommended_timeframes': ['1m', '5m', '15m', '1h', '1d']
            },
            ChartType.AREA: {
                'name': '에어리어',
                'supports_volume': False,
                'supports_indicators': True,
                'min_data_points': 10,
                'recommended_timeframes': ['1m', '5m', '15m', '1h', '1d']
            },
            ChartType.HEATMAP: {
                'name': '히트맵',
                'supports_volume': False,
                'supports_indicators': False,
                'min_data_points': 100,
                'recommended_timeframes': ['1h', '1d']
            },
            ChartType.HEIKIN_ASHI: {
                'name': 'Heikin-Ashi',
                'supports_volume': True,
                'supports_indicators': True,
                'min_data_points': 20,
                'recommended_timeframes': ['5m', '15m', '1h', '1d']
            },
            ChartType.RENKO: {
                'name': 'Renko',
                'supports_volume': False,
                'supports_indicators': True,
                'min_data_points': 50,
                'recommended_timeframes': ['1h', '1d']
            }
        }
        
        return configs.get(chart_type, configs[ChartType.CANDLESTICK])
    
    @staticmethod
    def validate_data(chart_type: ChartType, data_points: int) -> tuple:
        """
        데이터 검증
        
        Args:
            chart_type: 차트 타입
            data_points: 데이터 포인트 수
            
        Returns:
            tuple: (is_valid, error_message)
        """
        config = ChartTypeConfig.get_config(chart_type)
        min_points = config['min_data_points']
        
        if data_points < min_points:
            return False, f"{config['name']} 차트는 최소 {min_points}개의 데이터 포인트가 필요합니다"
        
        if data_points > 10000:
            return False, f"데이터 포인트는 최대 10,000개까지만 지원됩니다 (현재: {data_points})"
        
        return True, ""


def convert_to_heikin_ashi(candles):
    """
    일반 캔들을 Heikin-Ashi 캔들로 변환
    
    Args:
        candles: list of dict with keys: open, high, low, close
        
    Returns:
        list: Heikin-Ashi 캔들 데이터
    """
    if not candles:
        return []
    
    ha_candles = []
    prev_ha = None
    
    for candle in candles:
        # Heikin-Ashi 계산
        ha_close = (candle['open'] + candle['high'] + candle['low'] + candle['close']) / 4
        
        if prev_ha is None:
            ha_open = (candle['open'] + candle['close']) / 2
        else:
            ha_open = (prev_ha['open'] + prev_ha['close']) / 2
        
        ha_high = max(candle['high'], ha_open, ha_close)
        ha_low = min(candle['low'], ha_open, ha_close)
        
        ha_candle = {
            'timestamp': candle['timestamp'],
            'open': ha_open,
            'high': ha_high,
            'low': ha_low,
            'close': ha_close,
            'volume': candle.get('volume', 0)
        }
        
        ha_candles.append(ha_candle)
        prev_ha = ha_candle
    
    return ha_candles


def convert_to_renko(candles, brick_size=None):
    """
    일반 캔들을 Renko 차트로 변환
    
    Args:
        candles: list of dict with keys: open, high, low, close
        brick_size: 벽돌 크기 (None이면 자동 계산)
        
    Returns:
        list: Renko 벽돌 데이터
    """
    if not candles:
        return []
    
    # 벽돌 크기 자동 계산
    if brick_size is None:
        prices = [c['close'] for c in candles]
        price_range = max(prices) - min(prices)
        brick_size = price_range / 50  # 50개 벽돌 기준
    
    renko_bricks = []
    current_price = candles[0]['close']
    
    for candle in candles:
        price = candle['close']
        
        # 상승 벽돌
        while price >= current_price + brick_size:
            renko_bricks.append({
                'timestamp': candle['timestamp'],
                'open': current_price,
                'close': current_price + brick_size,
                'type': 'up'
            })
            current_price += brick_size
        
        # 하락 벽돌
        while price <= current_price - brick_size:
            renko_bricks.append({
                'timestamp': candle['timestamp'],
                'open': current_price,
                'close': current_price - brick_size,
                'type': 'down'
            })
            current_price -= brick_size
    
    return renko_bricks
