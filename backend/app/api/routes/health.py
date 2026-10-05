"""Liveness and readiness probes (outside /api/v1)."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.db import health as db_health
from app.db.engine import get_connection

logger = logging.getLogger("app.health")
router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", summary="Liveness: the process is up (no database access)")
def live():
    return {"status": "ok"}


@router.get("/ready", summary="Readiness: database connectivity, read access and read-only session",
            responses={503: {"description": "Not ready (database unavailable or check failed)."}})
def ready(request: Request):
    """Ready when the database answers as a read-only session and both application views are
    readable. ML status is reported separately and does not affect readiness."""
    try:
        with get_connection() as conn:
            database = db_health.check_database(conn)
    except Exception as exc:  # report, never leak details
        logger.warning("readiness: database unavailable (%s)", type(exc).__name__)
        database = {"status": "unavailable", "role": None, "read_only": None, "views_readable": None}

    is_ready = database["status"] == "ok"
    body = {
        "status": "ready" if is_ready else "not_ready",
        "database": database,
        "ml": request.app.state.prediction_service.health(),
    }
    return JSONResponse(status_code=200 if is_ready else 503, content=body)
