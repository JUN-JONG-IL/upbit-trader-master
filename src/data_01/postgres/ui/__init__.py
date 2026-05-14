"""src/data_01/postgres/ui ??PostgreSQL CQRS Event Store UI ?⑦궎吏"""

from .postgres_dialog import PostgresEventStoreDialog

__all__ = ["PostgresEventStoreDialog"]

# 紐⑤땲?곕쭅 ?ㅼ씠?쇰줈洹??덉쟾 濡쒕뱶
try:
    from .postgres_monitor import PostgresMonitorDialog  # noqa: F401
    __all__.append("PostgresMonitorDialog")
except Exception:
    pass


