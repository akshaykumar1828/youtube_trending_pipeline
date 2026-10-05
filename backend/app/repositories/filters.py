"""Dashboard filters: date range, countries, categories.

Allowed values are validated against PostgreSQL metadata (app.trending_snapshots),
never a hardcoded list. Filters render to a fixed SQL condition string with
bound parameters only; user input never becomes SQL text.

Rules:
  - default range: DEFAULT_WINDOW_DAYS days ending at the database max date
  - dates outside [min date, max date] are rejected
  - an empty / missing country or category list means "all"
  - country codes are normalised to uppercase
  - categories match stored names case-insensitively
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.engine import Connection

from . import meta

DEFAULT_WINDOW_DAYS = 30


class FilterValidationError(ValueError):
    def __init__(self, field, message):
        self.field = field
        super().__init__(f"{field}: {message}")


@dataclass(frozen=True)
class Filters:
    start_date: date
    end_date: date
    countries: tuple[str, ...] = ()   # empty = all countries
    categories: tuple[str, ...] = ()  # empty = all categories

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    def previous_period(self) -> tuple[date, date]:
        """The immediately preceding period of equal length."""
        prev_end = self.start_date - timedelta(days=1)
        return prev_end - timedelta(days=self.days - 1), prev_end

    def sql_conditions(self) -> tuple[str, dict]:
        """WHERE conditions for app.trending_snapshots and their bound parameters."""
        clauses = ["trending_date BETWEEN :start_date AND :end_date"]
        params = {"start_date": self.start_date, "end_date": self.end_date}
        if self.countries:
            clauses.append("country_code = ANY(:countries)")
            params["countries"] = list(self.countries)
        if self.categories:
            clauses.append("category = ANY(:categories)")
            params["categories"] = list(self.categories)
        return " AND ".join(clauses), params


def build_filters(conn: Connection, start_date=None, end_date=None, countries=None, categories=None) -> Filters:
    min_date, max_date = meta.get_date_range(conn)

    end = end_date or max_date
    _check_date("end_date", end, min_date, max_date)
    start = start_date or max(min_date, end - timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    _check_date("start_date", start, min_date, max_date)
    if start > end:
        raise FilterValidationError("start_date", f"{start} is after end_date {end}")

    return Filters(
        start_date=start,
        end_date=end,
        countries=_normalise_countries(conn, countries),
        categories=_normalise_categories(conn, categories),
    )


def _check_date(field, value, min_date, max_date):
    if not isinstance(value, date):
        raise FilterValidationError(field, "must be a date")
    if not min_date <= value <= max_date:
        raise FilterValidationError(field, f"{value} is outside the available range {min_date} to {max_date}")


def _as_list(field, values):
    if values is None:
        return []
    if isinstance(values, str) or not all(isinstance(v, str) for v in values):
        raise FilterValidationError(field, "must be a list of strings")
    return values


def _normalise_countries(conn, countries):
    requested = [c.strip().upper() for c in _as_list("countries", countries)]
    if not requested:
        return ()
    valid = {c["code"] for c in meta.get_countries(conn)}
    unknown = sorted(set(requested) - valid)
    if unknown:
        raise FilterValidationError("countries", f"unknown {unknown}; valid: {', '.join(sorted(valid))}")
    return tuple(sorted(set(requested)))


def _normalise_categories(conn, categories):
    requested = [c.strip() for c in _as_list("categories", categories)]
    if not requested:
        return ()
    by_lower = {c.lower(): c for c in meta.get_categories(conn)}
    unknown = sorted({c for c in requested if c.lower() not in by_lower})
    if unknown:
        raise FilterValidationError("categories", f"unknown {unknown}; valid: {', '.join(sorted(by_lower.values()))}")
    return tuple(sorted({by_lower[c.lower()] for c in requested}))
