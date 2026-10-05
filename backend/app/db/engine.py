"""Read-only SQLAlchemy Core engine for application queries.

The engine is created lazily on first use (importing this module never
connects), always as the read-only application role. This module never runs
migrations, refreshes materialized views, or writes to the database.
"""

from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from .config import app_settings

APPLICATION_NAME = "yt_trending_app"
STATEMENT_TIMEOUT_MS = 15000


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(
        app_settings().url,
        pool_size=5,
        max_overflow=5,          # at most 10 connections; the role allows 20
        pool_timeout=10,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 5,
            "application_name": APPLICATION_NAME,
            # Read-only is also the role default; repeated here as a second guard.
            "options": f"-c default_transaction_read_only=on -c statement_timeout={STATEMENT_TIMEOUT_MS}",
        },
    )


@contextmanager
def get_connection():
    """Yield a pooled read-only connection. Nothing is committed; exiting rolls back."""
    with get_engine().connect() as conn:
        yield conn


def dispose_engine() -> None:
    """Close pooled connections and drop the cached engine (shutdown / tests)."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
