"""Analytics repository tests, validated against independently written SQL
(row_number() latest selection, count(DISTINCT), numpy percentiles, exact fractions).
"""

import math
from dataclasses import replace
from fractions import Fraction

import numpy as np
import pytest
from sqlalchemy import text

from app.repositories import analytics, overview
from app.repositories.common import QueryParameterError
from conftest import MAX_DATE, W30_START

WINDOW = {"s": W30_START, "e": MAX_DATE}

LATEST_W30 = """
    SELECT * FROM (
        SELECT s.*, row_number() OVER (
            PARTITION BY video_id ORDER BY trending_date DESC, view_count DESC NULLS LAST, country_code) AS rn
        FROM app.trending_snapshots s WHERE trending_date BETWEEN :s AND :e
    ) x WHERE rn = 1
"""

LATEST_PER_COUNTRY_W30 = """
    SELECT * FROM (
        SELECT s.*, row_number() OVER (
            PARTITION BY country_code, video_id ORDER BY trending_date DESC, view_count DESC NULLS LAST) AS rn
        FROM app.trending_snapshots s WHERE trending_date BETWEEN :s AND :e
    ) x WHERE rn = 1
"""


# ---------------------------------------------------
# CATEGORY
# ---------------------------------------------------
def test_category_totals_reconcile_with_kpis(conn, w30):
    rows = analytics.get_category_performance(conn, w30)
    kpis = overview.get_kpis(conn, w30)
    assert sum(r["trending_volume"] for r in rows) == kpis["trending_volume"]["value"]
    assert sum(r["unique_videos"] for r in rows) == kpis["unique_videos"]["value"]  # video-level: one category each
    assert sum(r["views"] for r in rows) == kpis["views"]["value"]
    assert math.isclose(sum(r["volume_share_pct"] for r in rows), 100.0, rel_tol=1e-9)
    assert [r["trending_volume"] for r in rows] == sorted((r["trending_volume"] for r in rows), reverse=True)


def test_category_matches_independent_sql(conn, w30):
    gaming = next(r for r in analytics.get_category_performance(conn, w30) if r["category"] == "Gaming")
    volume = conn.execute(text(
        "SELECT count(*) FROM app.trending_snapshots WHERE trending_date BETWEEN :s AND :e AND category = 'Gaming'"),
        WINDOW).scalar_one()
    vid = conn.execute(text(
        f"SELECT count(*) AS n, sum(view_count) AS v, sum(like_count) AS l, sum(comment_count) AS c "
        f"FROM ({LATEST_W30}) x WHERE category = 'Gaming'"), WINDOW).one()
    assert gaming["trending_volume"] == volume
    assert gaming["unique_videos"] == vid.n
    assert gaming["views"] == int(vid.v)
    assert math.isclose(gaming["engagement_rate"], (int(vid.l) + int(vid.c)) / int(vid.v), rel_tol=1e-12)


def test_category_filter_limits_rows(conn, w30):
    rows = analytics.get_category_performance(conn, replace(w30, categories=("Music", "Sports")))
    assert sorted(r["category"] for r in rows) == ["Music", "Sports"]


# ---------------------------------------------------
# COUNTRY
# ---------------------------------------------------
def test_country_matches_independent_sql(conn, w30):
    rows = {r["country_code"]: r for r in analytics.get_country_performance(conn, w30)}
    snap = {r.country_code: r for r in conn.execute(text(
        "SELECT country_code, count(*) AS vol, count(DISTINCT video_id) AS vids FROM app.trending_snapshots "
        "WHERE trending_date BETWEEN :s AND :e GROUP BY country_code"), WINDOW)}
    latest = {r.country_code: r for r in conn.execute(text(
        f"SELECT country_code, sum(view_count) AS v, sum(like_count) AS l, sum(comment_count) AS c "
        f"FROM ({LATEST_PER_COUNTRY_W30}) x GROUP BY country_code"), WINDOW)}
    assert set(rows) == set(snap) == {"AU", "CA", "GB", "IE", "IN", "NZ", "SG", "US", "ZA"}
    for code, r in rows.items():
        assert r["trending_volume"] == snap[code].vol
        assert r["unique_videos"] == snap[code].vids
        assert r["views_of_trending_videos"] == int(latest[code].v)
        expected_rate = (int(latest[code].l) + int(latest[code].c)) / int(latest[code].v)
        assert math.isclose(r["engagement_rate"], expected_rate, rel_tol=1e-12)
    assert rows["IN"]["country_name"] == "India"


def test_country_level_metrics_are_not_additive(conn, w30):
    rows = analytics.get_country_performance(conn, w30)
    kpis = overview.get_kpis(conn, w30)
    assert sum(r["trending_volume"] for r in rows) == kpis["trending_volume"]["value"]   # snapshot-level: additive
    assert sum(r["unique_videos"] for r in rows) > kpis["unique_videos"]["value"]        # multi-country videos
    assert sum(r["views_of_trending_videos"] for r in rows) > kpis["views"]["value"]     # global counts repeated


# ---------------------------------------------------
# ENGAGEMENT
# ---------------------------------------------------
@pytest.fixture
def latest_counts(conn):
    return conn.execute(text(
        f"SELECT video_id, category, view_count, like_count, comment_count FROM ({LATEST_W30}) x"), WINDOW).all()


