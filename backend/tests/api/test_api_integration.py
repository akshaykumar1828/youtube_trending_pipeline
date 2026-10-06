"""API integration tests against the real database (yt_app_ro), ML disabled.

The core check: each endpoint's JSON equals the direct repository result for the same
resolved Filters (no transformation drift between repository and API)."""

import json

import pytest
from dotenv import dotenv_values
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from sqlalchemy import text

from api_support import MAX_DATE, MIN_DATE, REPO_ROOT, W30_START, make_settings, sign_in_as
from app.api import deps
from app.main import create_app
from app.repositories import analytics, meta, overview, videos
from app.repositories.filters import build_filters
from app.schemas.analytics import CategoryPerformance, EngagementAnalysis
from app.schemas.common import AppliedFilters, FilteredResponse
from app.schemas.overview import Kpis
from app.schemas.videos import VideoPage

RESPONSES = []  # every response body, scanned for credentials at the end


@pytest.fixture(scope="module")
def client():
    app = create_app(make_settings())
    sign_in_as(app)  # analytics correctness; real sessions are covered in tests/auth
    with TestClient(app) as c:
        yield c


def get(client, url, params=None, status=200):
    r = client.get(url, params=params)
    RESPONSES.append(r.text)
    assert r.status_code == status, r.text[:300]
    return r.json()


def expected_filtered(filters, data):
    return jsonable_encoder({"filters": AppliedFilters.from_filters(filters).model_dump(), "data": data})


FILTER_CASES = {
    "default": ([], {}),
    "IN+US+Music": ([("country", "in"), ("country", "US"), ("category", "music")],
                    {"countries": ["in", "US"], "categories": ["music"]}),
    "single-day": ([("start_date", "2026-10-05"), ("end_date", "2026-10-05")],
                   {"start_date": MAX_DATE, "end_date": MAX_DATE}),
}


# ---------------------------------------------------
# META
# ---------------------------------------------------
def test_meta_filters(client, conn):
    body = get(client, "/api/v1/meta/filters")
    assert body == jsonable_encoder({"data": {
        "countries": meta.get_countries(conn), "categories": meta.get_categories(conn),
        "date_range": {"min_date": MIN_DATE, "max_date": MAX_DATE},
        "default_range": {"start_date": W30_START, "end_date": MAX_DATE, "days": 30}}})
    assert len(body["data"]["countries"]) == 9 and len(body["data"]["categories"]) == 17  # + Movies (2026 data)


# ---------------------------------------------------
# API == REPOSITORY
# ---------------------------------------------------
@pytest.mark.parametrize("case", FILTER_CASES, ids=list(FILTER_CASES))
@pytest.mark.parametrize("url, call", [
    ("/api/v1/overview/kpis", lambda c, f: overview.get_kpis(c, f)),
    ("/api/v1/overview/daily-volume", lambda c, f: overview.get_daily_volume(c, f)),
    ("/api/v1/overview/daily-volume?split_by=country", lambda c, f: overview.get_daily_volume(c, f, "country")),
    ("/api/v1/analytics/categories", lambda c, f: analytics.get_category_performance(c, f)),
    ("/api/v1/analytics/countries", lambda c, f: analytics.get_country_performance(c, f)),
    ("/api/v1/analytics/engagement?scatter_limit=50", lambda c, f: analytics.get_engagement_analysis(c, f, 50)),
    ("/api/v1/analytics/channels?sort=views&limit=20", lambda c, f: analytics.get_top_channels(c, f, "views", 20)),
    ("/api/v1/videos?sort=engagement_rate&order=asc&page=2&page_size=30",
     lambda c, f: videos.list_videos(c, f, sort="engagement_rate", order="asc", page=2, page_size=30)),
], ids=["kpis", "daily", "daily-country", "categories", "countries", "engagement", "channels", "videos"])
def test_api_equals_repository(client, conn, url, call, case):
    params, filter_kwargs = FILTER_CASES[case]
    path, _, query = url.partition("?")
    query_params = [tuple(p.split("=")) for p in query.split("&")] if query else []
    body = get(client, path, params=query_params + params)
    filters = build_filters(conn, **filter_kwargs)
    assert body == expected_filtered(filters, call(conn, filters))


