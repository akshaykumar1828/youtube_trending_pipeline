"""Authentication and tenant membership use cases.

Each function runs on one yt_auth_rw connection and commits explicitly. Authorization
decisions use only the server-side Principal (resolved from the session cookie on every
request), never ids or roles supplied by the client.
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from app.auth import passwords
from app.auth.permissions import Permission, Role, can_assign_role, can_manage_member, permissions_for
from app.auth.tokens import hash_token, new_session_token
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    InvalidCredentialsError,
    NotFoundError,
    RegistrationClosedError,
    TooManyAttemptsError,
)
from app.core.settings import Settings
from app.repositories import auth as repo

logger = logging.getLogger("app.auth")


@dataclass(frozen=True)
class Principal:
    """The authenticated identity of one request."""

    user_id: uuid.UUID
    email: str
    display_name: str
    role: Role
    tenant_id: uuid.UUID
    tenant_name: str

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_for(self.role)

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions

    def as_current_user(self) -> dict:
        return {
            "user": {"id": self.user_id, "email": self.email, "display_name": self.display_name,
                     "role": self.role, "permissions": sorted(self.permissions)},
            "tenant": {"id": self.tenant_id, "name": self.tenant_name},
        }


def _principal(row) -> Principal:
    return Principal(user_id=row.user_id, email=row.email, display_name=row.display_name,
                     role=Role(row.role), tenant_id=row.tenant_id, tenant_name=row.tenant_name)


def _email_taken() -> ConflictError:
    return ConflictError("email_taken", "An account with this email already exists.", "email")


def _start_session(conn: Connection, settings: Settings, user_id, tenant_id) -> tuple[str, Principal]:
    token = new_session_token()
    token_hash = hash_token(token, settings.require_auth_secret())
    repo.delete_expired_sessions(conn, user_id)
    repo.create_session(conn, token_hash, user_id, tenant_id, settings.auth_session_ttl_minutes)
    row = repo.find_principal(conn, token_hash)
    conn.commit()
    return token, _principal(row)


# --- sessions ------------------------------------------------------------------------------

def principal_for_token(conn: Connection, settings: Settings, token: str) -> Principal | None:
    row = repo.find_principal(conn, hash_token(token, settings.require_auth_secret()))
    return _principal(row) if row else None


def register(conn: Connection, settings: Settings, *, email: str, password: str,
             display_name: str, tenant_name: str | None) -> tuple[str, Principal]:
    """New tenant with the caller as its OWNER; returns a signed-in session."""
    if not settings.auth_registration_enabled:
        raise RegistrationClosedError()
    password_hash = passwords.hash_password(password)
    try:
        tenant_id = repo.create_tenant(conn, tenant_name or f"{display_name}'s workspace"[:100])
        user_id = repo.create_user(conn, email, display_name, password_hash)
        repo.create_membership(conn, user_id, tenant_id, Role.OWNER)
    except IntegrityError as exc:
        conn.rollback()
        if repo.is_unique_email_violation(exc):
            raise _email_taken() from None
        raise
    logger.info("registered user %s in new tenant %s", user_id, tenant_id)
    return _start_session(conn, settings, user_id, tenant_id)


def login(conn: Connection, settings: Settings, *, email: str, password: str) -> tuple[str, Principal]:
    """Generic failure for unknown email, wrong password and inactive account; per-account
    lockout after repeated failures. Password verification always runs (equal timing)."""
    candidate = repo.find_login_candidate(conn, email)
    if candidate is None:
        passwords.burn_verification(password)
        raise InvalidCredentialsError()
    if candidate.locked:
        passwords.burn_verification(password)
        raise TooManyAttemptsError()
    if not passwords.verify_password(candidate.password_hash, password):
        repo.record_failed_login(conn, candidate.user_id, settings.auth_max_failed_logins,
                                 settings.auth_lockout_minutes)
        conn.commit()
        logger.info("failed sign-in for user %s", candidate.user_id)
        raise InvalidCredentialsError()
    if not candidate.is_active:
        raise InvalidCredentialsError()
    new_hash = passwords.hash_password(password) if passwords.needs_rehash(candidate.password_hash) else None
    repo.record_successful_login(conn, candidate.user_id, new_hash)
    return _start_session(conn, settings, candidate.user_id, candidate.tenant_id)


def logout(conn: Connection, settings: Settings, token: str) -> None:
    repo.delete_session(conn, hash_token(token, settings.require_auth_secret()))
    conn.commit()


# --- tenant and members (always scoped to principal.tenant_id) -----------------------------

def tenant_detail(conn: Connection, principal: Principal) -> dict:
    row = repo.get_tenant(conn, principal.tenant_id)
    if row is None:  # pragma: no cover - the session join guarantees the tenant exists
        raise NotFoundError("Tenant not found")
    return {"id": row.id, "name": row.name, "created_at": row.created_at, "member_count": row.member_count}


def _member(row) -> dict:
    return {"id": row.user_id, "email": row.email, "display_name": row.display_name, "role": Role(row.role),
            "is_active": row.is_active, "created_at": row.created_at, "last_login_at": row.last_login_at}


def list_members(conn: Connection, principal: Principal) -> list[dict]:
    return [_member(r) for r in repo.list_members(conn, principal.tenant_id)]


def create_member(conn: Connection, principal: Principal, *, email: str, display_name: str,
                  password: str, role: Role) -> dict:
    if not can_assign_role(principal.role, role):
        raise ForbiddenError(f"Your role cannot create {role} members.")
    password_hash = passwords.hash_password(password)
    try:
        user_id = repo.create_user(conn, email, display_name, password_hash)
        repo.create_membership(conn, user_id, principal.tenant_id, role)
    except IntegrityError as exc:
        conn.rollback()
        if repo.is_unique_email_violation(exc):
            raise _email_taken() from None
        raise
    row = repo.get_member(conn, principal.tenant_id, user_id)
    conn.commit()
    logger.info("user %s created member %s (%s) in tenant %s", principal.user_id, user_id, role,
                principal.tenant_id)
    return _member(row)


def update_member(conn: Connection, principal: Principal, user_id: uuid.UUID, *,
                  role: Role | None, is_active: bool | None) -> dict:
    repo.lock_tenant(conn, principal.tenant_id)
    target = repo.get_member(conn, principal.tenant_id, user_id)
    if target is None:  # unknown id and other tenants' users look the same
        raise NotFoundError("Member not found")
    if target.user_id == principal.user_id:
        raise ForbiddenError("You cannot change your own role or status.")
    current = Role(target.role)
    if not can_manage_member(principal.role, current):
        raise ForbiddenError(f"Your role cannot change {current} members.")
    if role is not None and not can_assign_role(principal.role, role):
        raise ForbiddenError(f"Your role cannot assign the {role} role.")

    loses_owner = current is Role.OWNER and target.is_active and (
        (role is not None and role is not Role.OWNER) or is_active is False)
    if loses_owner and repo.count_other_active_owners(conn, principal.tenant_id, user_id) == 0:
        raise ConflictError("last_owner", "A workspace must keep at least one active owner.")

    if role is not None and role is not current:
        repo.update_member_role(conn, principal.tenant_id, user_id, role)
    if is_active is not None and is_active != target.is_active:
        repo.set_user_active(conn, user_id, is_active)
    if is_active is False:
        repo.delete_user_sessions(conn, user_id)
    row = repo.get_member(conn, principal.tenant_id, user_id)
    conn.commit()
    logger.info("user %s updated member %s in tenant %s (role=%s, is_active=%s)", principal.user_id,
                user_id, principal.tenant_id, role, is_active)
    return _member(row)
