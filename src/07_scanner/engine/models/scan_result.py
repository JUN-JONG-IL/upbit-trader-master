"""
[Purpose]
- 스캔 결과 데이터 모델 정의

[Responsibilities]
- 스캔 결과를 구조화된 dataclass로 표현
- DB 저장/조회를 위한 직렬화/역직렬화 지원
- 결과 비교 및 정렬 지원

[Dependencies]
- dataclasses: 데이터 클래스 정의
- datetime: 타임스탬프 처리

[Author] Copilot
[Created] 2026-03-05
[Modified] 2026-03-05
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ScanResult:
    """
    단일 종목 스캔 결과 모델.

    Args:
        symbol: 종목 코드 (예: KRW-BTC)
        interval: 조회 타임프레임 (예: 1분, 5분, 1시간)
        score: 조건 충족 점수 (0.0 ~ 1.0)
        matched_conditions: 충족된 조건 이름 목록
        indicators: 계산된 지표값 딕셔너리
        timestamp: 스캔 수행 시각

    Attributes:
        symbol: 종목 코드
        interval: 타임프레임
        score: 종합 점수
        matched_conditions: 충족된 조건 리스트
        indicators: 계산된 지표값 {'RSI': 28.5, 'MA5': 100.0, ...}
        timestamp: 스캔 시각 (UTC)

    Examples:
        >>> result = ScanResult(symbol='KRW-BTC', interval='5분', score=0.85)
        >>> result.to_dict()
        {'symbol': 'KRW-BTC', 'interval': '5분', 'score': 0.85, ...}
    """

    symbol: str
    interval: str
    score: float
    matched_conditions: List[str] = field(default_factory=list)
    indicators: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        """유효성 검증."""
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be between 0.0 and 1.0, got {self.score}")
        if not self.symbol:
            raise ValueError("symbol must not be empty")

    def to_dict(self) -> Dict[str, Any]:
        """
        딕셔너리로 직렬화 (DB 저장용).

        Returns:
            직렬화된 딕셔너리
        """
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScanResult:
        """
        딕셔너리에서 역직렬화.

        Args:
            data: 딕셔너리 데이터

        Returns:
            ScanResult 인스턴스
        """
        data = dict(data)
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)

    @classmethod
    def from_tuple(cls, tup: tuple) -> ScanResult:
        """
        (symbol, interval, score) 튜플에서 생성.

        Args:
            tup: (symbol, interval, score) 튜플

        Returns:
            ScanResult 인스턴스
        """
        symbol, interval, score = tup
        return cls(symbol=symbol, interval=interval, score=score)

    def __lt__(self, other: ScanResult) -> bool:
        """스코어 기준 비교 (내림차순 정렬용)."""
        return self.score > other.score

    def __repr__(self) -> str:
        return (
            f"ScanResult(symbol={self.symbol!r}, interval={self.interval!r}, "
            f"score={self.score:.3f}, conditions={len(self.matched_conditions)})"
        )
