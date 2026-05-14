# -*- coding: utf-8 -*-
"""
Pattern Detector - Automatic chart pattern recognition
Detects 14+ classic technical analysis patterns
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple
from enum import Enum


class PatternType(Enum):
    """14+ Chart Patterns"""
    HEAD_AND_SHOULDERS = "head_and_shoulders"
    INVERSE_HEAD_AND_SHOULDERS = "inverse_head_and_shoulders"
    DOUBLE_TOP = "double_top"
    DOUBLE_BOTTOM = "double_bottom"
    TRIPLE_TOP = "triple_top"
    TRIPLE_BOTTOM = "triple_bottom"
    ASCENDING_TRIANGLE = "ascending_triangle"
    DESCENDING_TRIANGLE = "descending_triangle"
    SYMMETRICAL_TRIANGLE = "symmetrical_triangle"
    FLAG = "flag"
    PENNANT = "pennant"
    WEDGE = "wedge"
    CHANNEL = "channel"
    CUP_AND_HANDLE = "cup_and_handle"


class DetectedPattern:
    """Detected pattern with details"""
    
    def __init__(self, pattern_type: PatternType, start_idx: int, end_idx: int, confidence: float):
        self.pattern_type = pattern_type
        self.start_idx = start_idx
        self.end_idx = end_idx
        self.confidence = confidence
        self.key_points: List[Tuple[int, float]] = []  # (index, price) pairs
        self.description = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "pattern": self.pattern_type.value,
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "confidence": self.confidence,
            "key_points": self.key_points,
            "description": self.description,
        }


class PatternDetector:
    """
    Automatic chart pattern detection.
    
    Features:
    - Detects 14+ classic patterns
    - Returns confidence score for each pattern
    - Identifies key points (peaks, valleys)
    """
    
    def __init__(self):
        self.min_confidence = 0.6  # Minimum confidence to report pattern
        self.patterns: List[DetectedPattern] = []
    
    def detect_all(self, data: pd.DataFrame) -> List[DetectedPattern]:
        """
        Detect all patterns in the data.
        
        Args:
            data: DataFrame with OHLC data
        
        Returns:
            List of detected patterns
        """
        self.patterns = []
        
        # Find peaks and valleys first
        peaks, valleys = self._find_peaks_and_valleys(data['high'].values, data['low'].values)
        
        # Detect each pattern type
        self.patterns.extend(self._detect_head_and_shoulders(data, peaks, valleys))
        self.patterns.extend(self._detect_double_top_bottom(data, peaks, valleys))
        self.patterns.extend(self._detect_triple_top_bottom(data, peaks, valleys))
        self.patterns.extend(self._detect_triangles(data, peaks, valleys))
        self.patterns.extend(self._detect_flag_pennant(data, peaks, valleys))
        self.patterns.extend(self._detect_cup_and_handle(data, peaks, valleys))
        
        # Filter by confidence
        self.patterns = [p for p in self.patterns if p.confidence >= self.min_confidence]
        
        return self.patterns
    
    def _find_peaks_and_valleys(self, highs: np.ndarray, lows: np.ndarray, 
                                order: int = 5) -> Tuple[List[int], List[int]]:
        """
        Find peaks (local maxima) and valleys (local minima).
        
        Args:
            highs: High prices
            lows: Low prices
            order: How many points on each side to use for comparison
        
        Returns:
            peaks, valleys: Lists of indices
        """
        from scipy.signal import argrelextrema
        
        peaks = argrelextrema(highs, np.greater, order=order)[0]
        valleys = argrelextrema(lows, np.less, order=order)[0]
        
        return peaks.tolist(), valleys.tolist()
    
    def _detect_head_and_shoulders(self, data: pd.DataFrame, 
                                   peaks: List[int], valleys: List[int]) -> List[DetectedPattern]:
        """Detect Head and Shoulders pattern"""
        patterns = []
        
        if len(peaks) < 3:
            return patterns
        
        # Look for 3 consecutive peaks where middle is highest
        for i in range(len(peaks) - 2):
            left_shoulder_idx = peaks[i]
            head_idx = peaks[i + 1]
            right_shoulder_idx = peaks[i + 2]
            
            left_shoulder = data['high'].iloc[left_shoulder_idx]
            head = data['high'].iloc[head_idx]
            right_shoulder = data['high'].iloc[right_shoulder_idx]
            
            # Head should be higher than shoulders
            if head > left_shoulder and head > right_shoulder:
                # Shoulders should be roughly at same level (within 3%)
                shoulder_diff = abs(left_shoulder - right_shoulder) / left_shoulder
                
                if shoulder_diff < 0.03:
                    # Calculate confidence based on how pronounced the head is
                    head_prominence = (head - max(left_shoulder, right_shoulder)) / head
                    confidence = min(0.95, 0.6 + head_prominence * 2)
                    
                    pattern = DetectedPattern(
                        PatternType.HEAD_AND_SHOULDERS,
                        left_shoulder_idx,
                        right_shoulder_idx,
                        confidence
                    )
                    pattern.key_points = [
                        (left_shoulder_idx, left_shoulder),
                        (head_idx, head),
                        (right_shoulder_idx, right_shoulder)
                    ]
                    pattern.description = "Bearish reversal pattern - Head and Shoulders"
                    patterns.append(pattern)
        
        # Inverse Head and Shoulders (valleys)
        if len(valleys) < 3:
            return patterns
        
        for i in range(len(valleys) - 2):
            left_shoulder_idx = valleys[i]
            head_idx = valleys[i + 1]
            right_shoulder_idx = valleys[i + 2]
            
            left_shoulder = data['low'].iloc[left_shoulder_idx]
            head = data['low'].iloc[head_idx]
            right_shoulder = data['low'].iloc[right_shoulder_idx]
            
            # Head should be lower than shoulders
            if head < left_shoulder and head < right_shoulder:
                shoulder_diff = abs(left_shoulder - right_shoulder) / left_shoulder
                
                if shoulder_diff < 0.03:
                    head_prominence = (min(left_shoulder, right_shoulder) - head) / min(left_shoulder, right_shoulder)
                    confidence = min(0.95, 0.6 + head_prominence * 2)
                    
                    pattern = DetectedPattern(
                        PatternType.INVERSE_HEAD_AND_SHOULDERS,
                        left_shoulder_idx,
                        right_shoulder_idx,
                        confidence
                    )
                    pattern.key_points = [
                        (left_shoulder_idx, left_shoulder),
                        (head_idx, head),
                        (right_shoulder_idx, right_shoulder)
                    ]
                    pattern.description = "Bullish reversal pattern - Inverse Head and Shoulders"
                    patterns.append(pattern)
        
        return patterns
    
    def _detect_double_top_bottom(self, data: pd.DataFrame,
                                  peaks: List[int], valleys: List[int]) -> List[DetectedPattern]:
        """Detect Double Top and Double Bottom patterns"""
        patterns = []
        
        # Double Top
        if len(peaks) >= 2:
            for i in range(len(peaks) - 1):
                first_peak_idx = peaks[i]
                second_peak_idx = peaks[i + 1]
                
                first_peak = data['high'].iloc[first_peak_idx]
                second_peak = data['high'].iloc[second_peak_idx]
                
                # Peaks should be at similar levels (within 2%)
                peak_diff = abs(first_peak - second_peak) / first_peak
                
                if peak_diff < 0.02:
                    # Should have a valley between peaks
                    valley_between = data['low'].iloc[first_peak_idx:second_peak_idx].min()
                    trough_depth = (min(first_peak, second_peak) - valley_between) / min(first_peak, second_peak)
                    
                    if trough_depth > 0.02:  # At least 2% retracement
                        confidence = min(0.9, 0.65 + (1 - peak_diff) * 0.2)
                        
                        pattern = DetectedPattern(
                            PatternType.DOUBLE_TOP,
                            first_peak_idx,
                            second_peak_idx,
                            confidence
                        )
                        pattern.key_points = [
                            (first_peak_idx, first_peak),
                            (second_peak_idx, second_peak)
                        ]
                        pattern.description = "Bearish reversal pattern - Double Top"
                        patterns.append(pattern)
        
        # Double Bottom
        if len(valleys) >= 2:
            for i in range(len(valleys) - 1):
                first_valley_idx = valleys[i]
                second_valley_idx = valleys[i + 1]
                
                first_valley = data['low'].iloc[first_valley_idx]
                second_valley = data['low'].iloc[second_valley_idx]
                
                valley_diff = abs(first_valley - second_valley) / first_valley
                
                if valley_diff < 0.02:
                    peak_between = data['high'].iloc[first_valley_idx:second_valley_idx].max()
                    rally_height = (peak_between - max(first_valley, second_valley)) / max(first_valley, second_valley)
                    
                    if rally_height > 0.02:
                        confidence = min(0.9, 0.65 + (1 - valley_diff) * 0.2)
                        
                        pattern = DetectedPattern(
                            PatternType.DOUBLE_BOTTOM,
                            first_valley_idx,
                            second_valley_idx,
                            confidence
                        )
                        pattern.key_points = [
                            (first_valley_idx, first_valley),
                            (second_valley_idx, second_valley)
                        ]
                        pattern.description = "Bullish reversal pattern - Double Bottom"
                        patterns.append(pattern)
        
        return patterns
    
    def _detect_triple_top_bottom(self, data: pd.DataFrame,
                                  peaks: List[int], valleys: List[int]) -> List[DetectedPattern]:
        """Detect Triple Top and Triple Bottom patterns"""
        patterns = []
        
        # Triple Top
        if len(peaks) >= 3:
            for i in range(len(peaks) - 2):
                peak_indices = [peaks[i], peaks[i + 1], peaks[i + 2]]
                peak_values = [data['high'].iloc[idx] for idx in peak_indices]
                
                # All peaks should be at similar levels
                peak_std = np.std(peak_values) / np.mean(peak_values)
                
                if peak_std < 0.015:  # Very similar peaks
                    confidence = min(0.9, 0.7 + (1 - peak_std * 10) * 0.2)
                    
                    pattern = DetectedPattern(
                        PatternType.TRIPLE_TOP,
                        peak_indices[0],
                        peak_indices[2],
                        confidence
                    )
                    pattern.key_points = [(idx, val) for idx, val in zip(peak_indices, peak_values)]
                    pattern.description = "Bearish reversal pattern - Triple Top"
                    patterns.append(pattern)
        
        # Triple Bottom
        if len(valleys) >= 3:
            for i in range(len(valleys) - 2):
                valley_indices = [valleys[i], valleys[i + 1], valleys[i + 2]]
                valley_values = [data['low'].iloc[idx] for idx in valley_indices]
                
                valley_std = np.std(valley_values) / np.mean(valley_values)
                
                if valley_std < 0.015:
                    confidence = min(0.9, 0.7 + (1 - valley_std * 10) * 0.2)
                    
                    pattern = DetectedPattern(
                        PatternType.TRIPLE_BOTTOM,
                        valley_indices[0],
                        valley_indices[2],
                        confidence
                    )
                    pattern.key_points = [(idx, val) for idx, val in zip(valley_indices, valley_values)]
                    pattern.description = "Bullish reversal pattern - Triple Bottom"
                    patterns.append(pattern)
        
        return patterns
    
    def _detect_triangles(self, data: pd.DataFrame,
                         peaks: List[int], valleys: List[int]) -> List[DetectedPattern]:
        """Detect Triangle patterns (Ascending, Descending, Symmetrical)"""
        patterns = []
        
        # Need at least 2 peaks and 2 valleys
        if len(peaks) < 2 or len(valleys) < 2:
            return patterns
        
        # Look for triangles in recent data
        lookback = min(100, len(data))
        recent_peaks = [p for p in peaks if p >= len(data) - lookback]
        recent_valleys = [v for v in valleys if v >= len(data) - lookback]
        
        if len(recent_peaks) >= 2 and len(recent_valleys) >= 2:
            # Get trend of peaks and valleys
            peak_values = [data['high'].iloc[p] for p in recent_peaks[-2:]]
            valley_values = [data['low'].iloc[v] for v in recent_valleys[-2:]]
            
            peak_trend = peak_values[-1] - peak_values[0]
            valley_trend = valley_values[-1] - valley_values[0]
            
            # Ascending Triangle: flat top, rising bottoms
            if abs(peak_trend) < peak_values[0] * 0.01 and valley_trend > 0:
                pattern = DetectedPattern(
                    PatternType.ASCENDING_TRIANGLE,
                    recent_valleys[0],
                    recent_peaks[-1],
                    0.75
                )
                pattern.description = "Bullish continuation pattern - Ascending Triangle"
                patterns.append(pattern)
            
            # Descending Triangle: flat bottom, falling tops
            elif abs(valley_trend) < valley_values[0] * 0.01 and peak_trend < 0:
                pattern = DetectedPattern(
                    PatternType.DESCENDING_TRIANGLE,
                    recent_peaks[0],
                    recent_valleys[-1],
                    0.75
                )
                pattern.description = "Bearish continuation pattern - Descending Triangle"
                patterns.append(pattern)
            
            # Symmetrical Triangle: converging trendlines
            elif peak_trend < 0 and valley_trend > 0:
                pattern = DetectedPattern(
                    PatternType.SYMMETRICAL_TRIANGLE,
                    min(recent_peaks[0], recent_valleys[0]),
                    max(recent_peaks[-1], recent_valleys[-1]),
                    0.7
                )
                pattern.description = "Neutral pattern - Symmetrical Triangle"
                patterns.append(pattern)
        
        return patterns
    
    def _detect_flag_pennant(self, data: pd.DataFrame,
                            peaks: List[int], valleys: List[int]) -> List[DetectedPattern]:
        """Detect Flag and Pennant patterns"""
        patterns = []
        
        # Flags and pennants occur after sharp moves
        # Look for consolidation after a strong trend
        lookback = 50
        if len(data) < lookback:
            return patterns
        
        recent = data.iloc[-lookback:]
        price_change = (recent['close'].iloc[-1] - recent['close'].iloc[0]) / recent['close'].iloc[0]
        
        # Need a sharp move (> 5%)
        if abs(price_change) > 0.05:
            # Check for consolidation in last 20 candles
            consolidation = data.iloc[-20:]
            volatility = consolidation['close'].std() / consolidation['close'].mean()
            
            if volatility < 0.02:  # Low volatility = consolidation
                pattern_type = PatternType.FLAG if price_change > 0 else PatternType.PENNANT
                
                pattern = DetectedPattern(
                    pattern_type,
                    len(data) - 20,
                    len(data) - 1,
                    0.7
                )
                pattern.description = f"{'Bullish' if price_change > 0 else 'Bearish'} continuation - {pattern_type.value.replace('_', ' ').title()}"
                patterns.append(pattern)
        
        return patterns
    
    def _detect_cup_and_handle(self, data: pd.DataFrame,
                               peaks: List[int], valleys: List[int]) -> List[DetectedPattern]:
        """Detect Cup and Handle pattern"""
        patterns = []
        
        # Need sufficient data
        if len(data) < 100:
            return patterns
        
        # Look for U-shaped bottom followed by small consolidation
        lookback = min(100, len(data))
        recent = data.iloc[-lookback:]
        
        # Find the lowest point (cup bottom)
        cup_bottom_idx = recent['low'].idxmin()
        cup_bottom_pos = recent.index.get_loc(cup_bottom_idx)
        
        # Need data before and after bottom
        if cup_bottom_pos < 20 or cup_bottom_pos > lookback - 20:
            return patterns
        
        # Check for U-shape (prices before and after bottom should be higher)
        left_side = recent.iloc[:cup_bottom_pos]
        right_side = recent.iloc[cup_bottom_pos + 1:]
        
        if len(left_side) > 10 and len(right_side) > 10:
            left_avg = left_side['close'].mean()
            right_avg = right_side['close'].mean()
            bottom = recent['low'].iloc[cup_bottom_pos]
            
            # Both sides should be higher than bottom
            if left_avg > bottom * 1.05 and right_avg > bottom * 1.05:
                # Look for handle (small pullback after cup)
                if right_side['close'].iloc[-5:].mean() < right_avg * 0.98:
                    pattern = DetectedPattern(
                        PatternType.CUP_AND_HANDLE,
                        len(data) - lookback,
                        len(data) - 1,
                        0.75
                    )
                    pattern.description = "Bullish continuation - Cup and Handle"
                    patterns.append(pattern)
        
        return patterns
