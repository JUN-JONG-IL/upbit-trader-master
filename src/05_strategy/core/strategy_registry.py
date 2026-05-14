"""
[Purpose]
- 전략 등록 및 관리 레지스트리
[Responsibilities]
- 전략 클래스를 이름으로 등록/조회/목록 관리
"""
from typing import Dict, List, Optional, Type


class StrategyRegistry:
    """전략 레지스트리 - 전략 클래스를 이름으로 등록/조회"""

    _strategies: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str, strategy_class: type) -> None:
        """전략 등록"""
        cls._strategies[name] = strategy_class

    @classmethod
    def get(cls, name: str) -> Optional[type]:
        """이름으로 전략 조회"""
        return cls._strategies.get(name)

    @classmethod
    def list_all(cls) -> List[str]:
        """등록된 전략 목록 반환"""
        return list(cls._strategies.keys())

    @classmethod
    def unregister(cls, name: str) -> None:
        """전략 등록 해제"""
        cls._strategies.pop(name, None)
