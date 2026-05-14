"""
[Purpose]
- 유전 알고리즘 기반 파라미터 최적화
"""
import logging
import random
from typing import Dict, List, Any, Callable

logger = logging.getLogger(__name__)


class GeneticAlgorithm:
    """유전 알고리즘 파라미터 최적화"""

    def __init__(
        self,
        population_size: int = 50,
        generations: int = 100,
        mutation_rate: float = 0.1,
        crossover_rate: float = 0.8
    ):
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate

    def optimize(
        self,
        param_ranges: Dict[str, tuple],
        fitness_fn: Callable[[Dict], float]
    ) -> Dict[str, Any]:
        """
        유전 알고리즘으로 파라미터 최적화

        Args:
            param_ranges: 파라미터 범위 (예: {'period': (5, 50), 'threshold': (0.5, 3.0)})
            fitness_fn: 적합도 함수 (파라미터 딕셔너리 → 점수)

        Returns:
            최적 파라미터
        """
        population = self._init_population(param_ranges)
        best_individual = None
        best_fitness = float('-inf')

        for gen in range(self.generations):
            fitness_scores = [fitness_fn(ind) for ind in population]

            gen_best_idx = max(range(len(fitness_scores)), key=lambda i: fitness_scores[i])
            if fitness_scores[gen_best_idx] > best_fitness:
                best_fitness = fitness_scores[gen_best_idx]
                best_individual = population[gen_best_idx].copy()

            logger.debug(f'세대 {gen+1}/{self.generations}, 최적 점수: {best_fitness:.4f}')

            population = self._evolve(population, fitness_scores, param_ranges)

        return best_individual or {}

    def _init_population(self, param_ranges: Dict[str, tuple]) -> List[Dict]:
        """초기 집단 생성"""
        population = []
        for _ in range(self.population_size):
            individual = {}
            for key, (low, high) in param_ranges.items():
                if isinstance(low, int) and isinstance(high, int):
                    individual[key] = random.randint(low, high)
                else:
                    individual[key] = random.uniform(low, high)
            population.append(individual)
        return population

    def _evolve(
        self,
        population: List[Dict],
        fitness_scores: List[float],
        param_ranges: Dict[str, tuple]
    ) -> List[Dict]:
        """다음 세대 생성"""
        new_population = []
        while len(new_population) < self.population_size:
            parent1 = self._tournament_select(population, fitness_scores)
            parent2 = self._tournament_select(population, fitness_scores)
            child = self._crossover(parent1, parent2)
            child = self._mutate(child, param_ranges)
            new_population.append(child)
        return new_population

    def _tournament_select(self, population: List[Dict], fitness_scores: List[float]) -> Dict:
        """토너먼트 선택"""
        idx1, idx2 = random.sample(range(len(population)), 2)
        return population[idx1] if fitness_scores[idx1] > fitness_scores[idx2] else population[idx2]

    def _crossover(self, parent1: Dict, parent2: Dict) -> Dict:
        """교차 연산"""
        if random.random() > self.crossover_rate:
            return parent1.copy()
        child = {}
        for key in parent1:
            child[key] = parent1[key] if random.random() < 0.5 else parent2[key]
        return child

    def _mutate(self, individual: Dict, param_ranges: Dict[str, tuple]) -> Dict:
        """돌연변이 연산"""
        for key, (low, high) in param_ranges.items():
            if random.random() < self.mutation_rate:
                if isinstance(low, int) and isinstance(high, int):
                    individual[key] = random.randint(low, high)
                else:
                    individual[key] = random.uniform(low, high)
        return individual
