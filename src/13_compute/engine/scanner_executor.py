"""
[Purpose]
스캐너 실행기 - 조건식 평가 및 종목 필터링

[Responsibilities]
- 사용자 정의 조건식 평가 (RSI < 30, Volume > MA(20) 등)
- 200ms 마이크로배치 실행
- 변경된 종목만 평가 (전체 종목 평가 금지)
- delta 전송 (add/remove)

[Main Flow]
1. 캔들 close 이벤트로 변경된 종목 추적
2. 200ms 주기로 배치 실행
3. 변경된 종목만 조건식 평가
4. add/remove delta 계산 및 전송
"""

import ast
import operator
from typing import Dict, Set, List, Callable, Optional, Any
from dataclasses import dataclass


@dataclass
class ScanCondition:
    """스캔 조건"""
    id: str
    name: str
    description: str
    expression: str  # "RSI(14) < 30 AND Volume > Volume_MA(20)"
    enabled: bool = True


class ExpressionEvaluator:
    """조건식 평가기 - AST 기반"""
    
    # 지원하는 연산자
    OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.And: operator.and_,
        ast.Or: operator.or_,
        ast.Not: operator.not_,
    }
    
    def __init__(self):
        self.functions = {
            'abs': abs,
            'max': max,
            'min': min,
            'round': round,
        }
    
    def evaluate(self, expression: str, context: Dict[str, Any]) -> bool:
        """
        조건식 평가
        
        Args:
            expression: 조건식 문자열
            context: 변수 컨텍스트 (지표 값 등)
        
        Returns:
            조건 만족 여부
        
        Example:
            expression = "RSI < 30 AND Volume > 1000000"
            context = {"RSI": 25.5, "Volume": 1500000}
            result = evaluate(expression, context)  # True
        """
        try:
            tree = ast.parse(expression, mode='eval')
            result = self._eval_node(tree.body, context)
            return bool(result)
        except Exception:
            return False
    
    def _eval_node(self, node, context: Dict[str, Any]):
        """AST 노드 평가"""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            return context.get(node.id, 0)
        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, context)
            right = self._eval_node(node.right, context)
            op = self.OPERATORS.get(type(node.op))
            if op:
                return op(left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand, context)
            op = self.OPERATORS.get(type(node.op))
            if op:
                return op(operand)
        elif isinstance(node, ast.Compare):
            left = self._eval_node(node.left, context)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator, context)
                op_func = self.OPERATORS.get(type(op))
                if not op_func or not op_func(left, right):
                    return False
                left = right
            return True
        elif isinstance(node, ast.BoolOp):
            op = self.OPERATORS.get(type(node.op))
            if isinstance(node.op, ast.And):
                return all(self._eval_node(val, context) for val in node.values)
            elif isinstance(node.op, ast.Or):
                return any(self._eval_node(val, context) for val in node.values)
        elif isinstance(node, ast.Call):
            func_name = node.func.id if isinstance(node.func, ast.Name) else None
            if func_name in self.functions:
                args = [self._eval_node(arg, context) for arg in node.args]
                return self.functions[func_name](*args)
        
        return False


