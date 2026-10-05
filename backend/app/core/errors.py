"""Error envelope and exception -> HTTP mapping.

Every error response has the shape
    {"error": {"code", "message", "field", "request_id", "details"}}
Responses never include SQL, bound values, stack traces, connection details
or credentials; full exceptions are logged server-side with the request id.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.repositories.common import QueryParameterError
from app.repositories.filters import FilterValidationError

logger = logging.getLogger("app.errors")

STATEMENT_TIMEOUT_PGCODE = "57014"


class ApiError(Exception):
    """An error with a fixed HTTP status and public code/message."""

    def __init__(self, status_code, code, message, field=None, details=None):
        super().__init__(message)
        self.status_code, self.code, self.message, self.field, self.details = (
            status_code, code, message, field, details)


class NotFoundError(ApiError):
    def __init__(self, message="Resource not found"):
        super().__init__(404, "not_found", message)


class ModelUnavailableError(ApiError):
    def __init__(self, message="The prediction model is not available"):
        super().__init__(503, "model_unavailable", message)


class NotAuthenticatedError(ApiError):
    def __init__(self, message="Authentication required."):
        super().__init__(401, "not_authenticated", message)


class InvalidCredentialsError(ApiError):
    def __init__(self):
        super().__init__(401, "invalid_credentials", "Invalid email or password.")


class TooManyAttemptsError(ApiError):
    def __init__(self):
        super().__init__(429, "too_many_attempts",
                         "Too many failed sign-in attempts. Try again later.")


class ForbiddenError(ApiError):
    def __init__(self, message="You do not have permission to perform this action."):
        super().__init__(403, "forbidden", message)


class ConflictError(ApiError):
    def __init__(self, code, message, field=None):
        super().__init__(409, code, message, field)


class RegistrationClosedError(ApiError):
    def __init__(self):
        super().__init__(403, "registration_closed", "Registration is disabled.")


def request_id_of(request_or_scope) -> str | None:
    scope = getattr(request_or_scope, "scope", request_or_scope)
    return scope.get("state", {}).get("request_id")


def error_body(code, message, request_id, field=None, details=None) -> dict:
    body = {"code": code, "message": message, "field": field, "request_id": request_id}
    if details:
        body["details"] = details
    return {"error": body}


def error_response(request, status_code, code, message, field=None, details=None) -> JSONResponse:
    return JSONResponse(status_code=status_code,
                        content=error_body(code, message, request_id_of(request), field, details))


def _validation_details(exc: RequestValidationError):
    details = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p not in ("query", "path", "body")]
        message = err.get("msg", "Invalid value")
        if err.get("type") == "value_error" and "error" in err.get("ctx", {}):
            message = str(err["ctx"]["error"])  # our validator's own message, no prefix
        details.append({"field": ".".join(loc) or None, "message": message})
    return details


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return error_response(request, exc.status_code, exc.code, exc.message, exc.field, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError):
        details = _validation_details(exc)
        field = details[0]["field"] if details else None
        return error_response(request, 422, "invalid_request", "The request is invalid.", field, details)

    @app.exception_handler(FilterValidationError)
    async def _filter_validation(request: Request, exc: FilterValidationError):
        return error_response(request, 422, "invalid_filter", str(exc), exc.field)

    @app.exception_handler(QueryParameterError)
    async def _query_parameter(request: Request, exc: QueryParameterError):
        return error_response(request, 422, "invalid_parameter", str(exc), exc.field)

    try:  # ml is an optional runtime dependency of the API
        from ml import InvalidInputError
    except ImportError:  # pragma: no cover - ml always present in this repo
        InvalidInputError = None

    if InvalidInputError is not None:
        @app.exception_handler(InvalidInputError)
        async def _prediction_input(request: Request, exc):
            details = [{"field": e["field"], "message": e["message"]} for e in exc.errors]
            return error_response(request, 422, "invalid_prediction_input", str(exc),
                                  details[0]["field"] if details else None, details)

    @app.exception_handler(PoolTimeoutError)
    async def _pool_timeout(request: Request, exc):
        logger.warning("database pool exhausted [request_id=%s]", request_id_of(request))
        return error_response(request, 503, "database_busy",
                              "The database is busy. Please retry shortly.")

    @app.exception_handler(DBAPIError)
    async def _database_error(request: Request, exc: DBAPIError):
        rid = request_id_of(request)
        pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
        if pgcode == STATEMENT_TIMEOUT_PGCODE:
            logger.warning("database statement timeout [request_id=%s]", rid)
            return error_response(request, 504, "query_timeout",
                                  "The query took too long. Try a narrower date range or fewer filters.")
        if exc.connection_invalidated or pgcode is None:
            logger.error("database unavailable [request_id=%s]: %s", rid, type(exc.orig).__name__)
            return error_response(request, 503, "database_unavailable", "The database is unavailable.")
        logger.exception("database error [request_id=%s]", rid)
        return error_response(request, 500, "database_error", "A database error occurred.")

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        codes = {401: "not_authenticated", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}
        message = "Not found" if exc.status_code == 404 else str(exc.detail)
        return error_response(request, exc.status_code, codes.get(exc.status_code, "http_error"), message)
