"""
[Purpose]
- 스캔 조건 빌더 - 사용자 설정(settings dict)을 Condition/ConditionGroup 객체로 변환

[Responsibilities]
- settings dict → ConditionGroup 변환
- 조건 유효성 검증
- 기본 프리셋에서 조건 생성

[Dependencies]
- scanner.models.condition (Condition, ConditionGroup, ConditionOperator, LogicOperator)

[Author] Copilot
[Created] 2026-03-05
[Modified] 2026-03-05
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models.condition import (
    Condition,
    ConditionGroup,
    ConditionOperator,
    LogicOperator,
)


class ConditionBuilder:
    """
    사용자 설정을 구조화된 조건 객체로 빌드.

    Args:
        logic: 조건 그룹 논리 연산자 (기본값: AND)

    Examples:
        >>> builder = ConditionBuilder()
        >>> group = builder.from_settings({'rsi_threshold': 30, 'golden_enabled': True})
    """

    def __init__(self, logic: LogicOperator = LogicOperator.AND) -> None:
        self._logic = logic

    def from_settings(self, settings: Dict[str, Any]) -> ConditionGroup:
        """
        settings dict에서 ConditionGroup 생성.

        Args:
            settings: 스캐너 설정 딕셔너리

        Returns:
            조건 그룹 객체
        """
        group = ConditionGroup(logic=self._logic, label="scanner_conditions")
        self._add_rsi_condition(group, settings)
        self._add_ma_condition(group, settings)
        self._add_macd_condition(group, settings)
        self._add_bollinger_condition(group, settings)
        self._add_volume_condition(group, settings)
        self._add_stochastic_condition(group, settings)
        return group

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _add_rsi_condition(
        self, group: ConditionGroup, settings: Dict[str, Any]
    ) -> None:
        """RSI 조건 추가."""
        threshold = settings.get('rsi_threshold', 0)
        if not threshold:
            return
        cond_type = settings.get('rsi_condition', '이하')
        op = ConditionOperator.LTE if cond_type == '이하' else ConditionOperator.GTE
        group.add(Condition(
            indicator='RSI',
            operator=op,
            value=float(threshold),
            timeframe=settings.get('rsi_interval', '1분'),
            label=f"RSI {op.value} {threshold}",
        ))

    def _add_ma_condition(
        self, group: ConditionGroup, settings: Dict[str, Any]
    ) -> None:
        """이동 평균 / 골든크로스 조건 추가."""
        if not settings.get('golden_enabled', False):
            return
        ma_cond = settings.get('ma_condition', '골든크로스')
        if ma_cond == '골든크로스':
            op = ConditionOperator.CROSS_UP
        elif ma_cond == '데드크로스':
            op = ConditionOperator.CROSS_DOWN
        else:
            return
        short = settings.get('ma_short', 5)
        long_ = settings.get('ma_long', 20)
        group.add(Condition(
            indicator=f"MA{short}",
            operator=op,
            value=f"MA{long_}",
            timeframe=settings.get('ma_interval', '1분'),
            label=f"MA{short} {op.value} MA{long_}",
        ))

    def _add_macd_condition(
        self, group: ConditionGroup, settings: Dict[str, Any]
    ) -> None:
        """MACD 조건 추가."""
        if settings.get('macd_golden', False):
            group.add(Condition(
                indicator='MACD',
                operator=ConditionOperator.CROSS_UP,
                value='MACD_SIGNAL',
                label="MACD 골든크로스",
            ))
        if settings.get('macd_dead', False):
            group.add(Condition(
                indicator='MACD',
                operator=ConditionOperator.CROSS_DOWN,
                value='MACD_SIGNAL',
                label="MACD 데드크로스",
            ))

    def _add_bollinger_condition(
        self, group: ConditionGroup, settings: Dict[str, Any]
    ) -> None:
        """볼린저 밴드 조건 추가."""
        if settings.get('bb_lower_touch', False):
            group.add(Condition(
                indicator='CLOSE',
                operator=ConditionOperator.LTE,
                value='BB_LOWER',
                label="볼린저 하단 접촉",
            ))
        if settings.get('bb_upper_touch', False):
            group.add(Condition(
                indicator='CLOSE',
                operator=ConditionOperator.GTE,
                value='BB_UPPER',
                label="볼린저 상단 접촉",
            ))

    def _add_volume_condition(
        self, group: ConditionGroup, settings: Dict[str, Any]
    ) -> None:
        """거래량 조건 추가."""
        surge = settings.get('volume_surge', {})
        if not any(surge.values()):
            return
        ratio = settings.get('vol_avg_ratio', 10)
        group.add(Condition(
            indicator='VOLUME',
            operator=ConditionOperator.GTE,
            value=float(ratio),
            label=f"거래량 {ratio}배 이상",
        ))

    def _add_stochastic_condition(
        self, group: ConditionGroup, settings: Dict[str, Any]
    ) -> None:
        """Stochastic 조건 추가."""
        if settings.get('stoch_k_gt_d', False):
            group.add(Condition(
                indicator='STOCH_K',
                operator=ConditionOperator.GT,
                value='STOCH_D',
                label="Stochastic %K > %D",
            ))
        if settings.get('stoch_k_lt_d', False):
            group.add(Condition(
                indicator='STOCH_K',
                operator=ConditionOperator.LT,
                value='STOCH_D',
                label="Stochastic %K < %D",
            ))

    def add_custom(
        self,
        group: ConditionGroup,
        indicator: str,
        operator: ConditionOperator,
        value: Any,
        timeframe: str = "1분",
        label: str = "",
    ) -> ConditionGroup:
        """
        커스텀 조건 직접 추가.

        Args:
            group: 대상 조건 그룹
            indicator: 지표 이름
            operator: 연산자
            value: 기준값
            timeframe: 타임프레임
            label: 레이블

        Returns:
            조건이 추가된 그룹
        """
        group.add(Condition(
            indicator=indicator,
            operator=operator,
            value=value,
            timeframe=timeframe,
            label=label or f"{indicator} {operator.value} {value}",
        ))
        return group
