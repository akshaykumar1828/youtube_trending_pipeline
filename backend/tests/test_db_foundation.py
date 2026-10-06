"""Integration tests for the database foundation (backend/app/db, backend/app/repositories).

Runs against youtube_trending_db as the read-only role yt_app_ro.
Read-only: write attempts are expected to fail and run inside rolled-back transactions.
"""

import ast
import os
import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.db import config  # noqa: E402
from app.db.config import ConfigError, DatabaseSettings, app_settings  # noqa: E402
from app.db.engine import dispose_engine, get_connection, get_engine  # noqa: E402
from app.repositories import meta  # noqa: E402
from app.repositories.filters import FilterValidationError, Filters, build_filters  # noqa: E402

INSUFFICIENT_PRIVILEGE = "42501"
READ_ONLY_TRANSACTION = "25006"
EXPECTED_COUNTRIES = ["AU", "CA", "GB", "IE", "IN", "NZ", "SG", "US", "ZA"]


@pytest.fixture(scope="module", autouse=True)
def _engine_lifecycle():
    yield
    dispose_engine()


@pytest.fixture
def conn():
    with get_connection() as c:
        yield c


def _pgcode(exc_info):
    return exc_info.value.orig.pgcode


# ---------------------------------------------------
# CONNECTION + PRIVILEGES
# ---------------------------------------------------
def test_connects_as_read_only_role(conn):
    row = conn.execute(text(
        "SELECT current_user, current_setting('default_transaction_read_only'), current_setting('application_name')"
    )).one()
    assert tuple(row) == ("yt_app_ro", "on", "yt_trending_app")


def test_reads_trending_snapshots(conn):
    assert conn.execute(text("SELECT count(*) FROM app.trending_snapshots")).scalar_one() == 1135886


def test_reads_video_details(conn):
    assert conn.execute(text("SELECT count(*) FROM app.video_details")).scalar_one() == 217115


@pytest.mark.parametrize("relation", [
    "public.youtube_trending_in",
    "public.youtube_trending_all",
    "public.youtube_trending_all_mat",
])
def test_public_raw_and_legacy_access_denied(conn, relation):
    with pytest.raises(DBAPIError) as exc:
        conn.execute(text(f"SELECT 1 FROM {relation} LIMIT 1"))  # fixed test identifiers, not user input
    assert _pgcode(exc) == INSUFFICIENT_PRIVILEGE


def test_schema_migrations_access_denied(conn):
    with pytest.raises(DBAPIError) as exc:
        conn.execute(text("SELECT * FROM app.schema_migrations"))
    assert _pgcode(exc) == INSUFFICIENT_PRIVILEGE


def test_write_rejected_by_read_only_session(conn):
    with pytest.raises(DBAPIError) as exc:
        conn.execute(text("INSERT INTO app.schema_migrations VALUES ('999', 'x', 'x')"))
    assert _pgcode(exc) == READ_ONLY_TRANSACTION


def test_write_rejected_by_privileges_even_if_read_write(conn):
    conn.execute(text("SET TRANSACTION READ WRITE"))
    with pytest.raises(DBAPIError) as exc:
        conn.execute(text("DELETE FROM public.youtube_trending_in WHERE false"))
    assert _pgcode(exc) == INSUFFICIENT_PRIVILEGE


# ---------------------------------------------------
# ENGINE + CONFIG
# ---------------------------------------------------
def test_engine_uses_app_role_and_pool_settings():
    engine = get_engine()
    assert engine.url.username == os.environ["DB_APP_RO_USER"] == "yt_app_ro"
    assert engine.url.username != os.getenv("DB_USER", "postgres")
    assert engine.pool._pre_ping is True
    assert engine.pool.size() == 5


def test_app_user_must_not_be_admin(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda: None)
    monkeypatch.setenv("DB_APP_RO_USER", os.getenv("DB_USER", "postgres"))
    with pytest.raises(ConfigError, match="not the admin user"):
        app_settings()


def test_missing_settings_named_without_values(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda: None)
    monkeypatch.delenv("DB_APP_RO_PASSWORD")
    with pytest.raises(ConfigError, match="DB_APP_RO_PASSWORD") as exc:
        app_settings()
    assert os.environ["DB_PASSWORD"] not in str(exc.value)


def test_no_credentials_in_reprs_or_errors():
    secrets = [os.environ["DB_APP_RO_PASSWORD"], os.environ["DB_PASSWORD"]]
    settings = app_settings()
    rendered = [repr(settings), str(settings), str(settings.url), repr(settings.url), repr(get_engine())]

    wrong = DatabaseSettings(settings.host, settings.port, settings.name, settings.user, "wrong-password-for-test")
    from sqlalchemy import create_engine
    bad_engine = create_engine(wrong.url, connect_args={"connect_timeout": 5})
    with pytest.raises(DBAPIError) as exc:
        bad_engine.connect()
    bad_engine.dispose()
    rendered.append(str(exc.value))

    for text_ in rendered:
        for secret in secrets + ["wrong-password-for-test"]:
            assert secret not in text_


