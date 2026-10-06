"""Overview repository tests. Independent checks use different SQL formulations
(row_number() instead of DISTINCT ON, count(DISTINCT) instead of hash GROUP BY,
app.video_details as an independent source for the unfiltered case).
"""

import math
from dataclasses import replace
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from app.repositories import meta, overview
from app.repositories.common import (
    LATEST_PER_VIDEO,
    QueryParameterError,
    filtered_cte,
    pct_change,
    pts_change,
)
from app.repositories.filters import Filters, build_filters
from conftest import MAX_DATE, MIN_DATE, W30_START

# Independent "latest snapshot within the filtered dataset" via row_number().
INDEPENDENT_LATEST = """
    SELECT * FROM (
        SELECT s.*, row_number() OVER (
            PARTITION BY video_id ORDER BY trending_date DESC, view_count DESC NULLS LAST, country_code
        ) AS rn
        FROM app.trending_snapshots s WHERE {where}
    ) x WHERE rn = 1
"""


def independent_kpis(conn, start, end, countries=None, categories=None):
    where = "trending_date BETWEEN :s AND :e"
    params = {"s": start, "e": end}
    if countries:
        where += " AND country_code IN :countries"
        params["countries"] = tuple(countries)
    if categories:
        where += " AND category IN :categories"
        params["categories"] = tuple(categories)
    snap = conn.execute(text(
        f"SELECT count(*) AS vol, count(DISTINCT video_id) AS vids, count(DISTINCT channel_id) AS chans "
        f"FROM app.trending_snapshots WHERE {where}"), params).one()
    vid = conn.execute(text(
        f"SELECT count(*) AS n, sum(view_count) AS views, sum(like_count) AS likes, sum(comment_count) AS comments "
        f"FROM ({INDEPENDENT_LATEST.format(where=where)}) l"), params).one()
    return {
        "trending_volume": snap.vol,
        "unique_videos": snap.vids,
        "unique_channels": snap.chans,
        "views": int(vid.views or 0),
        "engagement_rate": (int(vid.likes) + int(vid.comments)) / int(vid.views) if vid.views else None,
        "latest_rows": vid.n,
    }


def assert_kpis_match(kpis, expected, key="value"):
    for name in ("trending_volume", "unique_videos", "unique_channels", "views"):
        assert kpis[name][key] == expected[name], name
    assert math.isclose(kpis["engagement_rate"][key], expected["engagement_rate"], rel_tol=1e-12)
    assert expected["latest_rows"] == expected["unique_videos"]


# ---------------------------------------------------
# "LATEST SNAPSHOT" SEMANTICS
# ---------------------------------------------------
def test_unfiltered_latest_equals_app_video_details(conn, all_time):
    """With no narrowing filters, the filtered-latest rule reproduces app.video_details exactly."""
    filtered, params = filtered_cte(all_time, "*")
    row = conn.execute(text(f"""
        WITH {filtered}, {LATEST_PER_VIDEO}
        SELECT count(*) AS n,
               count(*) FILTER (WHERE d.latest_trending_date = l.trending_date
                                  AND d.latest_country_code = l.country_code
                                  AND d.view_count IS NOT DISTINCT FROM l.view_count) AS matching
        FROM latest l JOIN app.video_details d ON d.video_id = l.video_id
    """), params).one()
    assert row.n == row.matching == 217115


def test_latest_is_within_filtered_dataset_not_global(conn):
    """With filters, 'latest' is the latest snapshot INSIDE the filters, which can differ
    from the global latest in app.video_details."""
    f = Filters(W30_START, MAX_DATE, countries=("IN",))
    filtered, params = filtered_cte(f, "*")
    row = conn.execute(text(f"""
        WITH {filtered}, {LATEST_PER_VIDEO}
        SELECT count(*) AS n,
               count(*) FILTER (WHERE l.country_code <> 'IN' OR l.trending_date NOT BETWEEN :start_date AND :end_date)
                   AS outside_filters,
               count(*) FILTER (WHERE d.latest_country_code <> l.country_code
                                   OR d.latest_trending_date <> l.trending_date) AS differs_from_global
        FROM latest l JOIN app.video_details d ON d.video_id = l.video_id
    """), params).one()
    assert row.n > 0
    assert row.outside_filters == 0
    assert row.differs_from_global > 0


