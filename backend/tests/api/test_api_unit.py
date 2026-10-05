"""API unit tests: no database. Repository functions and build_filters are replaced with
recorders so these tests check HTTP parsing, parameter propagation, error mapping,
envelopes, request ids, CORS, body-size guard, health and ML-disabled behaviour."""

import datetime as dt
import re
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from api_support import (DAILY, ENGAGEMENT, FAKE_FILTERS, KPIS, MAX_DATE, PREDICTION_BODY, VIDEO_DETAIL_MIN,
                         VIDEO_PAGE, FakeConn, make_settings, sign_in_as)
from app.api import deps
from app.api.routes import health as health_routes
from app.core.settings import Settings, SettingsError
from app.main import create_app
from app.repositories import analytics, overview, videos
from app.repositories.common import QueryParameterError
from app.repositories.filters import FilterValidationError
from app.services.predictions import FAILED, PredictionService


class Recorder:
    def __init__(self, result=None, raises=None):
        self.result, self.raises, self.calls = result, raises, []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.raises is not None:
            raise self.raises
        return self.result


@pytest.fixture
def app_and_mocks(monkeypatch):
    app = create_app(make_settings())
    sign_in_as(app)  # these tests cover analytics behaviour; auth has its own tests

    def fake_db():
        yield FakeConn()

    app.dependency_overrides[deps.get_db] = fake_db
    build = Recorder(FAKE_FILTERS)
    monkeypatch.setattr(deps, "build_filters", build)
    mocks = {
        "build_filters": build,
        "get_kpis": Recorder(KPIS), "get_daily_volume": Recorder(DAILY),
        "get_category_performance": Recorder([]), "get_country_performance": Recorder([]),
        "get_engagement_analysis": Recorder(ENGAGEMENT), "get_top_channels": Recorder([]),
        "list_videos": Recorder(VIDEO_PAGE), "get_video": Recorder(VIDEO_DETAIL_MIN), "get_video_history": Recorder([]),
    }
    for module in (overview, analytics, videos):
        for name, rec in mocks.items():
            if hasattr(module, name):
                monkeypatch.setattr(module, name, rec)
    return app, mocks


@pytest.fixture
def client(app_and_mocks):
    app, _ = app_and_mocks
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mocks(app_and_mocks):
    return app_and_mocks[1]


# ---------------------------------------------------
# FILTER PARAMETERS -> build_filters -> repository
# ---------------------------------------------------
def test_filter_params_propagate_to_build_filters_and_repository(client, mocks):
    r = client.get("/api/v1/overview/kpis", params=[
        ("start_date", "2025-12-01"), ("end_date", "2025-12-31"),
        ("country", "in"), ("country", "US"), ("category", "Music"), ("category", "news & politics")])
    assert r.status_code == 200
    (conn,), kwargs = mocks["build_filters"].calls[0]
    assert isinstance(conn, FakeConn)
    assert kwargs == {"start_date": dt.date(2025, 12, 1), "end_date": dt.date(2025, 12, 31),
                      "countries": ["in", "US"], "categories": ["Music", "news & politics"]}
    (repo_conn, repo_filters), _ = mocks["get_kpis"].calls[0]
    assert repo_conn is conn and repo_filters is FAKE_FILTERS  # same request-scoped connection
    assert r.json()["filters"] == {"start_date": "2025-12-07", "end_date": "2026-01-05", "days": 30,
                                   "countries": ["IN"], "categories": []}


def test_no_filter_params_mean_defaults(client, mocks):
    client.get("/api/v1/analytics/categories")
    assert mocks["build_filters"].calls[0][1] == {"start_date": None, "end_date": None,
                                                  "countries": None, "categories": None}


@pytest.mark.parametrize("params, field", [
    ({"start_date": "2025-13-01"}, "start_date"),
    ({"end_date": "yesterday"}, "end_date"),
    ([("country", "X" * 65)], "country.0"),
    ([("country", "IN")] * 21, "country"),
])
def test_invalid_filter_params_rejected_before_repository(client, mocks, params, field):
    r = client.get("/api/v1/overview/kpis", params=params)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "invalid_request" and err["field"] == field
    assert mocks["build_filters"].calls == [] and mocks["get_kpis"].calls == []