def test_all_time_kpis_and_videos(client, conn, all_time):
    params = [("start_date", MIN_DATE.isoformat()), ("end_date", MAX_DATE.isoformat())]
    assert get(client, "/api/v1/overview/kpis", params) == expected_filtered(all_time, overview.get_kpis(conn, all_time))
    page = get(client, "/api/v1/videos", params)
    assert page["data"]["total"] == 217115
    assert page == expected_filtered(all_time, videos.list_videos(conn, all_time))


def test_default_window_is_echoed(client):
    assert get(client, "/api/v1/overview/kpis")["filters"] == {
        "start_date": "2026-09-06", "end_date": "2026-10-05", "days": 30, "countries": [], "categories": []}


# ---------------------------------------------------
# RESPONSE SCHEMAS
# ---------------------------------------------------
@pytest.mark.parametrize("url, model", [
    ("/api/v1/overview/kpis", FilteredResponse[Kpis]),
    ("/api/v1/analytics/categories", FilteredResponse[list[CategoryPerformance]]),
    ("/api/v1/analytics/engagement", FilteredResponse[EngagementAnalysis]),
    ("/api/v1/videos", FilteredResponse[VideoPage]),
])
def test_responses_validate_against_schemas(client, url, model):
    model.model_validate(get(client, url))


# ---------------------------------------------------
# VIDEOS: pagination, sorting, search, detail, history
# ---------------------------------------------------
def test_pagination_deterministic_and_disjoint(client):
    ids = lambda b: [i["video_id"] for i in b["data"]["items"]]
    p1 = get(client, "/api/v1/videos", {"page": 1, "page_size": 20})
    p2 = get(client, "/api/v1/videos", {"page": 2, "page_size": 20})
    both = get(client, "/api/v1/videos", {"page": 1, "page_size": 40})
    assert ids(p1) + ids(p2) == ids(both) and not set(ids(p1)) & set(ids(p2))
    assert ids(get(client, "/api/v1/videos", {"page": 1, "page_size": 20})) == ids(p1)
    assert p1["data"]["total"] == 13158 and p1["data"]["total_pages"] == 658


@pytest.mark.parametrize("sort", list(videos.VIDEO_SORTS))
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_sorting_passes_through(client, conn, w30, sort, order):
    body = get(client, "/api/v1/videos", {"sort": sort, "order": order, "page_size": 15})
    expected = videos.list_videos(conn, w30, sort=sort, order=order, page_size=15)
    assert body["data"] == jsonable_encoder(expected)


def test_search_and_filters_combine(client, conn, w30):
    body = get(client, "/api/v1/videos", [("search", "CRICKET"), ("country", "IN"), ("page_size", "100")])
    assert body["data"]["total"] > 0
    assert all(i["trending_countries"] == ["IN"] for i in body["data"]["items"])


def test_repository_validation_surfaces_as_422(client):
    err = get(client, "/api/v1/videos", {"search": "a"}, status=422)["error"]
    assert (err["code"], err["field"]) == ("invalid_parameter", "search")
    err = get(client, "/api/v1/overview/kpis", [("country", "SGX")], status=422)["error"]
    assert (err["code"], err["field"]) == ("invalid_filter", "countries")
    err = get(client, "/api/v1/analytics/categories", {"end_date": "2026-10-06"}, status=422)["error"]
    assert (err["code"], err["field"]) == ("invalid_filter", "end_date")
    err = get(client, "/api/v1/overview/kpis", {"start_date": "2026-01-05", "end_date": "2026-01-01"}, status=422)["error"]
    assert err["field"] == "start_date"


