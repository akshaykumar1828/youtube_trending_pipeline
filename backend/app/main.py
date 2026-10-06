"""FastAPI application factory.

Run from the repository root (so both backend/app and the ml/ package import):
    python -m uvicorn app.main:app --app-dir backend
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.concurrency import run_in_threadpool

from app.api.deps import require_permission
from app.api.routes import analytics, auth, health, meta, overview, predictions, tenant, videos
from app.auth.permissions import Permission
from app.core.errors import register_exception_handlers
from app.core.middleware import BodySizeLimitMiddleware, OriginCheckMiddleware, RequestIdMiddleware
from app.core.settings import Settings, get_settings
from app.db.auth_engine import dispose_auth_engine
from app.db.engine import dispose_engine
from app.schemas.common import ErrorResponse
from app.services.predictions import PredictionService

logger = logging.getLogger("app")

API_PREFIX = "/api/v1"
DESCRIPTION = """
Read-only analytics API over YouTube trending snapshots (PostgreSQL `app` schema) and an ML model.

**Metric semantics**
* *Latest snapshot* = each video's latest snapshot **within the filtered dataset** (date range,
  countries, categories), not its globally latest snapshot.
* **Snapshot-level** metrics count trending appearances (country x video x day), e.g. trending volume.
* **Video-level** metrics count each video once via its latest filtered snapshot, e.g. unique videos,
  views, engagement rate.
* **Country-level** metrics use each video's latest filtered snapshot in that country. Country
  `views_of_trending_videos` are **global lifetime views** of videos that trended there; they are
  **not additive** across countries.
* View counts are lifetime totals: historical snapshots are **never summed** for views.
* Period change: counts and views in **percent**; engagement rate in **percentage points**.

**Authentication**: sign in via `/api/v1/auth/login` (or register). The session is an HttpOnly
cookie; every `/api/v1` endpoint except register/login requires it. Analytics endpoints need
`VIEW_ANALYTICS`, predictions `MAKE_PREDICTION`, member management `MANAGE_USERS`. The YouTube
dataset is global and read-only; workspaces (tenants) own only their users and memberships.
Health probes are public.
"""

AUTH_RESPONSES = {
    401: {"model": ErrorResponse, "description": "Not signed in or session expired."},
    403: {"model": ErrorResponse, "description": "Your role lacks the required permission."},
}


def create_app(settings: Settings | None = None, prediction_service: PredictionService | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.require_auth_secret()  # fail fast: no API without a session-signing secret
    service = prediction_service or PredictionService(enabled=settings.ml_enabled)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        started = time.perf_counter()
        if settings.ml_enabled and settings.ml_preload:
            await run_in_threadpool(service.load)
        logger.info("startup complete in %.2fs (ml=%s)", time.perf_counter() - started, service.status)
        yield
        dispose_engine()
        dispose_auth_engine()

    docs = settings.api_docs_enabled
    app = FastAPI(
        title="YouTube Trending Intelligence API",
        version="1.0.0",
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.settings = settings
    app.state.prediction_service = service

    register_exception_handlers(app)

    # add_middleware wraps outermost last: CORS -> RequestId -> OriginCheck -> GZip -> BodySize -> app
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(OriginCheckMiddleware, allowed_origins=settings.cors_origins)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),  # explicit list; never "*" with credentials
        allow_credentials=True,  # the session cookie
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    # Health is public. Auth and tenant routes declare their requirements per route
    # (register/login/logout are open; /auth/me and /tenant/* need a session).
    app.include_router(health.router)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(tenant.router, prefix=API_PREFIX)

    # Protected server-side, per router: the global, read-only YouTube dataset and the model.
    view_analytics = [Depends(require_permission(Permission.VIEW_ANALYTICS))]
    for router in (meta.router, overview.router, analytics.router, videos.router):
        app.include_router(router, prefix=API_PREFIX, dependencies=view_analytics, responses=AUTH_RESPONSES)
    app.include_router(predictions.router, prefix=API_PREFIX, responses=AUTH_RESPONSES,
                       dependencies=[Depends(require_permission(Permission.MAKE_PREDICTION))])
    return app


app = create_app()
