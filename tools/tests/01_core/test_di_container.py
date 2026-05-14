"""
DI 컨테이너 테스트
"""
import pytest
from di import DIContainer


def test_di_register_instance():
    """인스턴스 등록 및 조회 테스트"""
    container = DIContainer()

    class Service:
        pass

    svc = Service()
    container.register("service", svc)

    assert container.get("service") is svc


def test_di_singleton():
    """싱글톤 서비스 테스트"""
    container = DIContainer()

    class Service:
        pass

    container.register("service", Service)

    s1 = container.get("service")
    s2 = container.get("service")

    assert s1 is s2


def test_di_factory_non_singleton():
    """팩토리 서비스 테스트 (싱글톤=False)"""
    container = DIContainer()

    class Service:
        pass

    container.register("service", Service, singleton=False)

    s1 = container.get("service")
    s2 = container.get("service")

    assert s1 is not s2


def test_di_has():
    """서비스 등록 여부 확인 테스트"""
    container = DIContainer()

    class Service:
        pass

    assert not container.has("service")
    container.register("service", Service())
    assert container.has("service")


def test_di_unregister():
    """서비스 등록 해제 테스트"""
    container = DIContainer()

    class Service:
        pass

    container.register("service", Service())
    container.unregister("service")

    assert not container.has("service")
    with pytest.raises(KeyError):
        container.get("service")


def test_di_clear():
    """모든 서비스 초기화 테스트"""
    container = DIContainer()

    class A:
        pass

    class B:
        pass

    container.register("a", A())
    container.register("b", B)
    container.clear()

    assert not container.has("a")
    assert not container.has("b")


def test_di_list_services():
    """서비스 목록 조회 테스트"""
    container = DIContainer()

    class A:
        pass

    class B:
        pass

    container.register("alpha", A())
    container.register("beta", B)

    services = container.list_services()
    assert "alpha" in services
    assert "beta" in services


def test_di_key_error_on_missing():
    """미등록 서비스 조회 시 KeyError 테스트"""
    container = DIContainer()

    with pytest.raises(KeyError, match="Service not registered: missing"):
        container.get("missing")


def test_di_factory_singleton_cached():
    """팩토리 싱글톤 캐싱 테스트"""
    container = DIContainer()
    call_count = 0

    class Service:
        pass

    def factory():
        nonlocal call_count
        call_count += 1
        return Service()

    container.register("counted", factory, singleton=True)

    container.get("counted")
    container.get("counted")

    assert call_count == 1
