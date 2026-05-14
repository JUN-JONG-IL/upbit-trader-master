"""
[Purpose]
- 전략 선택 로직
"""
from typing import List, Optional
from ....core.strategy_registry import StrategyRegistry


class StrategySelector:
    """전략 선택 및 관리"""

    def get_available_strategies(self) -> List[str]:
        """등록된 전략 목록 반환"""
        return StrategyRegistry.list_all()

    def select_strategy(self, name: str) -> Optional[type]:
        """이름으로 전략 선택"""
        return StrategyRegistry.get(name)
