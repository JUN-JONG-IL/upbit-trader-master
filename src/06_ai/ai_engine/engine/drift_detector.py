#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Drift Detector - 모델 드리프트 감지
데이터 분포 변화 및 모델 성능 저하 탐지
"""

import logging
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DriftReport:
    """드리프트 리포트"""
    timestamp: datetime
    drift_score: float
    is_drifted: bool
    feature_drifts: Dict[str, float]
    performance_drop: float
    recommendation: str


class DriftDetector:
    """
    모델 드리프트 감지기
    
    데이터 분포 변화 및 성능 저하를 감지하여 재학습 필요성 판단
    """
    
    def __init__(self,
                 drift_threshold: float = 0.7,
                 performance_threshold: float = 0.1,
                 window_size: int = 1000):
        """
        Args:
            drift_threshold: 드리프트 임계값 (0~1)
            performance_threshold: 성능 저하 임계값
            window_size: 통계 윈도우 크기
        """
        self.drift_threshold = drift_threshold
        self.performance_threshold = performance_threshold
        self.window_size = window_size
        
        # 베이스라인 통계 (학습 데이터 분포)
        self.baseline_stats: Dict[str, Dict[str, float]] = {}
        
        # 현재 데이터 버퍼
        self.current_buffer: deque = deque(maxlen=window_size)
        
        # 성능 히스토리
        self.performance_history: deque = deque(maxlen=100)
        
        # 드리프트 리포트 히스토리
        self.drift_reports: List[DriftReport] = []
        
        logger.info("Drift Detector 초기화")
    
    def set_baseline(self, features: Dict[str, List[float]]):
        """
        베이스라인 통계 설정 (학습 데이터)
        
        Args:
            features: {feature_name: [values]} 형태의 딕셔너리
        """
        try:
            self.baseline_stats = {}
            
            for feature_name, values in features.items():
                values_array = np.array(values)
                
                self.baseline_stats[feature_name] = {
                    "mean": float(np.mean(values_array)),
                    "std": float(np.std(values_array)),
                    "min": float(np.min(values_array)),
                    "max": float(np.max(values_array)),
                    "median": float(np.median(values_array)),
                    "q25": float(np.percentile(values_array, 25)),
                    "q75": float(np.percentile(values_array, 75))
                }
            
            logger.info(f"베이스라인 설정 완료: {len(self.baseline_stats)}개 특징")
            
        except Exception as e:
            logger.error(f"베이스라인 설정 실패: {e}")
    
    def add_observation(self, features: Dict[str, float], 
                       actual_value: Optional[float] = None,
                       predicted_value: Optional[float] = None):
        """
        새 관측값 추가
        
        Args:
            features: 특징 딕셔너리
            actual_value: 실제 값
            predicted_value: 예측 값
        """
        observation = {
            "timestamp": datetime.now(),
            "features": features,
            "actual": actual_value,
            "predicted": predicted_value
        }
        
        self.current_buffer.append(observation)
        
        # 성능 기록
        if actual_value is not None and predicted_value is not None:
            error = abs(actual_value - predicted_value)
            self.performance_history.append(error)
    
    def detect_drift(self) -> DriftReport:
        """
        드리프트 감지
        
        Returns:
            DriftReport: 드리프트 리포트
        """
        try:
            if not self.baseline_stats or len(self.current_buffer) < 100:
                # 충분한 데이터가 없음
                return DriftReport(
                    timestamp=datetime.now(),
                    drift_score=0.0,
                    is_drifted=False,
                    feature_drifts={},
                    performance_drop=0.0,
                    recommendation="데이터 수집 중"
                )
            
            # 특징별 드리프트 계산
            feature_drifts = self._calculate_feature_drifts()
            
            # 전체 드리프트 점수 (평균)
            drift_score = np.mean(list(feature_drifts.values()))
            
            # 성능 저하 계산
            performance_drop = self._calculate_performance_drop()
            
            # 드리프트 판정
            is_drifted = (
                drift_score > self.drift_threshold or
                performance_drop > self.performance_threshold
            )
            
            # 권장 사항
            if is_drifted:
                if drift_score > 0.8:
                    recommendation = "즉시 재학습 필요 (심각한 드리프트)"
                elif drift_score > 0.7:
                    recommendation = "재학습 권장 (중간 드리프트)"
                else:
                    recommendation = "모니터링 강화 (경미한 드리프트)"
            else:
                recommendation = "정상 - 조치 불필요"
            
            # 리포트 생성
            report = DriftReport(
                timestamp=datetime.now(),
                drift_score=drift_score,
                is_drifted=is_drifted,
                feature_drifts=feature_drifts,
                performance_drop=performance_drop,
                recommendation=recommendation
            )
            
            self.drift_reports.append(report)
            
            if is_drifted:
                logger.warning(
                    f"드리프트 감지! 점수: {drift_score:.3f}, "
                    f"성능 저하: {performance_drop:.3f}"
                )
            
            return report
            
        except Exception as e:
            logger.error(f"드리프트 감지 실패: {e}")
            return DriftReport(
                timestamp=datetime.now(),
                drift_score=0.0,
                is_drifted=False,
                feature_drifts={},
                performance_drop=0.0,
                recommendation="오류 발생"
            )
    
    def _calculate_feature_drifts(self) -> Dict[str, float]:
        """
        특징별 드리프트 점수 계산 (KL Divergence 또는 KS Test)
        
        Returns:
            Dict[str, float]: {feature_name: drift_score}
        """
        feature_drifts = {}
        
        try:
            # 현재 윈도우의 특징 값 추출
            current_features = {}
            for obs in self.current_buffer:
                for feature_name, value in obs["features"].items():
                    if feature_name not in current_features:
                        current_features[feature_name] = []
                    current_features[feature_name].append(value)
            
            # 각 특징별 드리프트 계산
            for feature_name, current_values in current_features.items():
                if feature_name not in self.baseline_stats:
                    continue
                
                baseline = self.baseline_stats[feature_name]
                current_array = np.array(current_values)
                
                # 평균 및 표준편차 차이로 드리프트 추정
                mean_diff = abs(
                    np.mean(current_array) - baseline["mean"]
                ) / (baseline["std"] + 1e-8)
                
                std_diff = abs(
                    np.std(current_array) - baseline["std"]
                ) / (baseline["std"] + 1e-8)
                
                # 드리프트 점수 (0~1로 정규화)
                drift_score = min(1.0, (mean_diff + std_diff) / 2)
                
                feature_drifts[feature_name] = drift_score
            
        except Exception as e:
            logger.error(f"특징 드리프트 계산 실패: {e}")
        
        return feature_drifts
    
    def _calculate_performance_drop(self) -> float:
        """
        성능 저하 계산
        
        Returns:
            float: 성능 저하 비율 (0~1)
        """
        try:
            if len(self.performance_history) < 20:
                return 0.0
            
            errors = list(self.performance_history)
            
            # 초기 에러와 최근 에러 비교
            early_error = np.mean(errors[:20])
            recent_error = np.mean(errors[-20:])
            
            if early_error == 0:
                return 0.0
            
            # 성능 저하 비율
            drop = (recent_error - early_error) / early_error
            
            return max(0.0, min(1.0, drop))
            
        except Exception as e:
            logger.error(f"성능 저하 계산 실패: {e}")
            return 0.0
    
    def get_drift_score(self) -> float:
        """최근 드리프트 점수 반환"""
        if not self.drift_reports:
            return 0.0
        return self.drift_reports[-1].drift_score
    
    def get_latest_report(self) -> Optional[DriftReport]:
        """최신 드리프트 리포트 반환"""
        if not self.drift_reports:
            return None
        return self.drift_reports[-1]
    
    def reset(self):
        """상태 초기화"""
        self.current_buffer.clear()
        self.performance_history.clear()
        logger.info("Drift Detector 상태 초기화")


# 싱글톤 인스턴스
_detector_instance = None


def get_drift_detector() -> DriftDetector:
    """글로벌 Drift Detector 인스턴스 반환"""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = DriftDetector()
    return _detector_instance
