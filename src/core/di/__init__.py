"""
[Purpose]
- 의존성 주입 모듈 공개 인터페이스

[Exports]
- DIContainer: DI 컨테이너 클래스
- container: 전역 싱글톤 인스턴스
"""
from .container import DIContainer, container

__all__ = ["DIContainer", "container"]