# ---------------------------------------------------
# META REPOSITORY
# ---------------------------------------------------
def test_get_countries(conn):
    countries = meta.get_countries(conn)
    assert [c["code"] for c in countries] == EXPECTED_COUNTRIES
    assert {"code": "IN", "name": "India"} in countries


def test_get_min_and_max_date(conn):
    assert meta.get_min_date(conn) == date(2024, 10, 12)
    assert meta.get_max_date(conn) == date(2026, 10, 5)
    assert meta.get_date_range(conn) == (date(2024, 10, 12), date(2026, 10, 5))


def test_get_categories_from_database(conn):
    categories = meta.get_categories(conn)
    independent = list(conn.execute(text(
        "SELECT category FROM app.trending_snapshots GROUP BY category ORDER BY category"
    )).scalars())
    assert categories == independent
    assert len(categories) == 17
    assert "Unknown" in categories and "Gaming" in categories


def test_no_hardcoded_categories_or_countries(conn):
    literals = set()
    for f in ("meta.py", "filters.py"):
        tree = ast.parse((BACKEND / "app" / "repositories" / f).read_text(encoding="utf-8"))
        literals |= {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    values = meta.get_categories(conn) + [c["code"] for c in meta.get_countries(conn)] + ["India", "Australia"]
    assert not literals & set(values)


# ---------------------------------------------------
# FILTERS
# ---------------------------------------------------
def test_default_filters_are_30_days_ending_at_max_date(conn):
    f = build_filters(conn)
    assert (f.start_date, f.end_date, f.days) == (date(2026, 9, 6), date(2026, 10, 5), 30)
    assert f.countries == () and f.categories == ()


def test_default_start_never_before_min_date(conn):
    f = build_filters(conn, end_date=date(2024, 10, 20))
    assert f.start_date == date(2024, 10, 12)


def test_previous_period_is_immediately_preceding_equal_length(conn):
    f = build_filters(conn)
    assert f.previous_period() == (date(2026, 8, 7), date(2026, 9, 5))
    g = build_filters(conn, start_date=date(2025, 1, 10), end_date=date(2025, 1, 16))
    assert g.previous_period() == (date(2025, 1, 3), date(2025, 1, 9))


@pytest.mark.parametrize("kwargs, field", [
    ({"start_date": date(2025, 6, 2), "end_date": date(2025, 6, 1)}, "start_date"),
    ({"start_date": date(2024, 10, 11)}, "start_date"),
    ({"end_date": date(2026, 10, 6)}, "end_date"),
    ({"end_date": "2026-01-05"}, "end_date"),
])
def test_invalid_dates_rejected(conn, kwargs, field):
    with pytest.raises(FilterValidationError) as exc:
        build_filters(conn, **kwargs)
    assert exc.value.field == field


def test_countries_normalised_and_validated(conn):
    f = build_filters(conn, countries=[" in", "US", "us"])
    assert f.countries == ("IN", "US")
    for bad in (["SG", "XX"], ["IN'; DROP TABLE app.video_details;--"], "IN", [1]):
        with pytest.raises(FilterValidationError) as exc:
            build_filters(conn, countries=bad)
        assert exc.value.field == "countries"


def test_categories_case_insensitive_and_validated(conn):
    f = build_filters(conn, categories=["gaming", "NEWS & POLITICS", "Gaming"])
    assert f.categories == ("Gaming", "News & Politics")
    with pytest.raises(FilterValidationError) as exc:
        build_filters(conn, categories=["Cooking"])
    assert exc.value.field == "categories"


def test_empty_lists_mean_all(conn):
    assert build_filters(conn, countries=[], categories=[]) == build_filters(conn)
    sql, params = build_filters(conn, countries=[]).sql_conditions()
    assert "country_code" not in sql and "category" not in sql


def test_sql_conditions_use_only_bound_parameters(conn):
    f = build_filters(conn, countries=["IN"], categories=["Music"])
    sql, params = f.sql_conditions()
    assert sql == ("trending_date BETWEEN :start_date AND :end_date"
                   " AND country_code = ANY(:countries) AND category = ANY(:categories)")
    assert params == {"start_date": date(2026, 9, 6), "end_date": date(2026, 10, 5),
                      "countries": ["IN"], "categories": ["Music"]}
    assert "IN" not in sql.replace("BETWEEN", "") and "Music" not in sql


def test_filtered_query_executes_with_expected_result(conn):
    sql, params = build_filters(conn, countries=["in"]).sql_conditions()
    volume = conn.execute(text(f"SELECT count(*) FROM app.trending_snapshots WHERE {sql}"), params).scalar_one()
    assert volume == 5870  # IN, 2026-09-06..2026-10-05 (independent SQL count)


def test_filters_dataclass_is_immutable():
    f = Filters(date(2025, 1, 1), date(2025, 1, 31))
    with pytest.raises(Exception):
        f.start_date = date(2025, 2, 1)
