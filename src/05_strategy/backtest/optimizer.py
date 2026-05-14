"""
[Purpose]
- 전략 파라미터 최적화 엔진
[Responsibilities]
- Grid Search, Random Search 기반 최적 파라미터 탐색
"""

import itertools
import logging
from typing import Dict, List, Any, Callable, Optional
import numpy as np

logger = logging.getLogger(__name__)


class ParameterOptimizer:
    """전략 파라미터 최적화기"""

    def __init__(self, metric: str = 'sharpe_ratio'):
        self.metric = metric
        self.results: List[Dict] = []

    def grid_search(
        self,
        strategy_class: type,
        param_grid: Dict[str, List[Any]],
        backtester,
        data,
        **kwargs
    ) -> Dict:
        """
        Grid Search로 최적 파라미터 탐색

        Args:
            strategy_class: 전략 클래스
            param_grid: 파라미터 그리드 (예: {'period': [10, 20, 30], 'threshold': [1.5, 2.0]})
            backtester: Backtester 인스턴스
            data: 백테스트 데이터
            **kwargs: 전략 생성자에 전달할 추가 인수

        Returns:
            최적 파라미터 및 결과
        """
        logger.info(f'Grid search 시작: {param_grid}')
        best_score = float('-inf')
        best_params = {}
        best_result = {}

        param_combinations = self._generate_combinations(param_grid)
        total = len(param_combinations)

        for i, params in enumerate(param_combinations):
            try:
                strategy = strategy_class(**params, **kwargs)
                result = backtester.run(strategy, data)
                score = result.get('metrics', {}).get(self.metric, float('-inf'))

                self.results.append({'params': params, 'score': score, 'result': result})

                if score > best_score:
                    best_score = score
                    best_params = params
                    best_result = result

                logger.info(f'진행: {i+1}/{total}, 파라미터: {params}, 점수: {score:.4f}')
            except Exception as e:
                logger.warning(f'파라미터 {params} 평가 실패: {e}')

        logger.info(f'Grid search 완료: 최적 파라미터={best_params}, 최적 점수={best_score:.4f}')
        return {'best_params': best_params, 'best_score': best_score, 'best_result': best_result}

    def _generate_combinations(self, param_grid: Dict[str, List[Any]]) -> List[Dict]:
        """파라미터 조합 생성"""
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        return [dict(zip(keys, combo)) for combo in itertools.product(*values)]
