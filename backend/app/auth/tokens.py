"""Opaque session tokens. Only a keyed hash (HMAC-SHA256 with AUTH_SECRET_KEY) is stored,
so a leaked sessions table cannot be used to authenticate."""

import hashlib
import hmac
import secrets


def new_session_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits of randomness


def hash_token(token: str, secret: bytes) -> bytes:
    return hmac.new(secret, token.encode("utf-8"), hashlib.sha256).digest()
