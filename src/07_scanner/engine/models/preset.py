"""
[Purpose]
- 스캐너 프리셋 데이터 모델 정의

[Responsibilities]
- 프리셋을 dataclass로 구조화
- 직렬화/역직렬화 지원 (JSON, MongoDB)
- 프리셋 메타데이터 관리 (생성일, 수정일, 설명)

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
class Preset:
    """
    스캐너 프리셋 모델.

    Args:
        name: 프리셋 이름 (고유)
        settings: 스캐너 설정 딕셔너리
        description: 프리셋 설명
        tags: 분류 태그 목록
        is_builtin: 기본 제공 프리셋 여부
        created_at: 생성 시각
        updated_at: 마지막 수정 시각
        author: 작성자

    Examples:
        >>> preset = Preset(name='골든크로스', settings={'golden_enabled': True})
        >>> preset.to_dict()
        {'name': '골든크로스', 'settings': {...}, ...}
    """

    name: str
    settings: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    tags: List[str] = field(default_factory=list)
    is_builtin: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    author: str = "user"

    def __post_init__(self) -> None:
        """유효성 검증 및 타입 변환."""
        if not self.name:
            raise ValueError("Preset name must not be empty")
        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at)
        if isinstance(self.updated_at, str):
            self.updated_at = datetime.fromisoformat(self.updated_at)

    def touch(self) -> None:
        """updated_at 갱신."""
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """
        딕셔너리로 직렬화 (JSON/MongoDB 저장용).

        Returns:
            직렬화된 딕셔너리
        """
        d = asdict(self)
        d['created_at'] = self.created_at.isoformat()
        d['updated_at'] = self.updated_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Preset:
        """
        딕셔너리에서 역직렬화.

        Args:
            data: 딕셔너리 데이터

        Returns:
            Preset 인스턴스
        """
        data = dict(data)
        # MongoDB _id 필드 제거
        data.pop('_id', None)
        return cls(**data)

    def __repr__(self) -> str:
        return (
            f"Preset(name={self.name!r}, tags={self.tags}, "
            f"builtin={self.is_builtin})"
        )
