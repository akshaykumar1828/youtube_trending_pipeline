"""FastAPI dependencies: request-scoped read-only connection, Filters, prediction service,
and authentication / authorization (current principal, permission checks)."""

import datetime as dt
from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import Depends, Query, Request
from pydantic import StringConstraints
from sqlalchemy.engine import Connection

from app.auth.permissions import Permission
from app.core.errors import ForbiddenError, NotAuthenticatedError
from app.core.settings import Settings
from app.db.auth_engine import get_auth_connection
from app.db.engine import get_connection
from app.repositories.filters import Filters, build_filters
from app.services import auth as auth_service
from app.services.auth import Principal
from app.services.predictions import PredictionService

MAX_FILTER_VALUES = 20
FilterValue = Annotated[str, StringConstraints(max_length=64)]


def get_db() -> Iterator[Connection]:
    """One pooled connection per request, as the read-only role yt_app_ro.

    The transaction is READ ONLY (role default + engine option) and REPEATABLE READ, so all
    statements of a request see one consistent snapshot. Nothing is committed; the
    transaction is rolled back and the connection returned to the pool when the request ends.
    """
    with get_connection() as conn:
        conn.execution_options(isolation_level="REPEATABLE READ")  # before the first statement
        yield conn


DbConnection = Annotated[Connection, Depends(get_db)]


def get_filters(
    conn: DbConnection,
    start_date: Annotated[dt.date | None, Query(
        description="First trending date (inclusive, YYYY-MM-DD). Default: 29 days before end_date, "
                    "not earlier than the first date in the data.")] = None,
    end_date: Annotated[dt.date | None, Query(
        description="Last trending date (inclusive). Default: the latest trending date in the data.")] = None,
    country: Annotated[list[FilterValue] | None, Query(
        max_length=MAX_FILTER_VALUES,
        description="Country code; repeat for several (?country=IN&country=US). Omit for all countries.")] = None,
    category: Annotated[list[FilterValue] | None, Query(
        max_length=MAX_FILTER_VALUES,
        description="Category (case-insensitive); repeat for several. Omit for all categories.")] = None,
) -> Filters:
    """Query parameters -> the existing Phase 2c Filters. build_filters() is the only
    filter validation (date range, valid countries/categories, defaults)."""
    return build_filters(conn, start_date=start_date, end_date=end_date,
                         countries=country or None, categories=category or None)


AppliedFiltersDep = Annotated[Filters, Depends(get_filters)]


def get_prediction_service(request: Request) -> PredictionService:
    return request.app.state.prediction_service


PredictionServiceDep = Annotated[PredictionService, Depends(get_prediction_service)]


# --- authentication / authorization ----------------------------------------------------------

def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_auth_db() -> Iterator[Connection]:
    """One pooled yt_auth_rw connection (schema `auth` only). Services commit explicitly;
    anything uncommitted is rolled back when the request ends."""
    with get_auth_connection() as conn:
        yield conn


AuthDb = Annotated[Connection, Depends(get_auth_db)]


def session_token(request: Request, settings: SettingsDep) -> str | None:
    token = request.cookies.get(settings.auth_cookie_name)
    return token if token and len(token) <= 128 else None


def get_current_principal(request: Request, settings: SettingsDep) -> Principal:
    """The identity behind the session cookie, re-read from the database on every request
    (so logout, deactivation and role changes apply immediately). The tenant comes from the
    session, never from the request. Uses a short-lived connection, released before the
    endpoint runs."""
    token = session_token(request, settings)
    if token is None:
        raise NotAuthenticatedError()
    with get_auth_connection() as conn:
        principal = auth_service.principal_for_token(conn, settings, token)
    if principal is None:
        raise NotAuthenticatedError("Your session has expired. Sign in again.")
    request.state.principal = principal
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def require_permission(permission: Permission) -> Callable[..., Principal]:
    def check(principal: CurrentPrincipal) -> Principal:
        if not principal.can(permission):
            raise ForbiddenError()
        return principal

    check.__name__ = f"require_{permission.lower()}"
    return check