@pytest.mark.parametrize("url, mock, expected_args, expected_kwargs", [
    ("/api/v1/overview/daily-volume?split_by=category", "get_daily_volume", (FAKE_FILTERS, "category"), {}),
    ("/api/v1/overview/daily-volume", "get_daily_volume", (FAKE_FILTERS, None), {}),
    ("/api/v1/analytics/engagement?scatter_limit=7", "get_engagement_analysis", (FAKE_FILTERS,), {"scatter_limit": 7}),
    ("/api/v1/analytics/engagement", "get_engagement_analysis", (FAKE_FILTERS,), {"scatter_limit": 200}),
    ("/api/v1/analytics/channels?sort=views&limit=5", "get_top_channels", (FAKE_FILTERS,), {"sort": "views", "limit": 5}),
    ("/api/v1/analytics/channels", "get_top_channels", (FAKE_FILTERS,), {"sort": "unique_videos", "limit": 10}),
    ("/api/v1/videos?sort=likes&order=asc&page=3&page_size=10&search=abc", "list_videos", (FAKE_FILTERS,),
     {"sort": "likes", "order": "asc", "page": 3, "page_size": 10, "search": "abc"}),
    ("/api/v1/videos", "list_videos", (FAKE_FILTERS,),
     {"sort": "views", "order": "desc", "page": 1, "page_size": 25, "search": None}),
])
def test_route_parameters_reach_repository(client, mocks, url, mock, expected_args, expected_kwargs):
    assert client.get(url).status_code == 200
    args, kwargs = mocks[mock].calls[0]
    assert isinstance(args[0], FakeConn)
    assert args[1:] == expected_args and kwargs == expected_kwargs


@pytest.mark.parametrize("url", [
    "/api/v1/videos?page=0", "/api/v1/videos?page_size=101", "/api/v1/videos?page_size=0",
    "/api/v1/videos?sort=title", "/api/v1/videos?order=up", "/api/v1/videos?page=abc",
    "/api/v1/analytics/channels?limit=51", "/api/v1/analytics/channels?sort=subscribers",
    "/api/v1/analytics/engagement?scatter_limit=501", "/api/v1/overview/daily-volume?split_by=channel",
])
def test_out_of_range_parameters_rejected(client, mocks, url):
    r = client.get(url)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    assert all(not rec.calls for name, rec in mocks.items() if name != "build_filters")


# ---------------------------------------------------
# ERROR MAPPING
# ---------------------------------------------------
class FakeDriverError(Exception):
    def __init__(self, pgcode):
        super().__init__("driver detail with secret_value")
        self.pgcode = pgcode


@pytest.mark.parametrize("exc, status, code, field", [
    (FilterValidationError("countries", "unknown ['XX']"), 422, "invalid_filter", "countries"),
    (QueryParameterError("sort", "must be one of x"), 422, "invalid_parameter", "sort"),
    (OperationalError("SELECT secret_sql", {"p": "secret_param"}, FakeDriverError("57014")), 504, "query_timeout", None),
    (OperationalError("SELECT secret_sql", {"p": "secret_param"}, FakeDriverError(None)), 503, "database_unavailable", None),
    (PoolTimeoutError("QueuePool limit reached secret_value"), 503, "database_busy", None),
    (ProgrammingError("SELECT secret_sql", {"p": "secret_param"}, FakeDriverError("42501")), 500, "database_error", None),
    (RuntimeError("boom secret_value"), 500, "internal_error", None),
])
def test_error_mapping(client, mocks, exc, status, code, field):
    mocks["get_kpis"].raises = exc
    r = client.get("/api/v1/overview/kpis")
    assert r.status_code == status
    body = r.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code and body["error"]["field"] == field
    assert body["error"]["request_id"] == r.headers["x-request-id"]
    for leak in ("secret", "SELECT", "Traceback", "psycopg2", "FakeDriverError"):
        assert leak not in r.text


