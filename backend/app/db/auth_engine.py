"""SQLAlchemy engine for authentication (role yt_auth_rw, `auth` schema only).

Kept separate from the read-only analytics engine (app/db/engine.py): analytics queries
never get write access, and authentication never gets access to analytics or raw data.
"""

from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from .config import auth_settings


@lru_cache(maxsize=1)
def get_auth_engine() -> Engine:
    return create_engine(
        auth_settings().url,
        pool_size=5,
        max_overflow=5,
        pool_timeout=10,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5, "application_name": "yt_trending_auth"},
    )


@contextmanager
def get_auth_connection():
    """Pooled connection. Callers commit explicitly; anything uncommitted is rolled back."""
    with get_auth_engine().connect() as conn:
        yield conn


def dispose_auth_engine() -> None:
    if get_auth_engine.cache_info().currsize:
        get_auth_engine().dispose()
    get_auth_engine.cache_clear()
