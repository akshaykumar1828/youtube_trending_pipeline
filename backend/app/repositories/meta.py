"""Read-only metadata queries against app.trending_snapshots.

Countries, categories and date boundaries all come from PostgreSQL; nothing is
hardcoded and today's date is never assumed (the data ends at its own max date).
Functions take a Connection; the caller owns the connection's lifetime.
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Connection

_COUNTRIES = text("""
    SELECT DISTINCT country_code, country_name
    FROM app.trending_snapshots
    ORDER BY country_code
""")

_CATEGORIES = text("""
    SELECT DISTINCT category
    FROM app.trending_snapshots
    ORDER BY category
""")

_DATE_RANGE = text("""
    SELECT min(trending_date) AS min_date, max(trending_date) AS max_date
    FROM app.trending_snapshots
""")


def get_countries(conn: Connection) -> list[dict]:
    """[{"code": "AU", "name": "Australia"}, ...] sorted by code."""
    return [{"code": r.country_code, "name": r.country_name} for r in conn.execute(_COUNTRIES)]


def get_categories(conn: Connection) -> list[str]:
    """Distinct stored category names, sorted (includes 'Unknown' for missing categories)."""
    return list(conn.execute(_CATEGORIES).scalars())


def get_date_range(conn: Connection) -> tuple[date, date]:
    """(min trending date, max trending date) in the data."""
    row = conn.execute(_DATE_RANGE).one()
    return row.min_date, row.max_date


def get_min_date(conn: Connection) -> date:
    return get_date_range(conn)[0]


def get_max_date(conn: Connection) -> date:
    return get_date_range(conn)[1]
