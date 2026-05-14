"""Session manager for tracking authenticated user sessions.

Re-exports from services subpackage for backward compatibility.
"""
from .services.session_manager import SessionManager

__all__ = ['SessionManager']