# ---------------------------------------------------
# KPIs
# ---------------------------------------------------
def test_kpis_default_window_match_independent_sql(conn, w30):
    kpis = overview.get_kpis(conn, w30)
    assert_kpis_match(kpis, independent_kpis(conn, W30_START, MAX_DATE))
    assert kpis["period"] == {"start_date": W30_START, "end_date": MAX_DATE, "days": 30}


def test_previous_period_matches_independent_sql(conn, w30):
    kpis = overview.get_kpis(conn, w30)
    prev = kpis["previous_period"]
    assert (prev["start_date"], prev["end_date"], prev["available"]) == (date(2026, 8, 7), date(2026, 9, 5), True)
    assert_kpis_match(kpis, independent_kpis(conn, prev["start_date"], prev["end_date"]), key="previous")


def test_change_values_follow_definitions(conn, w30):
    kpis = overview.get_kpis(conn, w30)
    for name in ("trending_volume", "unique_videos", "unique_channels", "views"):
        m = kpis[name]
        assert math.isclose(m["change_pct"], (m["value"] - m["previous"]) / m["previous"] * 100)
    e = kpis["engagement_rate"]
    assert math.isclose(e["change_pts"], (e["value"] - e["previous"]) * 100)


def test_change_helpers():
    assert pct_change(110, 100) == pytest.approx(10.0)
    assert pct_change(5, 0) is None
    assert pct_change(5, None) is None
    assert pts_change(0.031, 0.030) == pytest.approx(0.1)
    assert pts_change(None, 0.03) is None


def test_country_filtered_kpis(conn, w30):
    f = replace(w30, countries=("IN",))
    kpis = overview.get_kpis(conn, f)
    assert kpis["trending_volume"]["value"] == 5870
    assert_kpis_match(kpis, independent_kpis(conn, W30_START, MAX_DATE, countries=["IN"]))


def test_country_and_category_filtered_kpis_via_build_filters(conn):
    f = build_filters(conn, countries=["in", "us"], categories=["music"])
    kpis = overview.get_kpis(conn, f)
    assert_kpis_match(kpis, independent_kpis(conn, W30_START, MAX_DATE, countries=["IN", "US"], categories=["Music"]))


def test_previous_period_unavailable_at_data_start(conn):
    kpis = overview.get_kpis(conn, Filters(MIN_DATE, MIN_DATE + timedelta(days=6)))
    assert kpis["previous_period"]["available"] is False
    for name in ("trending_volume", "unique_videos", "unique_channels", "views"):
        assert kpis[name]["previous"] is None and kpis[name]["change_pct"] is None
    assert kpis["engagement_rate"]["change_pts"] is None


def test_all_time_kpis_equal_global_totals(conn, all_time):
    kpis = overview.get_kpis(conn, all_time)
    totals = conn.execute(text(
        "SELECT count(*) AS n, sum(view_count) AS v, sum(like_count) AS l, sum(comment_count) AS c "
        "FROM app.video_details")).one()
    channels = conn.execute(text("SELECT count(DISTINCT channel_id) FROM app.trending_snapshots")).scalar_one()
    assert kpis["trending_volume"]["value"] == 1135886
    assert kpis["unique_videos"]["value"] == totals.n == 217115
    assert kpis["views"]["value"] == int(totals.v)
    assert kpis["unique_channels"]["value"] == channels
    assert math.isclose(kpis["engagement_rate"]["value"], (int(totals.l) + int(totals.c)) / int(totals.v), rel_tol=1e-12)
    assert kpis["previous_period"]["available"] is False


def test_single_day_window(conn):
    kpis = overview.get_kpis(conn, Filters(MAX_DATE, MAX_DATE))
    day_rows = conn.execute(text("SELECT count(*) FROM app.trending_snapshots WHERE trending_date = :d"),
                            {"d": MAX_DATE}).scalar_one()
    assert kpis["trending_volume"]["value"] == day_rows
    assert kpis["previous_period"]["start_date"] == kpis["previous_period"]["end_date"] == MAX_DATE - timedelta(days=1)


