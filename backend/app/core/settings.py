"""API settings read from the environment / .env.

Database credentials are NOT here: app/db/config.py reads them (read-only analytics role
and the auth role). This module reads the authentication secret, which is never logged
or exposed (repr=False).
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv


class SettingsError(RuntimeError):
    """Invalid API configuration."""


MIN_SECRET_LENGTH = 32


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    api_docs_enabled: bool = True
    ml_enabled: bool = True
    ml_preload: bool = True
    max_request_bytes: int = 65536
    # Authentication
    auth_secret_key: str | None = field(default=None, repr=False)
    auth_session_ttl_minutes: int = 480
    auth_cookie_secure: bool = True
    auth_cookie_name: str = "yt_session"
    auth_registration_enabled: bool = True
    auth_max_failed_logins: int = 5
    auth_lockout_minutes: int = 15

    def __post_init__(self):
        for origin in self.cors_origins:
            if origin == "*" or not origin.startswith(("http://", "https://")):
                raise SettingsError(f"CORS_ORIGINS must list explicit http(s) origins, got {origin!r}")
        if self.max_request_bytes <= 0:
            raise SettingsError("MAX_REQUEST_BYTES must be positive")
        if self.auth_secret_key is not None and len(self.auth_secret_key) < MIN_SECRET_LENGTH:
            raise SettingsError(f"AUTH_SECRET_KEY must be at least {MIN_SECRET_LENGTH} characters")
        if not 5 <= self.auth_session_ttl_minutes <= 7 * 24 * 60:
            raise SettingsError("AUTH_SESSION_TTL_MINUTES must be between 5 and 10080")
        if self.auth_max_failed_logins < 1 or self.auth_lockout_minutes < 1:
            raise SettingsError("AUTH_MAX_FAILED_LOGINS and AUTH_LOCKOUT_MINUTES must be positive")

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    def require_auth_secret(self) -> bytes:
        if not self.auth_secret_key:
            raise SettingsError(
                f"AUTH_SECRET_KEY is required (at least {MIN_SECRET_LENGTH} random characters). See .env.example."
            )
        return self.auth_secret_key.encode("utf-8")


def _bool(name, default):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    if value.strip().lower() in ("1", "true", "yes", "on"):
        return True
    if value.strip().lower() in ("0", "false", "no", "off"):
        return False
    raise SettingsError(f"{name} must be true or false")


def _int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        raise SettingsError(f"{name} must be an integer") from None


def load_settings() -> Settings:
    load_dotenv()  # existing environment variables take precedence over .env
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return Settings(
        app_env=app_env,
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        api_docs_enabled=_bool("API_DOCS_ENABLED", app_env == "development"),
        ml_enabled=_bool("ML_ENABLED", True),
        ml_preload=_bool("ML_PRELOAD", True),
        max_request_bytes=_int("MAX_REQUEST_BYTES", 65536),
        auth_secret_key=os.getenv("AUTH_SECRET_KEY") or None,
        auth_session_ttl_minutes=_int("AUTH_SESSION_TTL_MINUTES", 480),
        auth_cookie_secure=_bool("AUTH_COOKIE_SECURE", True),
        auth_registration_enabled=_bool("AUTH_REGISTRATION_ENABLED", True),
        auth_max_failed_logins=_int("AUTH_MAX_FAILED_LOGINS", 5),
        auth_lockout_minutes=_int("AUTH_LOCKOUT_MINUTES", 15),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