def test_engagement_totals_equal_kpis(conn, w30):
    e = analytics.get_engagement_analysis(conn, w30)
    kpis = overview.get_kpis(conn, w30)
    assert e["totals"]["videos"] == kpis["unique_videos"]["value"]
    assert e["totals"]["views"] == kpis["views"]["value"]
    assert math.isclose(e["totals"]["engagement_rate"], kpis["engagement_rate"]["value"], rel_tol=1e-12)


def test_engagement_distribution_matches_numpy(conn, w30, latest_counts):
    e = analytics.get_engagement_analysis(conn, w30)
    rates = [(r.like_count + r.comment_count) / r.view_count for r in latest_counts if r.view_count]
    assert e["totals"]["videos_without_views"] == sum(1 for r in latest_counts if not r.view_count)
    for key, q in (("p25", 25), ("p50", 50), ("p75", 75), ("p90", 90)):
        assert math.isclose(e["distribution"][key], float(np.percentile(rates, q)), rel_tol=1e-9)


def test_engagement_histogram_matches_exact_bucketing(conn, w30, latest_counts):
    hist = analytics.get_engagement_analysis(conn, w30)["histogram"]
    assert len(hist) == 11 and hist[0]["lower_pct"] == 0 and hist[-1] == {**hist[-1], "lower_pct": 10.0, "upper_pct": None}

    exact = [Fraction(r.like_count + r.comment_count, r.view_count) for r in latest_counts if r.view_count]
    expected = [0] * 11
    for rate in exact:
        expected[min(math.floor(rate * 100), 10)] += 1
    # Rates exactly on a bucket edge (e.g. 3/100) may fall either side through float rounding.
    on_edge = sum(1 for rate in exact if (rate * 100).denominator == 1 and rate * 100 <= 10)
    assert sum(h["videos"] for h in hist) == len(exact)
    assert sum(abs(h["videos"] - x) for h, x in zip(hist, expected)) <= 2 * on_edge


def test_engagement_by_category_matches_numpy(conn, w30, latest_counts):
    by_cat = {c["category"]: c for c in analytics.get_engagement_analysis(conn, w30)["by_category"]}
    music = [(r.like_count + r.comment_count) / r.view_count for r in latest_counts if r.category == "Music" and r.view_count]
    assert by_cat["Music"]["videos_with_views"] == len(music)
    assert math.isclose(by_cat["Music"]["p50"], float(np.percentile(music, 50)), rel_tol=1e-9)
    assert sum(c["videos"] for c in by_cat.values()) == len(latest_counts)


def test_engagement_scatter_is_top_videos_by_views(conn, w30, latest_counts):
    scatter = analytics.get_engagement_analysis(conn, w30, scatter_limit=50)["scatter"]
    expected = sorted(latest_counts, key=lambda r: (r.view_count is None, -(r.view_count or 0), r.video_id))[:50]  # NULLS LAST
    assert [s["video_id"] for s in scatter] == [r.video_id for r in expected]


@pytest.mark.parametrize("limit", [0, 501, True, "10"])
def test_engagement_scatter_limit_validated(conn, w30, limit):
    with pytest.raises(QueryParameterError):
        analytics.get_engagement_analysis(conn, w30, scatter_limit=limit)


# ---------------------------------------------------
# TOP CHANNELS
# ---------------------------------------------------
@pytest.mark.parametrize("sort", ["unique_videos", "trending_volume", "views"])
def test_top_channels_sorted(conn, w30, sort):
    rows = analytics.get_top_channels(conn, w30, sort=sort, limit=50)
    assert len(rows) == 50
    keys = [(r[sort], r["views"]) for r in rows]
    assert keys == sorted(keys, reverse=True)


def test_top_channel_matches_independent_sql(conn, w30):
    top = analytics.get_top_channels(conn, w30, limit=1)[0]
    vid = conn.execute(text(
        f"SELECT count(*) AS n, sum(view_count) AS v FROM ({LATEST_W30}) x WHERE channel_id = :ch"),
        {**WINDOW, "ch": top["channel_id"]}).one()
    volume = conn.execute(text(
        "SELECT count(*) FROM app.trending_snapshots WHERE trending_date BETWEEN :s AND :e AND channel_id = :ch"),
        {**WINDOW, "ch": top["channel_id"]}).scalar_one()
    best = conn.execute(text(
        f"SELECT channel_id, count(*) AS n, sum(view_count) AS v FROM ({LATEST_W30}) x "
        f"GROUP BY channel_id ORDER BY n DESC, v DESC LIMIT 1"), WINDOW).one()
    assert top["channel_id"] == best.channel_id
    assert (top["unique_videos"], top["views"], top["trending_volume"]) == (vid.n, int(vid.v), volume)


def test_top_channels_defaults_and_validation(conn, w30):
    assert len(analytics.get_top_channels(conn, w30)) == 10
    for kwargs in ({"sort": "subscribers"}, {"sort": "views DESC; --"}, {"limit": 0}, {"limit": 51}):
        with pytest.raises(QueryParameterError):
            analytics.get_top_channels(conn, w30, **kwargs)
