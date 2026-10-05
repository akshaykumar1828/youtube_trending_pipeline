"""Password hashing with Argon2id (argon2-cffi, RFC 9106 low-memory parameters)."""

from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128  # bounds hashing cost per request

_hasher = PasswordHasher()


def password_problem(password: str) -> str | None:
    """A user-facing reason the password is unacceptable, or None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
    if not password.strip():
        return "Password cannot be only whitespace."
    return None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return _hasher.hash("timing-equalisation-dummy-password")


def burn_verification(password: str) -> None:
    """Spend the same time as a real verification when the account does not exist, so
    response time does not reveal which emails are registered."""
    verify_password(_dummy_hash(), password)
