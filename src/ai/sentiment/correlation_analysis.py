#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Correlation Analysis Module

감성과 가격 간의 상관관계를 분석합니다.
- Granger Causality Test (인과관계 검정)
- Lead-Lag Analysis (시차 분석)
- 동적 상관계수 계산
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class CorrelationAnalyzer:
    """
    감성-가격 상관관계 분석기
    """
    
    def __init__(self):
        """Initialize Correlation Analyzer"""
        logger.info("Correlation Analyzer initialized")
    
    def granger_causality_test(
        self,
        sentiment_series: np.ndarray,
        price_series: np.ndarray,
        max_lag: int = 7
    ) -> Dict:
        """
        Granger Causality Test
        
        감성이 가격에 선행하는지 검정
        
        Args:
            sentiment_series: 감성 시계열
            price_series: 가격 시계열
            max_lag: 최대 시차
        
        Returns:
            검정 결과
        """
        try:
            from statsmodels.tsa.stattools import grangercausalitytests
            
            # Prepare data
            data = pd.DataFrame({
                'price': price_series,
                'sentiment': sentiment_series
            })
            
            # Remove NaN values
            data = data.dropna()
            
            if len(data) < max_lag + 10:
                logger.warning(f"Insufficient data for Granger test (need at least {max_lag + 10} samples)")
                return {
                    'causality_detected': False,
                    'message': 'Insufficient data',
                    'results': {}
                }
            
            # Run Granger causality test
            # Test if sentiment Granger-causes price
            results = grangercausalitytests(
                data[['price', 'sentiment']],
                maxlag=max_lag,
                verbose=False
            )
            
            # Extract p-values for each lag
            p_values = {}
            for lag in range(1, max_lag + 1):
                # Get F-test p-value
                p_value = results[lag][0]['ssr_ftest'][1]
                p_values[lag] = float(p_value)
            
            # Determine if causality exists (p < 0.05)
            significant_lags = [lag for lag, p in p_values.items() if p < 0.05]
            causality_detected = len(significant_lags) > 0
            
            # Find optimal lag (lowest p-value)
            if significant_lags:
                optimal_lag = min(p_values.items(), key=lambda x: x[1])[0]
                optimal_p_value = p_values[optimal_lag]
            else:
                optimal_lag = None
                optimal_p_value = None
            
            result = {
                'causality_detected': causality_detected,
                'significant_lags': significant_lags,
                'optimal_lag': optimal_lag,
                'optimal_p_value': optimal_p_value,
                'all_p_values': p_values,
                'interpretation': self._interpret_granger_result(causality_detected, optimal_lag)
            }
            
            logger.info(f"Granger causality test completed: causality={causality_detected}")
            
            return result
            
        except ImportError:
            logger.error("statsmodels not installed. Install with: pip install statsmodels")
            return self._fallback_correlation(sentiment_series, price_series)
        except Exception as e:
            logger.error(f"Granger causality test failed: {e}")
            return self._fallback_correlation(sentiment_series, price_series)
    
    def lead_lag_analysis(
        self,
        sentiment_series: np.ndarray,
        price_series: np.ndarray,
        max_lag: int = 10
    ) -> Dict:
        """
        Lead-Lag 분석
        
        최적 시차 탐지
        
        Args:
            sentiment_series: 감성 시계열
            price_series: 가격 시계열
            max_lag: 최대 시차
        
        Returns:
            Lead-lag 분석 결과
        """
        try:
            # Calculate cross-correlation at different lags
            correlations = {}
            
            for lag in range(-max_lag, max_lag + 1):
                if lag < 0:
                    # Sentiment lags price (price leads sentiment)
                    sent = sentiment_series[-lag:]
                    price = price_series[:lag]
                elif lag > 0:
                    # Sentiment leads price
                    sent = sentiment_series[:-lag]
                    price = price_series[lag:]
                else:
                    # No lag
                    sent = sentiment_series
                    price = price_series
                
                # Ensure same length
                min_len = min(len(sent), len(price))
                if min_len < 10:
                    continue
                
                sent = sent[:min_len]
                price = price[:min_len]
                
                # Calculate correlation
                corr = np.corrcoef(sent, price)[0, 1]
                correlations[lag] = float(corr)
            
            # Find optimal lag (maximum absolute correlation)
            optimal_lag = max(correlations.items(), key=lambda x: abs(x[1]))[0]
            optimal_corr = correlations[optimal_lag]
            
            # Interpret
            if optimal_lag > 0:
                interpretation = f"감성이 가격보다 {optimal_lag}시간 선행"
            elif optimal_lag < 0:
                interpretation = f"가격이 감성보다 {abs(optimal_lag)}시간 선행"
            else:
                interpretation = "동시 변동"
            
            result = {
                'optimal_lag': optimal_lag,
                'optimal_correlation': optimal_corr,
                'all_correlations': correlations,
                'interpretation': interpretation,
                'correlation_strength': abs(optimal_corr)
            }
            
            logger.info(f"Lead-lag analysis: optimal lag={optimal_lag}, corr={optimal_corr:.3f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Lead-lag analysis failed: {e}")
            return {
                'optimal_lag': 0,
                'optimal_correlation': 0.0,
                'all_correlations': {},
                'interpretation': 'Analysis failed'
            }
    
    def dynamic_correlation(
        self,
        sentiment_series: np.ndarray,
        price_series: np.ndarray,
        window_size: int = 24
    ) -> Dict:
        """
        동적 상관계수 계산 (시간에 따른 상관관계 변화)
        
        Args:
            sentiment_series: 감성 시계열
            price_series: 가격 시계열
            window_size: 윈도우 크기 (시간 단위)
        
        Returns:
            동적 상관계수 결과
        """
        try:
            n = len(sentiment_series)
            
            if n < window_size:
                logger.warning(f"Insufficient data for dynamic correlation (need at least {window_size} samples)")
                return {
                    'correlations': [],
                    'timestamps': [],
                    'mean_correlation': 0.0
                }
            
            correlations = []
            timestamps = []
            
            # Rolling correlation
            for i in range(window_size, n + 1):
                sent_window = sentiment_series[i - window_size:i]
                price_window = price_series[i - window_size:i]
                
                # Calculate correlation
                corr = np.corrcoef(sent_window, price_window)[0, 1]
                
                correlations.append(float(corr))
                timestamps.append(i)
            
            # Statistics
            mean_corr = np.mean(correlations)
            std_corr = np.std(correlations)
            max_corr = np.max(correlations)
            min_corr = np.min(correlations)
            
            result = {
                'correlations': correlations,
                'timestamps': timestamps,
                'mean_correlation': float(mean_corr),
                'std_correlation': float(std_corr),
                'max_correlation': float(max_corr),
                'min_correlation': float(min_corr),
                'window_size': window_size
            }
            
            logger.info(f"Dynamic correlation: mean={mean_corr:.3f}, std={std_corr:.3f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Dynamic correlation calculation failed: {e}")
            return {
                'correlations': [],
                'timestamps': [],
                'mean_correlation': 0.0
            }
    
    def analyze_correlation(
        self,
        sentiment_series: np.ndarray,
        price_series: np.ndarray,
        max_lag: int = 7
    ) -> Dict:
        """
        종합 상관관계 분석
        
        Args:
            sentiment_series: 감성 시계열
            price_series: 가격 시계열
            max_lag: 최대 시차
        
        Returns:
            종합 분석 결과
        """
        # Granger causality
        granger_result = self.granger_causality_test(sentiment_series, price_series, max_lag)
        
        # Lead-lag
        leadlag_result = self.lead_lag_analysis(sentiment_series, price_series, max_lag)
        
        # Dynamic correlation
        dynamic_result = self.dynamic_correlation(sentiment_series, price_series)
        
        result = {
            'granger_causality': granger_result,
            'lead_lag': leadlag_result,
            'dynamic_correlation': dynamic_result,
            'summary': self._generate_summary(granger_result, leadlag_result, dynamic_result)
        }
        
        return result
    
    def _interpret_granger_result(self, causality: bool, optimal_lag: Optional[int]) -> str:
        """Granger 검정 결과 해석"""
        if causality and optimal_lag:
            return f"감성이 가격 변동에 {optimal_lag}시간 선행하여 영향을 미침 (인과관계 존재)"
        else:
            return "감성과 가격 간 유의미한 인과관계 없음"
    
    def _generate_summary(
        self,
        granger_result: Dict,
        leadlag_result: Dict,
        dynamic_result: Dict
    ) -> str:
        """종합 분석 요약"""
        summary = []
        
        # Granger
        if granger_result.get('causality_detected'):
            summary.append(f"✓ 인과관계 감지 (최적 시차: {granger_result.get('optimal_lag')}시간)")
        else:
            summary.append("✗ 인과관계 미감지")
        
        # Lead-lag
        optimal_lag = leadlag_result.get('optimal_lag', 0)
        if optimal_lag != 0:
            summary.append(f"✓ {leadlag_result.get('interpretation', '')}")
        
        # Dynamic correlation
        mean_corr = dynamic_result.get('mean_correlation', 0.0)
        if abs(mean_corr) > 0.3:
            summary.append(f"✓ 강한 상관관계 (평균: {mean_corr:.3f})")
        elif abs(mean_corr) > 0.1:
            summary.append(f"○ 중간 상관관계 (평균: {mean_corr:.3f})")
        else:
            summary.append(f"✗ 약한 상관관계 (평균: {mean_corr:.3f})")
        
        return " | ".join(summary)
    
    def _fallback_correlation(
        self,
        sentiment_series: np.ndarray,
        price_series: np.ndarray
    ) -> Dict:
        """Fallback: 단순 상관계수"""
        try:
            # Simple Pearson correlation
            corr = np.corrcoef(sentiment_series, price_series)[0, 1]
            
            return {
                'causality_detected': abs(corr) > 0.3,
                'correlation': float(corr),
                'method': 'Pearson (fallback)',
                'interpretation': f"상관계수: {corr:.3f}"
            }
        except:
            return {
                'causality_detected': False,
                'correlation': 0.0,
                'method': 'fallback failed'
            }