class ScannerExecutor:
    """
    스캐너 실행기
    
    200ms 마이크로배치로 조건식 평가 및 종목 필터링
    """
    
    def __init__(self, interval_ms: int = 200):
        """
        Args:
            interval_ms: 배치 실행 간격 (밀리초)
        """
        self.interval_ms = interval_ms
        self.conditions: List[ScanCondition] = []
        self.matched_symbols: Dict[str, Set[str]] = {}  # {condition_id: set(symbols)}
        self.changed_symbols: Set[str] = set()  # 최근 변경된 종목
        self.indicators_cache: Dict[str, Dict[str, Any]] = {}  # {symbol: indicators}
        self.evaluator = ExpressionEvaluator()
    
    def add_condition(self, condition: ScanCondition):
        """조건 추가"""
        self.conditions.append(condition)
        if condition.id not in self.matched_symbols:
            self.matched_symbols[condition.id] = set()
    
    def remove_condition(self, condition_id: str):
        """조건 제거"""
        self.conditions = [c for c in self.conditions if c.id != condition_id]
        if condition_id in self.matched_symbols:
            del self.matched_symbols[condition_id]
    
    def on_candle_close(self, symbol: str, timeframe: str, candle: dict, indicators: Dict[str, Any]):
        """
        캔들 close 이벤트 처리
        
        Args:
            symbol: 심볼
            timeframe: 타임프레임
            candle: 캔들 데이터
            indicators: 지표 데이터
        """
        # 변경된 종목 추가
        self.changed_symbols.add(symbol)
        
        # 지표 캐시 업데이트
        self.indicators_cache[symbol] = {
            **indicators,
            'Close': candle['c'],
            'Open': candle['o'],
            'High': candle['h'],
            'Low': candle['l'],
            'Volume': candle['v'],
        }
    
    def run_batch(self) -> Dict[str, List[dict]]:
        """
        배치 실행 (200ms 주기)
        
        Returns:
            {'add': [...], 'remove': [...]}
        """
        add_list = []
        remove_list = []
        
        if not self.changed_symbols:
            return {'add': add_list, 'remove': remove_list}
        
        # 변경된 종목만 평가
        for symbol in self.changed_symbols:
            if symbol not in self.indicators_cache:
                continue
            
            context = self.indicators_cache[symbol]
            
            # 모든 조건 평가
            for condition in self.conditions:
                if not condition.enabled:
                    continue
                
                matched = self._evaluate_condition(condition, context)
                prev_matched = symbol in self.matched_symbols.get(condition.id, set())
                
                if matched and not prev_matched:
                    # 새로 매칭된 종목
                    self.matched_symbols[condition.id].add(symbol)
                    add_list.append({
                        'symbol': symbol,
                        'condition_id': condition.id,
                        'condition_name': condition.name,
                        'reason': condition.description,
                        'score': self._calculate_score(symbol, context)
                    })
                elif not matched and prev_matched:
                    # 매칭 해제된 종목
                    self.matched_symbols[condition.id].discard(symbol)
                    remove_list.append({
                        'symbol': symbol,
                        'condition_id': condition.id
                    })
        
        # 변경 심볼 초기화
        self.changed_symbols.clear()
        
        return {'add': add_list, 'remove': remove_list}
    
    def _evaluate_condition(self, condition: ScanCondition, context: Dict[str, Any]) -> bool:
        """
        조건 평가
        
        Args:
            condition: 스캔 조건
            context: 지표 컨텍스트
        
        Returns:
            조건 만족 여부
        """
        try:
            # 간단한 조건식 평가
            # 예: "RSI < 30 AND Volume > 1000000"
            
            # AST 기반 평가
            result = self.evaluator.evaluate(condition.expression, context)
            return result
            
        except Exception:
            return False
    
    def _calculate_score(self, symbol: str, context: Dict[str, Any]) -> float:
        """
        종목 스코어 계산
        
        Args:
            symbol: 심볼
            context: 지표 컨텍스트
        
        Returns:
            스코어 (0-100)
        """
        # 기본 스코어 계산 로직
        score = 50.0
        
        # RSI 기반 스코어 조정
        rsi = context.get('rsi_14', 50)
        if rsi < 30:
            score += (30 - rsi) / 30 * 25  # 과매도 보너스
        elif rsi > 70:
            score += (rsi - 70) / 30 * 25  # 과매수 보너스
        
        # 볼륨 기반 스코어 조정
        volume = context.get('Volume', 0)
        if volume > 0:
            score += min(10, volume / 1000000)
        
        return min(100.0, max(0.0, score))
    
    def get_matched_symbols(self, condition_id: Optional[str] = None) -> List[str]:
        """
        매칭된 종목 조회
        
        Args:
            condition_id: 조건 ID (None이면 모든 조건)
        
        Returns:
            매칭된 종목 리스트
        """
        if condition_id:
            return list(self.matched_symbols.get(condition_id, set()))
        
        # 모든 조건의 종목 병합
        all_symbols = set()
        for symbols in self.matched_symbols.values():
            all_symbols.update(symbols)
        
        return list(all_symbols)
    
    def get_all_results(self) -> List[dict]:
        """
        전체 스캔 결과 조회
        
        Returns:
            [{'symbol': str, 'condition_id': str, 'score': float}, ...]
        """
        results = []
        
        for condition in self.conditions:
            if not condition.enabled:
                continue
            
            for symbol in self.matched_symbols.get(condition.id, set()):
                context = self.indicators_cache.get(symbol, {})
                results.append({
                    'symbol': symbol,
                    'condition_id': condition.id,
                    'condition_name': condition.name,
                    'reason': condition.description,
                    'score': self._calculate_score(symbol, context)
                })
        
        # 스코어 순으로 정렬
        results.sort(key=lambda x: x['score'], reverse=True)
        
        return results
