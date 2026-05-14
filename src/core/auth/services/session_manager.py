"""Session manager for tracking authenticated user sessions."""
from __future__ import annotations


class SessionManager:
    """Manages active user sessions."""

    def create_session(self, user_id: str) -> str:
        raise NotImplementedError

    def invalidate_session(self, session_id: str) -> None:
        raise NotImplementedError
