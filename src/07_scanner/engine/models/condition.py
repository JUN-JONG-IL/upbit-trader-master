"""
[Purpose]
- 스캔 조건 데이터 모델 정의

[Responsibilities]
- 단일 조건 및 조건 그룹을 dataclass로 표현
- 조건 직렬화/역직렬화 지원
- 조건 결합 연산자(AND/OR) 지원

[Dependencies]
- dataclasses: 데이터 클래스 정의
- enum: 연산자 열거형

[Author] Copilot
[Created] 2026-03-05
[Modified] 2026-03-05
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class ConditionOperator(str, Enum):
    """
    조건 비교 연산자.

    Values:
        GT: 초과 (>)
        GTE: 이상 (>=)
        LT: 미만 (<)
        LTE: 이하 (<=)
        EQ: 동일 (==)
        CROSS_UP: 상향 돌파
        CROSS_DOWN: 하향 돌파
    """
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    CROSS_UP = "cross_up"
    CROSS_DOWN = "cross_down"


class LogicOperator(str, Enum):
    """
    조건 그룹 논리 연산자.

    Values:
        AND: 모든 조건 충족
        OR: 하나 이상 조건 충족
    """
    AND = "AND"
    OR = "OR"


@dataclass
class Condition:
    """
    단일 스캔 조건 모델.

    Args:
        indicator: 지표 이름 (예: 'RSI', 'MA5', 'volume')
        operator: 비교 연산자 (ConditionOperator)
        value: 기준값 (숫자 또는 다른 지표 이름)
        timeframe: 타임프레임 (예: '1분', '5분')
        enabled: 조건 활성화 여부
        weight: 점수 가중치 (0.0 ~ 1.0)
        label: 사람이 읽기 쉬운 레이블

    Examples:
        >>> cond = Condition(indicator='RSI', operator=ConditionOperator.LT, value=30)
        >>> cond.to_dict()
        {'indicator': 'RSI', 'operator': '<', 'value': 30, ...}
    """

    indicator: str
    operator: ConditionOperator
    value: Union[float, str]
    timeframe: str = "1분"
    enabled: bool = True
    weight: float = 1.0
    label: str = ""

    def __post_init__(self) -> None:
        """유효성 검증 및 타입 변환."""
        if isinstance(self.operator, str):
            self.operator = ConditionOperator(self.operator)
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError(f"weight must be between 0.0 and 1.0, got {self.weight}")
        if not self.label:
            self.label = f"{self.indicator} {self.operator.value} {self.value}"

    def to_dict(self) -> Dict[str, Any]:
        """
        딕셔너리로 직렬화.

        Returns:
            직렬화된 딕셔너리
        """
        d = asdict(self)
        d['operator'] = self.operator.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Condition:
        """
        딕셔너리에서 역직렬화.

        Args:
            data: 딕셔너리 데이터

        Returns:
            Condition 인스턴스
        """
        return cls(**data)


@dataclass
class ConditionGroup:
    """
    조건 그룹 모델 (AND/OR 결합).

    Args:
        conditions: 조건 리스트
        logic: 논리 연산자 (AND 또는 OR)
        label: 그룹 레이블

    Examples:
        >>> grp = ConditionGroup(
        ...     conditions=[
        ...         Condition('RSI', ConditionOperator.LT, 30),
        ...         Condition('volume', ConditionOperator.GT, 1.5),
        ...     ],
        ...     logic=LogicOperator.AND
        ... )
    """

    conditions: List[Condition] = field(default_factory=list)
    logic: LogicOperator = LogicOperator.AND
    label: str = ""

    def __post_init__(self) -> None:
        """타입 변환."""
        if isinstance(self.logic, str):
            self.logic = LogicOperator(self.logic)

    def add(self, condition: Condition) -> None:
        """
        조건 추가.

        Args:
            condition: 추가할 조건
        """
        self.conditions.append(condition)

    def to_dict(self) -> Dict[str, Any]:
        """
        딕셔너리로 직렬화.

        Returns:
            직렬화된 딕셔너리
        """
        return {
            'conditions': [c.to_dict() for c in self.conditions],
            'logic': self.logic.value,
            'label': self.label,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ConditionGroup:
        """
        딕셔너리에서 역직렬화.

        Args:
            data: 딕셔너리 데이터

        Returns:
            ConditionGroup 인스턴스
        """
        conditions = [Condition.from_dict(c) for c in data.get('conditions', [])]
        return cls(
            conditions=conditions,
            logic=data.get('logic', LogicOperator.AND),
            label=data.get('label', ''),
        )
