"""Database settings read from the environment / .env (Phase 0 contract).

Application queries use the read-only role (DB_APP_RO_USER / DB_APP_RO_PASSWORD).
The admin credentials (DB_USER / DB_PASSWORD) are only for administrative
operations such as migrations; the application engine never uses them.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv
from sqlalchemy.engine import URL


class ConfigError(RuntimeError):
    """Raised when required database settings are missing or unsafe."""


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    name: str
    user: str
    password: str = field(repr=False)

    @property
    def url(self) -> URL:
        # URL.create escapes special characters; str(url) masks the password.
        return URL.create(
            "postgresql+psycopg2",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.name,
        )


def _require(*names):
    load_dotenv()  # existing environment variables take precedence over .env
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        raise ConfigError(f"Missing required environment variables: {', '.join(missing)}. See .env.example.")


def _settings(user_var, password_var):
    _require("DB_NAME", user_var, password_var)
    return DatabaseSettings(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        name=os.environ["DB_NAME"],
        user=os.environ[user_var],
        password=os.environ[password_var],
    )


def app_settings() -> DatabaseSettings:
    """Settings for application queries (read-only role)."""
    settings = _settings("DB_APP_RO_USER", "DB_APP_RO_PASSWORD")
    if settings.user == os.getenv("DB_USER", "postgres"):
        raise ConfigError("DB_APP_RO_USER must be the read-only application role, not the admin user.")
    return settings


def auth_settings() -> DatabaseSettings:
    """Settings for authentication reads/writes (role yt_auth_rw: `auth` schema only)."""
    settings = _settings("DB_AUTH_USER", "DB_AUTH_PASSWORD")
    if settings.user == os.getenv("DB_USER", "postgres"):
        raise ConfigError("DB_AUTH_USER must be the dedicated auth role, not the admin user.")
    return settings


def admin_settings() -> DatabaseSettings:
    """Settings for administrative operations only (migrations). Not used by the app engine."""
    return _settings("DB_USER", "DB_PASSWORD")
