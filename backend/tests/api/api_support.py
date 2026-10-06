"""Shared helpers for API tests (plain module, not a conftest, so it cannot shadow
backend/tests/conftest.py which existing tests import by name)."""

import datetime as dt
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "backend"
for p in (str(BACKEND), str(REPO_ROOT)):  # backend/app and the ml/ package
    if p not in sys.path:
        sys.path.insert(0, p)

import uuid  # noqa: E402

from app.api import deps  # noqa: E402
from app.auth.permissions import Role  # noqa: E402
from app.core.settings import Settings  # noqa: E402
from app.repositories.filters import Filters  # noqa: E402
from app.services.auth import Principal  # noqa: E402

W30_START, MAX_DATE, MIN_DATE = dt.date(2026, 9, 6), dt.date(2026, 10, 5), dt.date(2024, 10, 12)

TEST_AUTH_SECRET = "test-only-session-hmac-key-not-a-real-secret-0123456789"


def make_settings(**overrides) -> Settings:
    base = dict(app_env="development", cors_origins=("http://localhost:5173",), api_docs_enabled=True,
                ml_enabled=False, ml_preload=False, max_request_bytes=65536, auth_secret_key=TEST_AUTH_SECRET)
    return Settings(**{**base, **overrides})


def fake_principal(role: Role = Role.MEMBER) -> Principal:
    return Principal(user_id=uuid.UUID(int=1), email="member@example.test", display_name="Test Member",
                     role=role, tenant_id=uuid.UUID(int=2), tenant_name="Test Workspace")


def sign_in_as(app, role: Role = Role.MEMBER) -> Principal:
    """For tests about analytics/prediction behaviour, not authentication: replace session
    lookup with a fixed principal. Permission checks (require_permission) still run."""
    principal = fake_principal(role)
    app.dependency_overrides[deps.get_current_principal] = lambda: principal
    return principal


class FakeConn:
    """Stand-in connection for unit tests where repositories are mocked."""


FAKE_FILTERS = Filters(W30_START, MAX_DATE, countries=("IN",), categories=())

COUNT = {"value": 10, "previous": 8, "change_pct": 25.0}
KPIS = {
    "period": {"start_date": W30_START, "end_date": MAX_DATE, "days": 30},
    "previous_period": {"start_date": dt.date(2026, 8, 7), "end_date": dt.date(2026, 9, 5), "days": 30,
                        "available": True},
    "unique_videos": COUNT, "trending_volume": COUNT, "views": COUNT, "unique_channels": COUNT,
    "engagement_rate": {"value": 0.03, "previous": 0.02, "change_pts": 1.0},
}
DAILY = {"split_by": None, "series": []}
ENGAGEMENT = {
    "totals": {"videos": 0, "videos_without_views": 0, "views": 0, "likes": 0, "comments": 0, "engagement_rate": None},
    "distribution": {"p25": None, "p50": None, "p75": None, "p90": None},
    "histogram": [], "by_category": [], "scatter": [],
}
VIDEO_PAGE = {"items": [], "page": 1, "page_size": 25, "total": 0, "total_pages": 0}
VIDEO_DETAIL_MIN = {
    "video_id": "abc", "title": "t", "description": None, "tags": None, "category": "Music",
    "published_at": None, "duration_sec": None, "definition": None, "dimension": None,
    "licensed_content": None, "thumbnail_url": None, "views": 1, "likes": 0, "comments": 0,
    "engagement_rate": 0.0, "latest_country_code": "IN", "latest_trending_date": MAX_DATE,
    "first_trending_date": MAX_DATE, "last_trending_date": MAX_DATE, "trending_countries": ["IN"],
    "snapshot_count": 1,
    "channel": {"channel_id": None, "title": None, "description": None, "custom_url": None, "country": None,
                "published_at": None, "subscribers": None, "hidden_subscribers": None, "total_views": None,
                "video_count": None},
}

PREDICTION_BODY = {
    "title": "Last Over Thriller | India vs Australia | Match Highlights",
    "description": "An unbelievable finish in the final over.",
    "tags": ["india vs australia", "cricket highlights"],
    "channel_title": "Star Sports India",
    "category": "Sports",
    "country": "IN",
    "duration_sec": 140,
    "channel_subscriber_count": 8800000,
    "channel_video_count": 14200,
    "channel_view_count": 19600000000,
}
