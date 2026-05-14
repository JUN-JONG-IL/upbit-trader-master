"""src/02_data/postgres/ui — PostgreSQL CQRS Event Store UI 패키지"""

from .postgres_dialog import PostgresEventStoreDialog

__all__ = ["PostgresEventStoreDialog"]

# 모니터링 다이얼로그 안전 로드
try:
    from .postgres_monitor import PostgresMonitorDialog  # noqa: F401
    __all__.append("PostgresMonitorDialog")
except Exception:
    pass