def analyze_sentiment_price_correlation(
    sentiment_series: np.ndarray,
    price_series: np.ndarray,
    max_lag: int = 7
) -> Dict:
    """
    Convenience function for sentiment-price correlation analysis
    
    Args:
        sentiment_series: 감성 시계열
        price_series: 가격 시계열
        max_lag: 최대 시차
    
    Returns:
        분석 결과
    """
    analyzer = CorrelationAnalyzer()
    return analyzer.analyze_correlation(sentiment_series, price_series, max_lag)


if __name__ == "__main__":
    """테스트 실행"""
    # Generate synthetic data
    np.random.seed(42)
    
    # Time series (100 hours)
    t = np.arange(100)
    
    # Sentiment with trend and noise
    sentiment = 0.5 * np.sin(t * 0.1) + np.random.randn(100) * 0.2
    
    # Price follows sentiment with 3-hour lag
    lag = 3
    price = np.zeros(100)
    price[lag:] = sentiment[:-lag] * 10 + 100 + np.random.randn(100 - lag) * 2
    price[:lag] = 100
    
    # Analyze
    analyzer = CorrelationAnalyzer()
    result = analyzer.analyze_correlation(sentiment, price, max_lag=10)
    
    print("Correlation Analysis Results:")
    print(f"\nGranger Causality:")
    print(f"  Detected: {result['granger_causality']['causality_detected']}")
    print(f"  Optimal lag: {result['granger_causality'].get('optimal_lag')}")
    
    print(f"\nLead-Lag:")
    print(f"  Optimal lag: {result['lead_lag']['optimal_lag']}")
    print(f"  Correlation: {result['lead_lag']['optimal_correlation']:.3f}")
    print(f"  Interpretation: {result['lead_lag']['interpretation']}")
    
    print(f"\nSummary:")
    print(f"  {result['summary']}")
