#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Auto Retraining Module

데이터 드리프트를 감지하고 자동으로 모델을 재학습합니다.
- PSI (Population Stability Index) 계산
- 데이터 분포 변화 감지
- 자동 재학습 트리거
- 알림 발송 (Slack, 이메일 등)
"""

import logging
from typing import Dict, Optional, Tuple
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)


class AutoRetrainingManager:
    """
    자동 재학습 관리자
    """
    
    def __init__(self, psi_threshold: float = 0.2, accuracy_drop_threshold: float = 0.05):
        """
        Initialize Auto Retraining Manager
        
        Args:
            psi_threshold: PSI 임계값 (0.2 초과 시 재학습)
            accuracy_drop_threshold: 정확도 하락 임계값 (5% 하락 시 재학습)
        """
        self.psi_threshold = psi_threshold
        self.accuracy_drop_threshold = accuracy_drop_threshold
        
        # Historical data
        self.reference_distribution = None
        self.baseline_accuracy = None
        
        # Drift detection history
        self.drift_history = []
        
        logger.info(f"Auto Retraining Manager initialized (PSI threshold: {psi_threshold})")
    
    def calculate_psi(
        self, 
        reference: np.ndarray, 
        current: np.ndarray,
        bins: int = 10
    ) -> float:
        """
        PSI (Population Stability Index) 계산
        
        Args:
            reference: 기준 데이터 (학습 데이터)
            current: 현재 데이터 (실시간 데이터)
            bins: 구간 개수
        
        Returns:
            PSI 값 (0에 가까울수록 분포 유사)
        """
        try:
            # Ensure 1D arrays
            reference = reference.flatten()
            current = current.flatten()
            
            # Define bin edges based on reference distribution
            _, bin_edges = np.histogram(reference, bins=bins)
            
            # Calculate distributions
            ref_counts, _ = np.histogram(reference, bins=bin_edges)
            cur_counts, _ = np.histogram(current, bins=bin_edges)
            
            # Convert to proportions
            ref_props = ref_counts / len(reference)
            cur_props = cur_counts / len(current)
            
            # Add small constant to avoid division by zero
            ref_props = np.where(ref_props == 0, 0.0001, ref_props)
            cur_props = np.where(cur_props == 0, 0.0001, cur_props)
            
            # Calculate PSI
            psi = np.sum((cur_props - ref_props) * np.log(cur_props / ref_props))
            
            logger.info(f"PSI calculated: {psi:.4f}")
            return float(psi)
            
        except Exception as e:
            logger.error(f"Failed to calculate PSI: {e}")
            return 0.0
    
    def detect_drift(
        self,
        reference_data: np.ndarray,
        current_data: np.ndarray
    ) -> Dict:
        """
        데이터 드리프트 감지
        
        Args:
            reference_data: 기준 데이터 (학습 데이터)
            current_data: 현재 데이터 (실시간 데이터)
        
        Returns:
            드리프트 감지 결과
        """
        # Calculate PSI for each feature
        if reference_data.ndim == 1:
            reference_data = reference_data.reshape(-1, 1)
            current_data = current_data.reshape(-1, 1)
        
        n_features = reference_data.shape[1]
        psi_values = []
        
        for i in range(n_features):
            psi = self.calculate_psi(reference_data[:, i], current_data[:, i])
            psi_values.append(psi)
        
        # Calculate average PSI
        avg_psi = np.mean(psi_values)
        max_psi = np.max(psi_values)
        
        # Determine drift severity
        drift_detected = avg_psi > self.psi_threshold
        
        if avg_psi < 0.1:
            severity = "low"
            message = "데이터 분포 안정적"
        elif avg_psi < 0.2:
            severity = "medium"
            message = "데이터 분포 경미한 변화 감지"
        else:
            severity = "high"
            message = "데이터 분포 유의미한 변화 감지 - 재학습 권장"
        
        result = {
            'drift_detected': drift_detected,
            'avg_psi': float(avg_psi),
            'max_psi': float(max_psi),
            'psi_values': [float(p) for p in psi_values],
            'severity': severity,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        
        # Record in history
        self.drift_history.append(result)
        
        logger.info(f"Drift detection: {severity} (PSI: {avg_psi:.4f})")
        
        return result
    
    def check_accuracy_drop(
        self,
        current_accuracy: float,
        baseline_accuracy: Optional[float] = None
    ) -> Dict:
        """
        모델 정확도 하락 확인
        
        Args:
            current_accuracy: 현재 정확도
            baseline_accuracy: 기준 정확도 (None인 경우 저장된 값 사용)
        
        Returns:
            정확도 하락 감지 결과
        """
        if baseline_accuracy is None:
            baseline_accuracy = self.baseline_accuracy
        
        if baseline_accuracy is None:
            logger.warning("Baseline accuracy not set")
            return {
                'drop_detected': False,
                'message': '기준 정확도 미설정'
            }
        
        # Calculate drop percentage
        drop = baseline_accuracy - current_accuracy
        drop_percentage = drop / baseline_accuracy
        
        drop_detected = drop_percentage > self.accuracy_drop_threshold
        
        if drop_detected:
            severity = "high" if drop_percentage > 0.1 else "medium"
            message = f"정확도 {drop_percentage*100:.1f}% 하락 감지 - 재학습 권장"
        else:
            severity = "low"
            message = "정확도 안정적"
        
        result = {
            'drop_detected': drop_detected,
            'baseline_accuracy': float(baseline_accuracy),
            'current_accuracy': float(current_accuracy),
            'drop': float(drop),
            'drop_percentage': float(drop_percentage),
            'severity': severity,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info(f"Accuracy check: {message}")
        
        return result
    
    def should_retrain(
        self,
        reference_data: np.ndarray,
        current_data: np.ndarray,
        current_accuracy: Optional[float] = None
    ) -> Tuple[bool, Dict]:
        """
        재학습 필요 여부 판단
        
        Args:
            reference_data: 기준 데이터
            current_data: 현재 데이터
            current_accuracy: 현재 정확도 (선택사항)
        
        Returns:
            (재학습 필요 여부, 상세 정보)
        """
        # Check drift
        drift_result = self.detect_drift(reference_data, current_data)
        
        # Check accuracy if provided
        accuracy_result = None
        if current_accuracy is not None:
            accuracy_result = self.check_accuracy_drop(current_accuracy)
        
        # Determine if retraining is needed
        should_retrain = drift_result['drift_detected']
        
        if accuracy_result and accuracy_result['drop_detected']:
            should_retrain = True
        
        # Compile reasons
        reasons = []
        if drift_result['drift_detected']:
            reasons.append(f"데이터 드리프트 감지 (PSI: {drift_result['avg_psi']:.4f})")
        if accuracy_result and accuracy_result['drop_detected']:
            reasons.append(f"정확도 하락 ({accuracy_result['drop_percentage']*100:.1f}%)")
        
        result = {
            'should_retrain': should_retrain,
            'reasons': reasons,
            'drift_result': drift_result,
            'accuracy_result': accuracy_result,
            'timestamp': datetime.now().isoformat()
        }
        
        if should_retrain:
            logger.warning(f"Retraining recommended: {', '.join(reasons)}")
        else:
            logger.info("Model stable - no retraining needed")
        
        return should_retrain, result
    
    def set_baseline(self, reference_data: np.ndarray, baseline_accuracy: float):
        """
        기준 데이터 및 정확도 설정
        
        Args:
            reference_data: 기준 데이터
            baseline_accuracy: 기준 정확도
        """
        self.reference_distribution = reference_data
        self.baseline_accuracy = baseline_accuracy
        logger.info(f"Baseline set: accuracy={baseline_accuracy:.4f}")
    
    def send_alert(self, message: str, alert_type: str = "info"):
        """
        알림 발송
        
        Args:
            message: 알림 메시지
            alert_type: 알림 타입 ("info", "warning", "error")
        """
        # TODO: Implement actual alert sending (Slack, email, etc.)
        logger.info(f"Alert [{alert_type}]: {message}")
        
        # Example: Send to Slack
        # self._send_slack_message(message, alert_type)
    
    def get_drift_history(self, last_n: int = 10) -> list:
        """
        드리프트 감지 히스토리 반환
        
        Args:
            last_n: 마지막 N개 이벤트
        
        Returns:
            드리프트 히스토리 리스트
        """
        return self.drift_history[-last_n:]


if __name__ == "__main__":
    """테스트 실행"""
    # Generate synthetic data
    np.random.seed(42)
    
    # Reference data (normal distribution)
    reference = np.random.normal(0, 1, (1000, 3))
    
    # Current data (slightly shifted distribution - simulating drift)
    current_no_drift = np.random.normal(0, 1, (500, 3))
    current_with_drift = np.random.normal(0.5, 1.2, (500, 3))  # Mean and std shifted
    
    # Create manager
    manager = AutoRetrainingManager(psi_threshold=0.2)
    manager.set_baseline(reference, baseline_accuracy=0.92)
    
    print("Test 1: No drift")
    should_retrain, result = manager.should_retrain(reference, current_no_drift)
    print(f"  Should retrain: {should_retrain}")
    print(f"  Average PSI: {result['drift_result']['avg_psi']:.4f}")
    
    print("\nTest 2: With drift")
    should_retrain, result = manager.should_retrain(reference, current_with_drift)
    print(f"  Should retrain: {should_retrain}")
    print(f"  Average PSI: {result['drift_result']['avg_psi']:.4f}")
    print(f"  Reasons: {result['reasons']}")
    
    print("\nTest 3: Accuracy drop")
    accuracy_result = manager.check_accuracy_drop(current_accuracy=0.85)
    print(f"  Drop detected: {accuracy_result['drop_detected']}")
    print(f"  Drop percentage: {accuracy_result['drop_percentage']*100:.1f}%")
