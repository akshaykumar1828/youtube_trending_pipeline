"""Users, tenants, memberships and sessions (schema `auth`, role yt_auth_rw).

Every tenant-scoped query takes the tenant id of the AUTHENTICATED principal and filters on
it in SQL; ids from the request are only ever looked up inside that tenant. Functions here
never commit: the service layer owns transactions.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection, Row
from sqlalchemy.exc import IntegrityError

EMAIL_UNIQUE_CONSTRAINT = "users_email_key"

_MEMBER_COLUMNS = """
    u.id AS user_id, u.email, u.display_name, u.is_active, u.created_at, u.last_login_at, m.role
"""


def is_unique_email_violation(exc: IntegrityError) -> bool:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", None) == EMAIL_UNIQUE_CONSTRAINT


# --- sign-in -------------------------------------------------------------------------------

def find_login_candidate(conn: Connection, email: str) -> Row | None:
    return conn.execute(text("""
        SELECT u.id AS user_id, u.password_hash, u.is_active,
               coalesce(u.locked_until > now(), false) AS locked,
               m.tenant_id
        FROM auth.users u
        JOIN auth.memberships m ON m.user_id = u.id
        WHERE u.email = :email
    """), {"email": email}).first()


def record_failed_login(conn: Connection, user_id, max_failed: int, lockout_minutes: int) -> None:
    """Count a failed password; at `max_failed` consecutive failures lock the account for
    `lockout_minutes` and start counting again."""
    conn.execute(text("""
        UPDATE auth.users SET
            locked_until = CASE WHEN failed_login_count + 1 >= :max_failed
                                THEN now() + make_interval(mins => :lockout) ELSE locked_until END,
            failed_login_count = CASE WHEN failed_login_count + 1 >= :max_failed
                                      THEN 0 ELSE failed_login_count + 1 END,
            updated_at = now()
        WHERE id = :user_id
    """), {"user_id": user_id, "max_failed": max_failed, "lockout": lockout_minutes})


def record_successful_login(conn: Connection, user_id, new_password_hash: str | None) -> None:
    conn.execute(text("""
        UPDATE auth.users SET
            failed_login_count = 0, locked_until = NULL, last_login_at = now(),
            password_hash = coalesce(:new_hash, password_hash), updated_at = now()
        WHERE id = :user_id
    """), {"user_id": user_id, "new_hash": new_password_hash})


# --- sessions ------------------------------------------------------------------------------

def create_session(conn: Connection, token_hash: bytes, user_id, tenant_id, ttl_minutes: int) -> None:
    conn.execute(text("""
        INSERT INTO auth.sessions (token_hash, user_id, tenant_id, expires_at)
        VALUES (:token_hash, :user_id, :tenant_id, now() + make_interval(mins => :ttl))
    """), {"token_hash": token_hash, "user_id": user_id, "tenant_id": tenant_id, "ttl": ttl_minutes})


def delete_session(conn: Connection, token_hash: bytes) -> None:
    conn.execute(text("DELETE FROM auth.sessions WHERE token_hash = :h"), {"h": token_hash})


def delete_user_sessions(conn: Connection, user_id) -> None:
    conn.execute(text("DELETE FROM auth.sessions WHERE user_id = :u"), {"u": user_id})


def delete_expired_sessions(conn: Connection, user_id) -> None:
    conn.execute(text("DELETE FROM auth.sessions WHERE user_id = :u AND expires_at <= now()"),
                 {"u": user_id})


def find_principal(conn: Connection, token_hash: bytes) -> Row | None:
    """The identity behind a live session: unexpired, active user, current membership role."""
    return conn.execute(text("""
        SELECT u.id AS user_id, u.email, u.display_name, m.role,
               t.id AS tenant_id, t.name AS tenant_name
        FROM auth.sessions s
        JOIN auth.memberships m ON m.user_id = s.user_id AND m.tenant_id = s.tenant_id
        JOIN auth.users u ON u.id = s.user_id
        JOIN auth.tenants t ON t.id = s.tenant_id
        WHERE s.token_hash = :h AND s.expires_at > now() AND u.is_active
    """), {"h": token_hash}).first()


# --- accounts and tenants ------------------------------------------------------------------

def create_tenant(conn: Connection, name: str):
    return conn.execute(text("INSERT INTO auth.tenants (name) VALUES (:name) RETURNING id"),
                        {"name": name}).scalar_one()


def create_user(conn: Connection, email: str, display_name: str, password_hash: str):
    """Raises IntegrityError (see is_unique_email_violation) when the email is taken."""
    return conn.execute(text("""
        INSERT INTO auth.users (email, display_name, password_hash)
        VALUES (:email, :display_name, :password_hash) RETURNING id
    """), {"email": email, "display_name": display_name, "password_hash": password_hash}).scalar_one()


def create_membership(conn: Connection, user_id, tenant_id, role: str) -> None:
    conn.execute(text("INSERT INTO auth.memberships (user_id, tenant_id, role) VALUES (:u, :t, :r)"),
                 {"u": user_id, "t": tenant_id, "r": role})


def get_tenant(conn: Connection, tenant_id) -> Row | None:
    return conn.execute(text("""
        SELECT t.id, t.name, t.created_at,
               (SELECT count(*) FROM auth.memberships m WHERE m.tenant_id = t.id) AS member_count
        FROM auth.tenants t WHERE t.id = :t
    """), {"t": tenant_id}).first()


def lock_tenant(conn: Connection, tenant_id) -> None:
    """Serialize membership changes within a tenant (keeps the last-owner check race-free)."""
    conn.execute(text("SELECT id FROM auth.tenants WHERE id = :t FOR UPDATE"), {"t": tenant_id})


def list_members(conn: Connection, tenant_id) -> list[Row]:
    return list(conn.execute(text(f"""
        SELECT {_MEMBER_COLUMNS}
        FROM auth.memberships m JOIN auth.users u ON u.id = m.user_id
        WHERE m.tenant_id = :t
        ORDER BY u.created_at, u.email
    """), {"t": tenant_id}))


def get_member(conn: Connection, tenant_id, user_id) -> Row | None:
    return conn.execute(text(f"""
        SELECT {_MEMBER_COLUMNS}
        FROM auth.memberships m JOIN auth.users u ON u.id = m.user_id
        WHERE m.tenant_id = :t AND m.user_id = :u
    """), {"t": tenant_id, "u": user_id}).first()


def count_other_active_owners(conn: Connection, tenant_id, user_id) -> int:
    return conn.execute(text("""
        SELECT count(*) FROM auth.memberships m JOIN auth.users u ON u.id = m.user_id
        WHERE m.tenant_id = :t AND m.role = 'OWNER' AND u.is_active AND u.id <> :u
    """), {"t": tenant_id, "u": user_id}).scalar_one()


def update_member_role(conn: Connection, tenant_id, user_id, role: str) -> None:
    conn.execute(text("UPDATE auth.memberships SET role = :r WHERE tenant_id = :t AND user_id = :u"),
                 {"r": role, "t": tenant_id, "u": user_id})


def set_user_active(conn: Connection, user_id, is_active: bool) -> None:
    conn.execute(text("UPDATE auth.users SET is_active = :a, updated_at = now() WHERE id = :u"),
                 {"a": is_active, "u": user_id})
