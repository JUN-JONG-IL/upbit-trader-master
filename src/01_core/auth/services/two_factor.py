"""Two-factor authentication support."""
from __future__ import annotations


class TwoFactorAuth:
    """Provides TOTP-based two-factor authentication."""

    def generate_secret(self) -> str:
        raise NotImplementedError

    def verify_token(self, secret: str, token: str) -> bool:
        raise NotImplementedError
