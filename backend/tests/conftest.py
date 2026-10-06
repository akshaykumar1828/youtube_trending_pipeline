"""Shared fixtures for backend integration tests (run as the read-only role yt_app_ro)."""

import sys
from datetime import date
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db.engine import dispose_engine, get_connection  # noqa: E402
from app.repositories.filters import Filters  # noqa: E402

MIN_DATE = date(2024, 10, 12)
MAX_DATE = date(2026, 10, 5)
W30_START = date(2026, 9, 6)


@pytest.fixture(scope="session", autouse=True)
def _dispose_engine_at_end():
    yield
    dispose_engine()


@pytest.fixture
def conn():
    with get_connection() as c:
        yield c


@pytest.fixture
def w30():
    """Default dashboard window: 30 days ending at the database max date, no country/category filter."""
    return Filters(W30_START, MAX_DATE)


@pytest.fixture
def all_time():
    """Full data range, no country/category filter (filtered latest == global latest)."""
    return Filters(MIN_DATE, MAX_DATE)
