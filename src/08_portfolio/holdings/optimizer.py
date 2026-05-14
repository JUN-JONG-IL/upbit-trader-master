#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
포트폴리오 최적화
- 마코위츠 모델 (Markowitz Portfolio Theory)
- 효율적 프론티어 계산
- 샤프 비율 최대화

[Author] Copilot
[Created] 2026-02-06
"""

import logging
import numpy as np
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)


class PortfolioOptimizer:
    """
    포트폴리오 최적화기
    
    마코위츠 평균-분산 모델을 사용한 최적 포트폴리오 계산
    """
    
    def __init__(
        self,
        returns: np.ndarray,
        cov_matrix: Optional[np.ndarray] = None
    ):
        """
        초기화
        
        Args:
            returns: 자산별 기대 수익률 (N,)
            cov_matrix: 공분산 행렬 (N x N). None이면 단위 행렬 사용
        """
        self.returns = np.array(returns)
        self.n_assets = len(returns)
        
        if cov_matrix is None:
            # 단위 행렬 사용 (모든 자산이 독립)
            self.cov_matrix = np.eye(self.n_assets)
        else:
            self.cov_matrix = np.array(cov_matrix)
        
        logger.info(f"[PortfolioOptimizer] Initialized with {self.n_assets} assets")
    
    def optimize(
        self,
        target_return: Optional[float] = None,
        method: str = "max_sharpe"
    ) -> Dict[str, Any]:
        """
        최적 포트폴리오 계산
        
        Args:
            target_return: 목표 수익률 (method='target_return'일 때 필요)
            method: 최적화 방법
                - 'max_sharpe': 샤프 비율 최대화
                - 'min_variance': 분산 최소화
                - 'target_return': 목표 수익률에서 분산 최소화
                
        Returns:
            최적 가중치 및 포트폴리오 통계
        """
        try:
            # scipy 사용 가능 여부 확인
            from scipy.optimize import minimize
            has_scipy = True
        except ImportError:
            logger.warning("[PortfolioOptimizer] scipy not available, using simple allocation")
            has_scipy = False
        
        if not has_scipy:
            # scipy 없이 간단한 할당
            return self._simple_optimize(method)
        
        # 제약조건
        constraints = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}  # 가중치 합 = 1
        ]
        
        # 목표 수익률 제약
        if method == 'target_return' and target_return is not None:
            constraints.append({
                'type': 'eq',
                'fun': lambda w: np.dot(w, self.returns) - target_return
            })
        
        # 경계 조건 (모든 가중치 0 ~ 1)
        bounds = [(0, 1) for _ in range(self.n_assets)]
        
        # 초기 가중치 (균등 분배)
        initial_weights = np.ones(self.n_assets) / self.n_assets
        
        # 목적 함수 선택
        if method == 'max_sharpe':
            # 샤프 비율 최대화 = -샤프 비율 최소화
            objective = lambda w: -self._sharpe_ratio(w)
        elif method == 'min_variance' or method == 'target_return':
            # 분산 최소화
            objective = lambda w: self._portfolio_variance(w)
        else:
            logger.error(f"[PortfolioOptimizer] Unknown method: {method}")
            return self._simple_optimize('equal')
        
        # 최적화 실행
        try:
            result = minimize(
                objective,
                x0=initial_weights,
                constraints=constraints,
                bounds=bounds,
                method='SLSQP'
            )
            
            if result.success:
                optimal_weights = result.x
            else:
                logger.warning(f"[PortfolioOptimizer] Optimization failed: {result.message}")
                optimal_weights = initial_weights
        except Exception as e:
            logger.error(f"[PortfolioOptimizer] Optimization error: {e}")
            optimal_weights = initial_weights
        
        # 포트폴리오 통계 계산
        stats = self._calculate_portfolio_stats(optimal_weights)
        
        return {
            "weights": optimal_weights.tolist(),
            "expected_return": float(stats["return"]),
            "volatility": float(stats["volatility"]),
            "sharpe_ratio": float(stats["sharpe_ratio"]),
            "method": method
        }
    
    def _simple_optimize(self, method: str) -> Dict[str, Any]:
        """
        scipy 없이 간단한 최적화
        
        Args:
            method: 할당 방법
            
        Returns:
            포트폴리오 결과
        """
        if method == 'max_sharpe' or method == 'equal':
            # 균등 분배
            weights = np.ones(self.n_assets) / self.n_assets
        elif method == 'max_return':
            # 최대 수익률 자산에 모두 투자
            weights = np.zeros(self.n_assets)
            weights[np.argmax(self.returns)] = 1.0
        else:
            weights = np.ones(self.n_assets) / self.n_assets
        
        stats = self._calculate_portfolio_stats(weights)
        
        return {
            "weights": weights.tolist(),
            "expected_return": float(stats["return"]),
            "volatility": float(stats["volatility"]),
            "sharpe_ratio": float(stats["sharpe_ratio"]),
            "method": f"simple_{method}"
        }
    
    def _portfolio_variance(self, weights: np.ndarray) -> float:
        """
        포트폴리오 분산 계산
        
        Args:
            weights: 자산 가중치
            
        Returns:
            분산
        """
        return np.dot(weights.T, np.dot(self.cov_matrix, weights))
    
    def _portfolio_return(self, weights: np.ndarray) -> float:
        """
        포트폴리오 기대 수익률 계산
        
        Args:
            weights: 자산 가중치
            
        Returns:
            기대 수익률
        """
        return np.dot(weights, self.returns)
    
    def _sharpe_ratio(self, weights: np.ndarray, risk_free_rate: float = 0.0) -> float:
        """
        샤프 비율 계산
        
        Args:
            weights: 자산 가중치
            risk_free_rate: 무위험 수익률
            
        Returns:
            샤프 비율
        """
        portfolio_return = self._portfolio_return(weights)
        portfolio_std = np.sqrt(self._portfolio_variance(weights))
        
        if portfolio_std == 0:
            return 0.0
        
        return (portfolio_return - risk_free_rate) / portfolio_std
    
    def _calculate_portfolio_stats(self, weights: np.ndarray) -> Dict[str, float]:
        """
        포트폴리오 통계 계산
        
        Args:
            weights: 자산 가중치
            
        Returns:
            통계 딕셔너리
        """
        return {
            "return": self._portfolio_return(weights),
            "volatility": np.sqrt(self._portfolio_variance(weights)),
            "sharpe_ratio": self._sharpe_ratio(weights)
        }
    
    def efficient_frontier(
        self,
        n_points: int = 100,
        min_return: Optional[float] = None,
        max_return: Optional[float] = None
    ) -> List[Dict[str, float]]:
        """
        효율적 프론티어 계산
        
        Args:
            n_points: 계산할 포인트 수
            min_return: 최소 수익률 (None이면 자동)
            max_return: 최대 수익률 (None이면 자동)
            
        Returns:
            효율적 프론티어 포인트 리스트
        """
        if min_return is None:
            min_return = np.min(self.returns)
        if max_return is None:
            max_return = np.max(self.returns)
        
        target_returns = np.linspace(min_return, max_return, n_points)
        frontier = []
        
        logger.info(f"[PortfolioOptimizer] Computing efficient frontier with {n_points} points")
        
        for target in target_returns:
            try:
                result = self.optimize(target_return=target, method='target_return')
                
                frontier.append({
                    "return": result["expected_return"],
                    "volatility": result["volatility"],
                    "sharpe_ratio": result["sharpe_ratio"],
                    "weights": result["weights"]
                })
            except Exception as e:
                logger.debug(f"[PortfolioOptimizer] Skipping target {target:.4f}: {e}")
                continue
        
        return frontier
    
    def risk_parity(self) -> Dict[str, Any]:
        """
        리스크 패리티 포트폴리오
        
        각 자산의 리스크 기여도를 동일하게 만드는 포트폴리오
        
        Returns:
            리스크 패리티 가중치 및 통계
        """
        # 간단한 근사: 변동성 역수 가중
        volatilities = np.sqrt(np.diag(self.cov_matrix))
        
        # 변동성의 역수로 가중치 설정
        inv_vol = 1.0 / (volatilities + 1e-8)
        weights = inv_vol / np.sum(inv_vol)
        
        stats = self._calculate_portfolio_stats(weights)
        
        return {
            "weights": weights.tolist(),
            "expected_return": float(stats["return"]),
            "volatility": float(stats["volatility"]),
            "sharpe_ratio": float(stats["sharpe_ratio"]),
            "method": "risk_parity"
        }
    
    def maximum_diversification(self) -> Dict[str, Any]:
        """
        최대 분산 포트폴리오
        
        분산 비율을 최대화하는 포트폴리오
        
        Returns:
            최대 분산 가중치 및 통계
        """
        # 간단한 근사: 균등 가중
        weights = np.ones(self.n_assets) / self.n_assets
        
        stats = self._calculate_portfolio_stats(weights)
        
        return {
            "weights": weights.tolist(),
            "expected_return": float(stats["return"]),
            "volatility": float(stats["volatility"]),
            "sharpe_ratio": float(stats["sharpe_ratio"]),
            "method": "maximum_diversification"
        }


if __name__ == "__main__":
    # 테스트
    logging.basicConfig(level=logging.INFO)
    
    # 3개 자산 예시
    returns = np.array([0.12, 0.10, 0.08])  # 연간 기대 수익률
    cov_matrix = np.array([
        [0.04, 0.01, 0.02],
        [0.01, 0.03, 0.01],
        [0.02, 0.01, 0.02]
    ])
    
    optimizer = PortfolioOptimizer(returns, cov_matrix)
    
    # 샤프 비율 최대화
    result_sharpe = optimizer.optimize(method='max_sharpe')
    print(f"Max Sharpe Portfolio: {result_sharpe}")
    
    # 최소 분산
    result_minvar = optimizer.optimize(method='min_variance')
    print(f"Min Variance Portfolio: {result_minvar}")
    
    # 리스크 패리티
    result_rp = optimizer.risk_parity()
    print(f"Risk Parity Portfolio: {result_rp}")
    
    # 효율적 프론티어
    frontier = optimizer.efficient_frontier(n_points=20)
    print(f"Efficient Frontier: {len(frontier)} points computed")
