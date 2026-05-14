"""
[Purpose]
- 백테스트 진행 상태 추적
"""
from typing import Callable, Optional


class ProgressTracker:
    """백테스트 진행 상태 추적기"""

    def __init__(self, callback: Optional[Callable] = None):
        self.callback = callback
        self.current = 0
        self.total = 0

    def start(self, total: int) -> None:
        """진행 추적 시작"""
        self.total = total
        self.current = 0

    def update(self, step: int = 1) -> None:
        """진행 상태 업데이트"""
        self.current += step
        if self.callback:
            progress = int(self.current / self.total * 100) if self.total > 0 else 0
            self.callback(progress)

    @property
    def progress_pct(self) -> float:
        """진행률 (0~100)"""
        return (self.current / self.total * 100) if self.total > 0 else 0.0
