"""Base Chart Engine - 추상 클래스"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import pandas as pd

class BaseChartEngine(ABC):
    """차트 엔진 기본 인터페이스"""
    
    @abstractmethod
    def render(self, data: pd.DataFrame, **kwargs) -> any:
        """차트 렌더링"""
        pass
    
    @abstractmethod
    def add_indicator(self, name: str, params: Dict):
        """지표 추가"""
        pass
    
    @abstractmethod
    def clear(self):
        """차트 초기화"""
        pass
