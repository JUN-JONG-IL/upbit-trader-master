"""src/data_01/postgres/ui ??PostgreSQL CQRS Event Store UI ?¨í‚¤ì§€"""

from .postgres_dialog import PostgresEventStoreDialog

__all__ = ["PostgresEventStoreDialog"]

# ëª¨ë‹ˆ?°ë§ ?¤ì´?¼ë¡œê·??ˆì „ ë¡œë“œ
try:
    from .postgres_monitor import PostgresMonitorDialog  # noqa: F401
    __all__.append("PostgresMonitorDialog")
except Exception:
    pass