def test_video_detail_and_history(client, conn):
    vid = "YyepU5ztLf4"
    assert get(client, f"/api/v1/videos/{vid}") == jsonable_encoder({"data": videos.get_video(conn, vid)})
    history = get(client, f"/api/v1/videos/{vid}/history")
    assert history == jsonable_encoder({"data": videos.get_video_history(conn, vid)})
    assert len(history["data"]) == videos.get_video(conn, vid)["snapshot_count"]


def test_unknown_video_404(client):
    for url in ("/api/v1/videos/no_such_vid", "/api/v1/videos/no_such_vid/history"):
        assert get(client, url, status=404)["error"]["code"] == "not_found"


# ---------------------------------------------------
# HEALTH + DB SESSION
# ---------------------------------------------------
def test_readiness_with_database(client):
    body = get(client, "/health/ready")
    assert body["status"] == "ready"
    assert body["database"] == {"status": "ok", "role": "yt_app_ro", "read_only": True, "views_readable": True}
    assert body["ml"]["status"] == "disabled"


def test_request_connection_is_read_only_repeatable_read_app_role():
    gen = deps.get_db()
    conn = next(gen)
    try:
        row = conn.execute(text("SELECT current_user, current_setting('transaction_isolation'), "
                                "current_setting('transaction_read_only'), current_setting('statement_timeout')")).one()
        assert tuple(row) == ("yt_app_ro", "repeatable read", "on", "15s")
    finally:
        gen.close()


# ---------------------------------------------------
# OPENAPI CONTRACT
# ---------------------------------------------------
def test_openapi_contract(client):
    spec = get(client, "/openapi.json")
    operations = {(m.upper(), p) for p, ops in spec["paths"].items() for m in ops}
    assert operations == {
        ("GET", "/health/live"), ("GET", "/health/ready"), ("GET", "/api/v1/meta/filters"),
        ("GET", "/api/v1/overview/kpis"), ("GET", "/api/v1/overview/daily-volume"),
        ("GET", "/api/v1/analytics/categories"), ("GET", "/api/v1/analytics/countries"),
        ("GET", "/api/v1/analytics/engagement"), ("GET", "/api/v1/analytics/channels"),
        ("GET", "/api/v1/videos"), ("GET", "/api/v1/videos/{video_id}"),
        ("GET", "/api/v1/videos/{video_id}/history"),
        ("GET", "/api/v1/predictions/model-info"), ("POST", "/api/v1/predictions"),
        ("POST", "/api/v1/auth/register"), ("POST", "/api/v1/auth/login"), ("POST", "/api/v1/auth/logout"),
        ("GET", "/api/v1/auth/me"), ("GET", "/api/v1/tenant"), ("GET", "/api/v1/tenant/members"),
        ("POST", "/api/v1/tenant/members"), ("PATCH", "/api/v1/tenant/members/{user_id}"),
    }
    public = {"/health/live", "/health/ready", "/api/v1/auth/register", "/api/v1/auth/login", "/api/v1/auth/logout"}
    for path, ops in spec["paths"].items():
        for op in ops.values():
            if path not in public:  # every protected operation documents the auth errors
                assert "401" in op["responses"], path
                assert "403" in op["responses"] or path == "/api/v1/auth/me", path
    blob = json.dumps(spec)
    for phrase in ("WITHIN THE FILTERED DATASET", "SNAPSHOT-LEVEL", "VIDEO-LEVEL", "COUNTRY-LEVEL",
                   "NOT additive across countries", "never summed", "PERCENTAGE POINTS", "Percent change",
                   "NOT a probability that an arbitrary video will become trending"):
        assert phrase in blob, phrase
    assert set(spec["components"]["schemas"]["VideoSort"]["enum"]) == set(videos.VIDEO_SORTS)


# ---------------------------------------------------
# NO CREDENTIALS IN RESPONSES (runs last in this module)
# ---------------------------------------------------
def test_zz_no_credentials_in_any_response():
    secrets = [v for k, v in dotenv_values(REPO_ROOT / ".env").items() if k.endswith(("PASSWORD", "API_KEY", "SECRET_KEY")) and v]
    assert RESPONSES and secrets
    for body in RESPONSES:
        for secret in secrets:
            assert secret not in body
