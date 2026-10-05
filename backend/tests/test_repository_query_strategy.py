"""Regression tests for the optimized query strategy.

1. The two-step "latest snapshot within the filtered dataset" (hash max-date, then
   tie-break among same-date candidates) selects exactly the rows of a full
   ORDER BY trending_date DESC, view_count DESC NULLS LAST, country_code.
2. The per-country latest selection yields exactly one row per (country, video).
3. All-time queries complete under the engine's normal 15 s statement timeout
   (no session tuning), as yt_app_ro.
"""

import pytest
from sqlalchemy import text

from app.repositories import analytics, overview, videos
from app.repositories.common import LATEST_PER_COUNTRY_VIDEO, LATEST_PER_VIDEO, filtered_cte
from app.repositories.filters import Filters
from conftest import MAX_DATE, W30_START

FULL_SORT_LATEST = """
    SELECT video_id, trending_date, country_code, view_count FROM (
        SELECT s.*, row_number() OVER (
            PARTITION BY video_id ORDER BY trending_date DESC, view_count DESC NULLS LAST, country_code) AS rn
        FROM app.trending_snapshots s WHERE {conditions}
    ) x WHERE rn = 1
"""


@pytest.mark.parametrize("filters", [
    Filters(W30_START, MAX_DATE),
    Filters(W30_START, MAX_DATE, countries=("GB", "IE", "US")),       # many same-day cross-country ties
    Filters(W30_START, MAX_DATE, countries=("IN", "US"), categories=("Music",)),
    Filters(MAX_DATE, MAX_DATE),
], ids=["30d", "GB+IE+US", "IN+US+Music", "single-day"])
def test_two_step_latest_equals_full_sort(conn, filters):
    filtered, params = filtered_cte(filters, "*")
    conditions, _ = filters.sql_conditions()
    optimized = conn.execute(text(
        f"WITH {filtered}, {LATEST_PER_VIDEO} SELECT video_id, trending_date, country_code, view_count FROM latest"
    ), params).all()
    full_sort = conn.execute(text(FULL_SORT_LATEST.format(conditions=conditions)), params).all()
    assert len(optimized) > 0
    assert sorted(map(tuple, optimized)) == sorted(map(tuple, full_sort))


def test_tie_cases_exist_in_regression_window(conn):
    """Guard: the GB+IE+US window really contains same-day multi-country ties."""
    ties = conn.execute(text("""
        SELECT count(*) FROM (
            SELECT video_id FROM app.trending_snapshots
            WHERE trending_date BETWEEN :s AND :e AND country_code IN ('GB', 'IE', 'US')
            GROUP BY video_id, trending_date HAVING count(*) > 1) t
    """), {"s": W30_START, "e": MAX_DATE}).scalar_one()
    assert ties > 1000


def test_country_latest_one_row_per_country_video(conn, w30):
    filtered, params = filtered_cte(w30, "*")
    row = conn.execute(text(f"""
        WITH {filtered}, {LATEST_PER_COUNTRY_VIDEO}
        SELECT count(*) AS n, count(DISTINCT (country_code, video_id)) AS pairs FROM country_latest
    """), params).one()
    expected = conn.execute(text(
        "SELECT count(DISTINCT (country_code, video_id)) FROM app.trending_snapshots "
        "WHERE trending_date BETWEEN :s AND :e"), {"s": W30_START, "e": MAX_DATE}).scalar_one()
    assert row.n == row.pairs == expected


# ---------------------------------------------------
# ALL-TIME RELIABILITY (normal engine settings: 15 s statement timeout, default work_mem)
# ---------------------------------------------------
def test_engine_settings_unchanged(conn):
    assert conn.execute(text("SHOW statement_timeout")).scalar_one() == "15s"
    assert conn.execute(text("SHOW work_mem")).scalar_one() == "4MB"


@pytest.mark.parametrize("name, fn", [
    ("get_kpis", lambda c, f: overview.get_kpis(c, f)),
    ("get_category_performance", lambda c, f: analytics.get_category_performance(c, f)),
    ("get_country_performance", lambda c, f: analytics.get_country_performance(c, f)),
    ("get_engagement_analysis", lambda c, f: analytics.get_engagement_analysis(c, f)),
    ("get_top_channels", lambda c, f: analytics.get_top_channels(c, f)),
    ("list_videos", lambda c, f: videos.list_videos(c, f)),
    ("list_videos_days_sort", lambda c, f: videos.list_videos(c, f, sort="days_on_trending")),
    ("list_videos_search", lambda c, f: videos.list_videos(c, f, search="cricket")),
])
def test_all_time_completes_under_statement_timeout(conn, all_time, name, fn):
    assert fn(conn, all_time) is not None


def test_all_time_list_videos_totals(conn, all_time):
    assert videos.list_videos(conn, all_time)["total"] == 99402
    last = videos.list_videos(conn, all_time, page=3977)
    assert len(last["items"]) == 99402 - 3976 * 25
