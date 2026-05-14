"""Symbol service for retrieving and managing market symbols."""
from __future__ import annotations


class SymbolService:
    """Manages available market symbols."""

    def get_symbols(self) -> list[str]:
        raise NotImplementedError
