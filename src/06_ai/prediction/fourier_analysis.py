#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fourier Analysis Module

푸리에 변환을 사용하여 가격 데이터의 주기성을 분석합니다.
- FFT (Fast Fourier Transform)로 주기성 탐지
- 계절성 분해 (Seasonal Decomposition)
- 자기상관 함수 (ACF/PACF) 분석
"""

import logging
from typing import Dict, List, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)


class FourierAnalyzer:
    """
    푸리에 변환 기반 주기성 분석
    """
    
    def __init__(self, sampling_rate: float = 1.0):
        """
        Initialize Fourier Analyzer
        
        Args:
            sampling_rate: 샘플링 레이트 (예: 1시간 = 1.0, 1일 = 24.0)
        """
        self.sampling_rate = sampling_rate
        logger.info(f"Fourier Analyzer initialized (sampling_rate: {sampling_rate})")
    
    def detect_periodicity(
        self,
        data: np.ndarray,
        top_n: int = 5
    ) -> Dict:
        """
        FFT를 사용한 주기성 탐지
        
        Args:
            data: 시계열 데이터 (1D array)
            top_n: 상위 N개 주기 반환
        
        Returns:
            주기성 정보를 담은 딕셔너리
        """
        try:
            # Remove mean (detrend)
            data_detrended = data - np.mean(data)
            
            # Apply FFT
            fft_values = np.fft.fft(data_detrended)
            fft_freq = np.fft.fftfreq(len(data), 1.0 / self.sampling_rate)
            
            # Get positive frequencies only
            positive_freq_idx = fft_freq > 0
            fft_freq = fft_freq[positive_freq_idx]
            fft_power = np.abs(fft_values[positive_freq_idx]) ** 2
            
            # Find top N frequencies
            top_indices = np.argsort(fft_power)[::-1][:top_n]
            
            # Calculate periods
            periods = []
            for idx in top_indices:
                freq = fft_freq[idx]
                power = fft_power[idx]
                period = 1.0 / freq if freq > 0 else np.inf
                
                periods.append({
                    'frequency': float(freq),
                    'period': float(period),
                    'power': float(power),
                    'period_hours': float(period) if self.sampling_rate == 1.0 else float(period / self.sampling_rate)
                })
            
            # Interpret periods
            interpretations = []
            for p in periods:
                period_hours = p['period_hours']
                if 3 < period_hours < 5:
                    interpretation = "4시간 주기"
                elif 20 < period_hours < 28:
                    interpretation = "1일 주기"
                elif 160 < period_hours < 200:
                    interpretation = "1주 주기"
                elif 670 < period_hours < 770:
                    interpretation = "1개월 주기"
                else:
                    interpretation = f"{period_hours:.1f}시간 주기"
                
                interpretations.append(interpretation)
            
            result = {
                'periods': periods,
                'interpretations': interpretations,
                'dominant_period': periods[0] if periods else None,
                'fft_freq': fft_freq.tolist(),
                'fft_power': fft_power.tolist()
            }
            
            logger.info(f"Periodicity detected: {len(periods)} dominant periods found")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to detect periodicity: {e}")
            return {
                'periods': [],
                'interpretations': [],
                'dominant_period': None
            }
    
    def seasonal_decomposition(
        self,
        data: np.ndarray,
        period: Optional[int] = None
    ) -> Dict:
        """
        계절성 분해 (Seasonal Decomposition)
        
        Args:
            data: 시계열 데이터
            period: 주기 (None인 경우 자동 탐지)
        
        Returns:
            분해된 성분 (추세, 계절성, 잔차)
        """
        try:
            # Auto-detect period if not provided
            if period is None:
                periodicity = self.detect_periodicity(data, top_n=1)
                if periodicity['dominant_period']:
                    period = int(periodicity['dominant_period']['period'])
                else:
                    period = 24  # Default to 24 hours
            
            # Simple moving average for trend
            trend = self._moving_average(data, window=period)
            
            # Detrended data
            detrended = data - trend
            
            # Seasonal component (average pattern over period)
            seasonal = self._extract_seasonal_component(detrended, period)
            
            # Residual
            residual = data - trend - seasonal
            
            result = {
                'trend': trend,
                'seasonal': seasonal,
                'residual': residual,
                'period': period
            }
            
            logger.info(f"Seasonal decomposition completed (period: {period})")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to decompose seasonality: {e}")
            return {
                'trend': np.zeros_like(data),
                'seasonal': np.zeros_like(data),
                'residual': data,
                'period': 0
            }
    
    def autocorrelation(
        self,
        data: np.ndarray,
        max_lag: int = 100
    ) -> Dict:
        """
        자기상관 함수 (ACF) 계산
        
        Args:
            data: 시계열 데이터
            max_lag: 최대 시차
        
        Returns:
            ACF 값들
        """
        try:
            # Normalize data
            data_normalized = (data - np.mean(data)) / (np.std(data) + 1e-10)
            
            # Calculate ACF
            acf_values = []
            for lag in range(max_lag + 1):
                if lag == 0:
                    acf_values.append(1.0)
                else:
                    acf = np.corrcoef(
                        data_normalized[:-lag],
                        data_normalized[lag:]
                    )[0, 1]
                    acf_values.append(acf)
            
            # Find significant lags (above 95% confidence interval)
            confidence_interval = 1.96 / np.sqrt(len(data))
            significant_lags = [
                lag for lag, acf in enumerate(acf_values)
                if abs(acf) > confidence_interval and lag > 0
            ]
            
            result = {
                'acf': acf_values,
                'lags': list(range(max_lag + 1)),
                'significant_lags': significant_lags,
                'confidence_interval': float(confidence_interval)
            }
            
            logger.info(f"ACF calculated: {len(significant_lags)} significant lags")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to calculate ACF: {e}")
            return {
                'acf': [1.0] + [0.0] * max_lag,
                'lags': list(range(max_lag + 1)),
                'significant_lags': []
            }
    
    def partial_autocorrelation(
        self,
        data: np.ndarray,
        max_lag: int = 100
    ) -> Dict:
        """
        편자기상관 함수 (PACF) 계산
        
        Args:
            data: 시계열 데이터
            max_lag: 최대 시차
        
        Returns:
            PACF 값들
        """
        try:
            # Simple PACF calculation using Yule-Walker equations
            acf_result = self.autocorrelation(data, max_lag)
            acf_values = acf_result['acf']
            
            pacf_values = [1.0]  # PACF at lag 0 is always 1
            
            for lag in range(1, min(max_lag + 1, len(acf_values))):
                # Use Durbin-Levinson recursion for PACF
                if lag == 1:
                    pacf_values.append(acf_values[1])
                else:
                    # Simplified calculation
                    numerator = acf_values[lag]
                    denominator = 1.0
                    
                    for j in range(1, lag):
                        numerator -= pacf_values[j] * acf_values[lag - j]
                    
                    pacf = numerator / (denominator + 1e-10)
                    pacf_values.append(pacf)
            
            # Confidence interval
            confidence_interval = 1.96 / np.sqrt(len(data))
            significant_lags = [
                lag for lag, pacf in enumerate(pacf_values)
                if abs(pacf) > confidence_interval and lag > 0
            ]
            
            result = {
                'pacf': pacf_values,
                'lags': list(range(len(pacf_values))),
                'significant_lags': significant_lags,
                'confidence_interval': float(confidence_interval)
            }
            
            logger.info(f"PACF calculated: {len(significant_lags)} significant lags")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to calculate PACF: {e}")
            return {
                'pacf': [1.0] + [0.0] * max_lag,
                'lags': list(range(max_lag + 1)),
                'significant_lags': []
            }
    
    def _moving_average(self, data: np.ndarray, window: int) -> np.ndarray:
        """이동 평균 계산"""
        if window < 1:
            return data
        
        # Pad data at the edges
        padded = np.pad(data, (window // 2, window // 2), mode='edge')
        
        # Calculate moving average
        ma = np.convolve(padded, np.ones(window) / window, mode='valid')
        
        # Ensure same length as input
        if len(ma) > len(data):
            ma = ma[:len(data)]
        elif len(ma) < len(data):
            ma = np.pad(ma, (0, len(data) - len(ma)), mode='edge')
        
        return ma
    
    def _extract_seasonal_component(
        self,
        data: np.ndarray,
        period: int
    ) -> np.ndarray:
        """계절성 성분 추출"""
        n = len(data)
        seasonal = np.zeros(n)
        
        # Calculate average pattern for each position in period
        for i in range(period):
            indices = np.arange(i, n, period)
            if len(indices) > 0:
                avg_value = np.mean(data[indices])
                seasonal[indices] = avg_value
        
        return seasonal


def analyze_time_series_periodicity(
    data: np.ndarray,
    sampling_rate: float = 1.0,
    top_n_periods: int = 5
) -> Dict:
    """
    Convenience function for time series periodicity analysis
    
    Args:
        data: 시계열 데이터
        sampling_rate: 샘플링 레이트
        top_n_periods: 상위 N개 주기
    
    Returns:
        분석 결과
    """
    analyzer = FourierAnalyzer(sampling_rate)
    
    # Detect periodicity
    periodicity = analyzer.detect_periodicity(data, top_n_periods)
    
    # Seasonal decomposition
    decomposition = analyzer.seasonal_decomposition(data)
    
    # ACF/PACF
    acf = analyzer.autocorrelation(data, max_lag=min(100, len(data) // 2))
    
    return {
        'periodicity': periodicity,
        'decomposition': decomposition,
        'acf': acf
    }


if __name__ == "__main__":
    """테스트 실행"""
    # Generate synthetic time series with known periodicities
    np.random.seed(42)
    
    # Time points (hourly for 30 days)
    t = np.arange(0, 24 * 30, 1)
    
    # Generate signal with multiple periodicities
    # Daily cycle (24 hours)
    daily = 10 * np.sin(2 * np.pi * t / 24)
    # Weekly cycle (168 hours)
    weekly = 5 * np.sin(2 * np.pi * t / 168)
    # Trend
    trend = 0.1 * t
    # Noise
    noise = np.random.randn(len(t)) * 2
    
    signal = daily + weekly + trend + noise + 100
    
    # Analyze
    analyzer = FourierAnalyzer(sampling_rate=1.0)
    result = analyzer.detect_periodicity(signal, top_n=3)
    
    print("Fourier Analysis Results:")
    print(f"  Number of dominant periods: {len(result['periods'])}")
    for i, (period, interp) in enumerate(zip(result['periods'], result['interpretations'])):
        print(f"  Period {i+1}: {period['period']:.1f} hours ({interp})")
    
    # Seasonal decomposition
    decomp = analyzer.seasonal_decomposition(signal, period=24)
    print(f"\nSeasonal Decomposition:")
    print(f"  Period: {decomp['period']} hours")
    print(f"  Trend range: [{np.min(decomp['trend']):.2f}, {np.max(decomp['trend']):.2f}]")
