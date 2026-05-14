"""Authentication service for managing user credentials.

Re-exports from services subpackage for backward compatibility.
"""
from .services.auth_service import AuthService

__all__ = ['AuthService']
