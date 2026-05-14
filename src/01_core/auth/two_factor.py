"""Two-factor authentication support.

Re-exports from services subpackage for backward compatibility.
"""
from .services.two_factor import TwoFactorAuth

__all__ = ['TwoFactorAuth']
