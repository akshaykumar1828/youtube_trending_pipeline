"""Videos repository tests: pagination, sorting, search, filters, detail, history."""

import math
from dataclasses import replace

import pytest
from sqlalchemy import text

from app.repositories import overview, videos
from app.repositories.common import QueryParameterError
from app.repositories.filters import Filters
from conftest import MAX_DATE, MIN_DATE, W30_START

WINDOW = {"s": W30_START, "e": MAX_DATE}

LATEST_W30 = """
    SELECT * FROM (
        SELECT s.*, row_number() OVER (
            PARTITION BY video_id ORDER BY trending_date DESC, view_count DESC NULLS LAST, country_code) AS rn
        FROM app.trending_snapshots s WHERE trending_date BETWEEN :s AND :e {extra}
    ) x WHERE rn = 1
"""


def ids(result):
    return [i["video_id"] for i in result["items"]]


# ---------------------------------------------------
# PAGINATION
# ---------------------------------------------------
def test_total_equals_unique_videos(conn, w30):
    result = videos.list_videos(conn, w30)
    assert result["total"] == overview.get_kpis(conn, w30)["unique_videos"]["value"] == 13213
    assert (result["page"], result["page_size"], len(result["items"])) == (1, 25, 25)
    assert result["total_pages"] == math.ceil(13213 / 25)


def test_pages_are_disjoint_and_stable(conn, w30):
    p1, p2 = videos.list_videos(conn, w30, page=1, page_size=10), videos.list_videos(conn, w30, page=2, page_size=10)
    p3 = videos.list_videos(conn, w30, page=3, page_size=10)
    combined = videos.list_videos(conn, w30, page=1, page_size=30)
    assert not set(ids(p1)) & set(ids(p2))
    assert ids(p1) + ids(p2) + ids(p3) == ids(combined)
    assert ids(videos.list_videos(conn, w30, page=1, page_size=10)) == ids(p1)


def test_last_and_past_end_pages(conn, w30):
    last = videos.list_videos(conn, w30, page=529)
    assert len(last["items"]) == 13213 - 528 * 25
    past = videos.list_videos(conn, w30, page=530)
    assert past["items"] == [] and past["total"] == 13213


@pytest.mark.parametrize("kwargs", [
    {"page": 0}, {"page": -1}, {"page": True}, {"page": "1"},
    {"page_size": 0}, {"page_size": 101}, {"page_size": 2.5},
])
def test_invalid_pagination_rejected(conn, w30, kwargs):
    with pytest.raises(QueryParameterError):
        videos.list_videos(conn, w30, **kwargs)


# ---------------------------------------------------
# SORTING
# ---------------------------------------------------
SORT_FIELDS = {
    "views": "views", "likes": "likes", "comments": "comments", "engagement_rate": "engagement_rate",
    "days_on_trending": "days_on_trending", "first_trending_date": "first_trending_date",
    "last_trending_date": "last_trending_date", "published_at": "published_at",
}


@pytest.mark.parametrize("order", ["desc", "asc"])
@pytest.mark.parametrize("sort", list(SORT_FIELDS))
def test_sorting(conn, w30, sort, order):
    items = videos.list_videos(conn, w30, sort=sort, order=order, page_size=100)["items"]
    values = [i[SORT_FIELDS[sort]] for i in items]
    present = [v for v in values if v is not None]
    assert values[:len(present)] == present  # NULLs last
    assert present == sorted(present, reverse=(order == "desc"))
    # ties broken by video_id ascending
    for a, b in zip(items, items[1:]):
        if a[SORT_FIELDS[sort]] == b[SORT_FIELDS[sort]]:
            assert a["video_id"] < b["video_id"]


@pytest.mark.parametrize("kwargs", [{"sort": "title"}, {"sort": "view_count; DROP TABLE x"}, {"order": "up"},
                                    {"order": "DESC"}])
def test_invalid_sort_rejected(conn, w30, kwargs):
    with pytest.raises(QueryParameterError):
        videos.list_videos(conn, w30, **kwargs)


# ---------------------------------------------------
# FILTERS + LATEST-WITHIN-FILTERS
# ---------------------------------------------------
def test_filters_respected(conn, w30):
    f = replace(w30, countries=("IN",), categories=("Music",))
    result = videos.list_videos(conn, f, page_size=100)
    expected_total = conn.execute(text(
        "SELECT count(DISTINCT video_id) FROM app.trending_snapshots "
        "WHERE trending_date BETWEEN :s AND :e AND country_code = 'IN' AND category = 'Music'"), WINDOW).scalar_one()
    assert result["total"] == expected_total
    assert all(i["trending_countries"] == ["IN"] and i["category"] == "Music" for i in result["items"])


def test_items_use_latest_snapshot_within_filters(conn, w30):
    f = replace(w30, countries=("IN",))
    items = videos.list_videos(conn, f, page_size=50)["items"]
    expected = {r.video_id: r for r in conn.execute(text(
        LATEST_W30.format(extra="AND country_code = 'IN'")), WINDOW)}
    for i in items:
        e = expected[i["video_id"]]
        assert (i["views"], i["likes"], i["comments"], i["title"]) == \
               (e.view_count, e.like_count, e.comment_count, e.video_title)


