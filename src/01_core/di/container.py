"""
[Purpose]
- 의존성 주입 컨테이너 (Dependency Injection)
- 서비스 라이프사이클 관리

[Responsibilities]
- 서비스 등록/조회
- 싱글톤 인스턴스 관리
- 팩토리 함수 지원

[Usage]
    from core.di import container

    # 등록
    container.register("redis", RedisClient())

    # 조회
    redis = container.get("redis")
"""
import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class DIContainer:
    """의존성 주입 컨테이너"""

    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._singletons: Dict[str, bool] = {}

    def register(self, name: str, service: Any, singleton: bool = True):
        """
        서비스 등록

        Args:
            name: 서비스 이름
            service: 서비스 인스턴스 또는 팩토리 함수
            singleton: 싱글톤 여부
        """
        if callable(service) and not hasattr(service, "__self__"):
            # 팩토리 함수
            self._factories[name] = service
            self._singletons[name] = singleton
        else:
            # 인스턴스
            self._services[name] = service
            self._singletons[name] = True  # 인스턴스는 항상 싱글톤

        logger.debug(f"Registered service: {name} (singleton={singleton})")

    def get(self, name: str) -> Any:
        """
        서비스 조회

        Args:
            name: 서비스 이름

        Returns:
            서비스 인스턴스

        Raises:
            KeyError: 서비스가 등록되지 않은 경우
        """
        if name in self._services:
            return self._services[name]

        if name in self._factories:
            instance = self._factories[name]()

            if self._singletons[name]:
                self._services[name] = instance

            return instance

        raise KeyError(f"Service not registered: {name}")

    def has(self, name: str) -> bool:
        """서비스 등록 여부 확인"""
        return name in self._services or name in self._factories

    def unregister(self, name: str):
        """서비스 등록 해제"""
        self._services.pop(name, None)
        self._factories.pop(name, None)
        self._singletons.pop(name, None)

    def clear(self):
        """모든 서비스 초기화"""
        self._services.clear()
        self._factories.clear()
        self._singletons.clear()

    def list_services(self) -> List[str]:
        """등록된 서비스 목록"""
        return list(set(self._services.keys()) | set(self._factories.keys()))


# 전역 인스턴스 (싱글톤)
container = DIContainer()