def test_empty_lists_equal_explicit_all(conn, w30):
    every = replace(w30, countries=tuple(c["code"] for c in meta.get_countries(conn)),
                    categories=tuple(meta.get_categories(conn)))
    a, b = overview.get_kpis(conn, w30), overview.get_kpis(conn, every)
    for name in ("trending_volume", "unique_videos", "unique_channels", "views", "engagement_rate"):
        assert a[name]["value"] == b[name]["value"], name


# ---------------------------------------------------
# DAILY VOLUME
# ---------------------------------------------------
def test_daily_volume_zero_filled_and_matches_independent_sql(conn, w30):
    result = overview.get_daily_volume(conn, w30)
    points = result["series"][0]["points"]
    assert result["split_by"] is None and result["series"][0]["key"] is None
    assert [p["date"] for p in points] == [W30_START + timedelta(days=i) for i in range(30)]

    expected = {
        r.trending_date: (r.vol, r.vids)
        for r in conn.execute(text(
            "SELECT trending_date, count(*) AS vol, count(DISTINCT video_id) AS vids FROM app.trending_snapshots "
            "WHERE trending_date BETWEEN :s AND :e GROUP BY trending_date"), {"s": W30_START, "e": MAX_DATE})
    }
    assert {p["date"]: (p["trending_volume"], p["unique_videos"]) for p in points} == expected
    assert sum(p["trending_volume"] for p in points) == overview.get_kpis(conn, w30)["trending_volume"]["value"]


def test_daily_volume_zero_fill_for_sparse_category(conn, all_time):
    points = overview.get_daily_volume(conn, replace(all_time, categories=("Nonprofits & Activism",)))["series"][0]["points"]
    assert len(points) == (MAX_DATE - MIN_DATE).days + 1 == 724  # every calendar day
    assert sum(p["trending_volume"] for p in points) == 13
    active_days = conn.execute(text(
        "SELECT count(DISTINCT trending_date) FROM app.trending_snapshots WHERE category = 'Nonprofits & Activism'"
    )).scalar_one()
    assert sum(1 for p in points if p["trending_volume"] == 0) == 724 - active_days


def test_daily_volume_includes_dates_missing_from_data(conn, all_time):
    """8 calendar days have no snapshots in any country (716 distinct dates over 724 days);
    they appear as explicit zeros, not gaps."""
    points = {p["date"]: p for p in overview.get_daily_volume(conn, all_time)["series"][0]["points"]}
    assert len(points) == 724
    for missing in (date(2024, 10, 24), date(2025, 4, 18), date(2025, 10, 14), date(2026, 6, 10), date(2026, 6, 11),
                    date(2026, 6, 12), date(2026, 6, 26), date(2026, 8, 10)):
        assert points[missing]["trending_volume"] == points[missing]["unique_videos"] == 0
    assert sum(1 for p in points.values() if p["trending_volume"] > 0) == 716


def test_daily_split_by_country_sums_to_unsplit(conn, w30):
    unsplit = {p["date"]: p["trending_volume"] for p in overview.get_daily_volume(conn, w30)["series"][0]["points"]}
    split = overview.get_daily_volume(conn, w30, split_by="country")
    assert split["split_by"] == "country"
    assert [s["key"] for s in split["series"]] == ["AU", "CA", "GB", "IE", "IN", "NZ", "SG", "US", "ZA"]
    for d, vol in unsplit.items():
        assert sum(next(p["trending_volume"] for p in s["points"] if p["date"] == d) for s in split["series"]) == vol


def test_daily_split_by_category(conn, w30):
    split = overview.get_daily_volume(conn, w30, split_by="category")
    present = conn.execute(text(
        "SELECT DISTINCT category FROM app.trending_snapshots WHERE trending_date BETWEEN :s AND :e"),
        {"s": W30_START, "e": MAX_DATE}).scalars().all()
    assert [s["key"] for s in split["series"]] == sorted(present)
    assert all(len(s["points"]) == 30 for s in split["series"])


@pytest.mark.parametrize("split_by", ["channel", "country_code; DROP TABLE x", "", 1])
def test_daily_invalid_split_rejected(conn, w30, split_by):
    with pytest.raises(QueryParameterError) as exc:
        overview.get_daily_volume(conn, w30, split_by=split_by)
    assert exc.value.field == "split_by"
