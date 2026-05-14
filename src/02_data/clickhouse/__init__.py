"""
ClickHouse 패키지

[Purpose]
ClickHouse 연결 관리 및 분석 쿼리 지원

[Modules]
- connection: ClickHouse 클라이언트 팩토리
- health_check: ClickHouse 연결 상태 확인
- ui: ClickHouse 관리 UI
"""

try:
    from .connection import get_client
except Exception:
    pass

__all__ = ["get_client"]