def test_unknown_route_and_method_use_envelope(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.post("/api/v1/overview/kpis")
    assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"


# ---------------------------------------------------
# VIDEO DETAIL / HISTORY 404 LOGIC
# ---------------------------------------------------
def test_video_detail_404(client, mocks):
    mocks["get_video"].result = None
    r = client.get("/api/v1/videos/abc")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_history_existing_video_with_empty_history_returns_empty_list(client, mocks):
    mocks["get_video_history"].result = []
    r = client.get("/api/v1/videos/abc/history")
    assert r.status_code == 200 and r.json() == {"data": []}
    assert len(mocks["get_video"].calls) == 1  # existence checked only because history was empty


def test_history_unknown_video_404(client, mocks):
    mocks["get_video_history"].result, mocks["get_video"].result = [], None
    assert client.get("/api/v1/videos/abc/history").status_code == 404


def test_history_non_empty_skips_existence_query(client, mocks):
    mocks["get_video_history"].result = [{"country_code": "IN", "country_name": "India", "trending_date": MAX_DATE,
                                          "views": 1, "likes": 0, "comments": 0, "engagement_rate": 0.0}]
    assert client.get("/api/v1/videos/abc/history").status_code == 200
    assert mocks["get_video"].calls == []


def test_video_id_length_validated(client):
    assert client.get("/api/v1/videos/" + "x" * 65).status_code == 422


# ---------------------------------------------------
# REQUEST IDS
# ---------------------------------------------------
def test_request_id_generated_and_returned(client):
    r = client.get("/api/v1/overview/kpis")
    assert re.fullmatch(r"[0-9a-f]{32}", r.headers["x-request-id"])


def test_valid_incoming_request_id_reused_invalid_replaced(client):
    assert client.get("/health/live", headers={"X-Request-ID": "abc-123.x_y"}).headers["x-request-id"] == "abc-123.x_y"
    replaced = client.get("/health/live", headers={"X-Request-ID": "bad id!"}).headers["x-request-id"]
    assert replaced != "bad id!" and re.fullmatch(r"[0-9a-f]{32}", replaced)


# ---------------------------------------------------
# CORS
# ---------------------------------------------------
def test_cors_allowed_origin(client):
    r = client.options("/api/v1/overview/kpis", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    # Credentials (the session cookie) are allowed, but only for the explicit allowlist.
    assert r.headers["access-control-allow-credentials"] == "true"
    assert "PATCH" in r.headers["access-control-allow-methods"]
    simple = client.get("/api/v1/overview/kpis", headers={"Origin": "http://localhost:5173"})
    assert simple.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "x-request-id" in simple.headers["access-control-expose-headers"].lower()


def test_cors_disallowed_origin(client):
    r = client.options("/api/v1/overview/kpis", headers={
        "Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert r.status_code == 400 and "access-control-allow-origin" not in r.headers
    simple = client.get("/api/v1/overview/kpis", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in simple.headers


@pytest.mark.parametrize("origins", [("*",), ("localhost:5173",), ("ftp://x",)])
def test_wildcard_or_invalid_cors_rejected(origins):
    with pytest.raises(SettingsError):
        Settings(cors_origins=origins)


# ---------------------------------------------------
# BODY SIZE GUARD
# ---------------------------------------------------
def test_body_too_large_with_content_length(client):
    r = client.post("/api/v1/predictions", content=b"x" * 70_000, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"
    assert r.json()["error"]["request_id"] == r.headers["x-request-id"]


def test_body_too_large_chunked(client):
    def chunks():
        for _ in range(20):
            yield b"x" * 5000
    r = client.post("/api/v1/predictions", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"


def test_body_within_limit_reaches_validation(client):
    r = client.post("/api/v1/predictions", json={"title": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


# ---------------------------------------------------
# HEALTH
# ---------------------------------------------------
@contextmanager
def _broken_connection():
    raise OperationalError("connect", {}, FakeDriverError(None))
    yield  # pragma: no cover


def test_liveness_needs_no_database(client, monkeypatch):
    monkeypatch.setattr(health_routes, "get_connection", _broken_connection)
    monkeypatch.setattr(deps, "get_connection", _broken_connection)
    r = client.get("/health/live")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_readiness_reports_database_unavailable(client, monkeypatch):
    monkeypatch.setattr(health_routes, "get_connection", _broken_connection)
    r = client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready" and body["database"]["status"] == "unavailable"
    assert body["ml"]["status"] == "disabled"
    assert "secret" not in r.text


def test_readiness_independent_of_ml_failure(monkeypatch):
    @contextmanager
    def ok_connection():
        yield FakeConn()

    service = PredictionService(enabled=True)
    import ml
    monkeypatch.setattr(ml, "TrendingPredictor", Recorder(raises=RuntimeError("artifact missing")))
    service.load()
    assert service.status == FAILED

    app = create_app(make_settings(ml_enabled=True, ml_preload=False), prediction_service=service)
    sign_in_as(app)
    monkeypatch.setattr(health_routes, "get_connection", ok_connection)
    monkeypatch.setattr(health_routes.db_health, "check_database",
                        lambda conn: {"status": "ok", "role": "yt_app_ro", "read_only": True, "views_readable": True})
    with TestClient(app) as c:
        r = c.get("/health/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ready" and r.json()["ml"]["status"] == "failed"
        p = c.post("/api/v1/predictions", json=PREDICTION_BODY)
        assert p.status_code == 503 and p.json()["error"]["code"] == "model_unavailable"


# ---------------------------------------------------
# DOCS / ML DISABLED / PREDICTION REQUEST VALIDATION
# ---------------------------------------------------
def test_docs_disabled_outside_development(monkeypatch):
    app = create_app(make_settings(app_env="production", api_docs_enabled=False))
    with TestClient(app) as c:
        for url in ("/docs", "/redoc", "/openapi.json"):
            assert c.get(url).status_code == 404


def test_ml_disabled_returns_503_while_analytics_work(client):
    for r in (client.get("/api/v1/predictions/model-info"), client.post("/api/v1/predictions", json=PREDICTION_BODY)):
        assert r.status_code == 503 and r.json()["error"]["code"] == "model_unavailable"
    assert client.get("/api/v1/overview/kpis").status_code == 200


@pytest.mark.parametrize("change", [
    {"unexpected": 1},
    {"title": None},
    {"title": "x" * 201},
    {"tags": ["t"] * 51},
    {"tags": ["x" * 101]},
    {"channel_subscriber_count": -1},
    {"channel_view_count": 10 ** 14},
    {"duration_sec": -5},
    {"category": True},
    {"category": ["Sports"]},
])
def test_prediction_request_validation(client, change):
    body = {**PREDICTION_BODY, **change}
    if change.get("title", "") is None:
        body.pop("title")
    r = client.post("/api/v1/predictions", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
