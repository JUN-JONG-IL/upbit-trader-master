"""
[Purpose]
- 전략 파라미터 유효성 검사
"""
from typing import Any, Dict, List


class StrategyValidator:
    """전략 파라미터 검증"""

    @staticmethod
    def validate_period(period: Any, min_val: int = 1, max_val: int = 500) -> bool:
        """기간 파라미터 검증"""
        return isinstance(period, int) and min_val <= period <= max_val

    @staticmethod
    def validate_threshold(threshold: Any, min_val: float = 0.0) -> bool:
        """임계값 파라미터 검증"""
        return isinstance(threshold, (int, float)) and threshold >= min_val

    @staticmethod
    def validate_price(price: Any) -> bool:
        """가격 유효성 검증"""
        return isinstance(price, (int, float)) and price > 0

    @staticmethod
    def validate_params(params: Dict[str, Any], schema: Dict[str, dict]) -> List[str]:
        """
        파라미터 스키마 기반 검증

        Args:
            params: 검증할 파라미터
            schema: 스키마 (예: {'period': {'type': int, 'min': 1, 'max': 200}})

        Returns:
            오류 메시지 목록 (비어있으면 유효)
        """
        errors = []
        for key, rules in schema.items():
            if key not in params:
                errors.append(f"필수 파라미터 누락: {key}")
                continue
            val = params[key]
            if 'type' in rules and not isinstance(val, rules['type']):
                errors.append(f"{key}: 타입 오류 (expected {rules['type'].__name__})")
            if 'min' in rules and val < rules['min']:
                errors.append(f"{key}: 최소값({rules['min']}) 미만")
            if 'max' in rules and val > rules['max']:
                errors.append(f"{key}: 최대값({rules['max']}) 초과")
        return errors