def test_item_aggregates_match_independent_sql(conn, w30):
    for i in videos.list_videos(conn, w30, page_size=20)["items"]:
        r = conn.execute(text(
            "SELECT array_agg(DISTINCT country_code) AS c, count(DISTINCT trending_date) AS d, min(trending_date) AS f, "
            "max(trending_date) AS l, count(*) AS n FROM app.trending_snapshots "
            "WHERE video_id = :v AND trending_date BETWEEN :s AND :e"), {**WINDOW, "v": i["video_id"]}).one()
        assert (sorted(r.c), r.d, r.f, r.l, r.n) == (
            i["trending_countries"], i["days_on_trending"], i["first_trending_date"],
            i["last_trending_date"], i["snapshot_count"])


def test_boundary_single_day_at_min_date(conn):
    result = videos.list_videos(conn, Filters(MIN_DATE, MIN_DATE))
    expected = conn.execute(text(
        "SELECT count(DISTINCT video_id) FROM app.trending_snapshots WHERE trending_date = :d"),
        {"d": MIN_DATE}).scalar_one()
    assert result["total"] == expected
    assert all(i["first_trending_date"] == i["last_trending_date"] == MIN_DATE for i in result["items"])


# ---------------------------------------------------
# SEARCH
# ---------------------------------------------------
def independent_search_count(conn, needle):
    return conn.execute(text(
        f"SELECT count(*) FROM ({LATEST_W30.format(extra='')}) x "
        "WHERE strpos(lower(video_title), lower(:n)) > 0 OR strpos(lower(channel_title), lower(:n)) > 0 "
        "OR video_id = :n"), {**WINDOW, "n": needle}).scalar_one()


def test_search_case_insensitive_substring(conn, w30):
    lower = videos.list_videos(conn, w30, search="cricket", page_size=100)
    upper = videos.list_videos(conn, w30, search="  CRICKET ", page_size=100)
    assert lower["total"] == upper["total"] == independent_search_count(conn, "cricket") > 0
    assert ids(lower) == ids(upper)
    assert all("cricket" in (i["title"] + " " + i["channel_title"]).lower() for i in lower["items"])


@pytest.mark.parametrize("needle", ["%%", "__", "100%"])
def test_search_wildcards_are_literal(conn, w30, needle):
    result = videos.list_videos(conn, w30, search=needle, page_size=100)
    assert result["total"] == independent_search_count(conn, needle)
    assert result["total"] < 13213
    assert all(needle.lower() in (i["title"] + " " + i["channel_title"]).lower() for i in result["items"])


def test_search_exact_video_id(conn, w30):
    target = videos.list_videos(conn, w30, sort="likes", page_size=1)["items"][0]["video_id"]
    assert target in ids(videos.list_videos(conn, w30, search=target))


def test_search_combines_with_filters(conn, w30):
    result = videos.list_videos(conn, replace(w30, countries=("IN",)), search="cricket", page_size=100)
    assert result["total"] > 0
    assert all(i["trending_countries"] == ["IN"] for i in result["items"])


def test_blank_search_means_no_search(conn, w30):
    assert videos.list_videos(conn, w30, search="   ")["total"] == 13213


@pytest.mark.parametrize("search", ["a", "x" * 101, 123, ["cricket"]])
def test_invalid_search_rejected(conn, w30, search):
    with pytest.raises(QueryParameterError) as exc:
        videos.list_videos(conn, w30, search=search)
    assert exc.value.field == "search"


# ---------------------------------------------------
# DETAIL + HISTORY
# ---------------------------------------------------
@pytest.fixture
def long_running_video(conn):
    """A video whose history extends before the default 30-day window."""
    return conn.execute(text(
        "SELECT * FROM app.video_details WHERE first_trending_date < :s AND last_trending_date >= :s "
        "ORDER BY snapshot_count DESC, video_id LIMIT 1"), {"s": W30_START}).mappings().one()


def test_get_video_matches_video_details(conn, long_running_video):
    v = videos.get_video(conn, long_running_video["video_id"])
    d = long_running_video
    assert (v["title"], v["views"], v["likes"], v["comments"], v["category"]) == \
           (d["video_title"], d["view_count"], d["like_count"], d["comment_count"], d["category"])
    assert (v["snapshot_count"], v["trending_countries"], v["first_trending_date"]) == \
           (d["snapshot_count"], list(d["trending_countries"]), d["first_trending_date"])
    assert v["channel"]["channel_id"] == d["channel_id"]
    assert math.isclose(v["engagement_rate"], (d["like_count"] + d["comment_count"]) / d["view_count"])


def test_get_video_history_is_full_and_unfiltered(conn, long_running_video):
    history = videos.get_video_history(conn, long_running_video["video_id"])
    assert len(history) == long_running_video["snapshot_count"]
    keys = [(h["trending_date"], h["country_code"]) for h in history]
    assert keys == sorted(keys)
    assert history[0]["trending_date"] == long_running_video["first_trending_date"] < W30_START


def test_unknown_video(conn):
    assert videos.get_video(conn, "no_such_vid") is None
    assert videos.get_video_history(conn, "no_such_vid") == []


@pytest.mark.parametrize("video_id", [None, "", "x" * 65, 123])
def test_invalid_video_id_rejected(conn, video_id):
    for fn in (videos.get_video, videos.get_video_history):
        with pytest.raises(QueryParameterError):
            fn(conn, video_id)
