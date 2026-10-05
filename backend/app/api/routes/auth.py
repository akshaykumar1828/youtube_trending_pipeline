"""Registration, sign-in, sign-out and the current identity.

The session token travels only in an HttpOnly cookie (never in a response body), so page
JavaScript cannot read it. The database stores only an HMAC of the token.
"""

from fastapi import APIRouter, Depends, Response

from app.api.deps import AuthDb, CurrentPrincipal, SettingsDep, session_token
from app.core.settings import Settings
from app.schemas.auth import CurrentUser, LoginRequest, LogoutResult, RegisterRequest
from app.schemas.common import DataResponse, ErrorResponse
from app.services import auth as auth_service

COOKIE_PATH = "/api"


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(no_store)], responses={
    422: {"model": ErrorResponse, "description": "Invalid request."},
})


def _set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(settings.auth_cookie_name, token, max_age=settings.auth_session_ttl_minutes * 60,
                        path=COOKIE_PATH, secure=settings.auth_cookie_secure, httponly=True, samesite="lax")


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.auth_cookie_name, path=COOKIE_PATH, secure=settings.auth_cookie_secure,
                           httponly=True, samesite="lax")


def _end_previous_session(conn, settings, token) -> None:
    if token:
        auth_service.logout(conn, settings, token)


@router.post("/register", status_code=201, response_model=DataResponse[CurrentUser],
             summary="Create an account and a new workspace (you become its OWNER) and sign in",
             responses={403: {"model": ErrorResponse, "description": "Registration is disabled."},
                        409: {"model": ErrorResponse, "description": "Email already registered."}})
def register(body: RegisterRequest, response: Response, conn: AuthDb, settings: SettingsDep,
             previous: str | None = Depends(session_token)):
    token, principal = auth_service.register(conn, settings, email=body.email, password=body.password,
                                             display_name=body.display_name, tenant_name=body.tenant_name)
    _end_previous_session(conn, settings, previous)
    _set_session_cookie(response, settings, token)
    return {"data": principal.as_current_user()}


@router.post("/login", response_model=DataResponse[CurrentUser], summary="Sign in with email and password",
             responses={401: {"model": ErrorResponse, "description": "Invalid email or password."},
                        429: {"model": ErrorResponse, "description": "Account temporarily locked."}})
def login(body: LoginRequest, response: Response, conn: AuthDb, settings: SettingsDep,
          previous: str | None = Depends(session_token)):
    token, principal = auth_service.login(conn, settings, email=body.email, password=body.password)
    _end_previous_session(conn, settings, previous)
    _set_session_cookie(response, settings, token)
    return {"data": principal.as_current_user()}


@router.post("/logout", response_model=DataResponse[LogoutResult],
             summary="Sign out: revoke the current session and clear the cookie (idempotent)")
def logout(response: Response, conn: AuthDb, settings: SettingsDep,
           token: str | None = Depends(session_token)):
    _end_previous_session(conn, settings, token)
    _clear_session_cookie(response, settings)
    return {"data": {"status": "logged_out"}}


@router.get("/me", response_model=DataResponse[CurrentUser], summary="The signed-in user, role and workspace",
            responses={401: {"model": ErrorResponse, "description": "Not signed in or session expired."}})
def me(principal: CurrentPrincipal):
    return {"data": principal.as_current_user()}
