"""
[Purpose]
- 실시간 시그널 집계 및 관리
"""
from typing import List, Dict, Optional
from datetime import datetime


class SignalAggregator:
    """시그널 집계 및 관리"""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self._signals: List[Dict] = []

    def add(self, signal: Dict) -> None:
        """시그널 추가"""
        signal['received_at'] = datetime.now().isoformat()
        self._signals.append(signal)
        if len(self._signals) > self.max_history:
            self._signals = self._signals[-self.max_history:]

    def get_all(self) -> List[Dict]:
        """전체 시그널 반환"""
        return list(self._signals)

    def get_by_code(self, code: str) -> List[Dict]:
        """특정 코인 시그널 필터링"""
        return [s for s in self._signals if s.get('code') == code]

    def clear(self) -> None:
        """시그널 초기화"""
        self._signals.clear()
