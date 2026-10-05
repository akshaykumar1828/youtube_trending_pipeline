"""Auth unit tests (no database): role/permission matrix, role-management rules, password
hashing and policy, token hashing, settings, timing equalisation, permission dependency."""

import pytest
from fastapi.testclient import TestClient

from api_support import make_settings, sign_in_as
from app.auth import passwords
from app.auth.permissions import Permission, Role, can_assign_role, can_manage_member, permissions_for
from app.auth.tokens import hash_token, new_session_token
from app.core.settings import Settings, SettingsError
from app.main import create_app
from app.services import auth as auth_service

P = Permission


def test_role_permission_matrix():
    assert permissions_for(Role.OWNER) == {P.VIEW_ANALYTICS, P.MAKE_PREDICTION, P.MANAGE_USERS}
    assert permissions_for(Role.ADMIN) == {P.VIEW_ANALYTICS, P.MAKE_PREDICTION, P.MANAGE_USERS}
    assert permissions_for(Role.MEMBER) == {P.VIEW_ANALYTICS, P.MAKE_PREDICTION}


@pytest.mark.parametrize("actor, role, allowed", [
    (Role.OWNER, Role.OWNER, True), (Role.OWNER, Role.ADMIN, True), (Role.OWNER, Role.MEMBER, True),
    (Role.ADMIN, Role.OWNER, False), (Role.ADMIN, Role.ADMIN, True), (Role.ADMIN, Role.MEMBER, True),
    (Role.MEMBER, Role.OWNER, False), (Role.MEMBER, Role.ADMIN, False), (Role.MEMBER, Role.MEMBER, False),
])
def test_role_assignment_and_management_rules(actor, role, allowed):
    assert can_assign_role(actor, role) is allowed
    assert can_manage_member(actor, role) is allowed  # same hierarchy for changing a member


def test_password_hash_is_argon2id_salted_and_verifies():
    h1, h2 = passwords.hash_password("a long enough password"), passwords.hash_password("a long enough password")
    assert h1.startswith("$argon2id$") and h1 != h2
    assert passwords.verify_password(h1, "a long enough password")
    assert not passwords.verify_password(h1, "a long enough passworD")
    assert not passwords.verify_password("not-a-hash", "whatever")
    assert not passwords.needs_rehash(h1)


@pytest.mark.parametrize("password, ok", [
    ("x" * 11, False), ("x" * 12, True), ("x" * 128, True), ("x" * 129, False), (" " * 12, False),
])
def test_password_policy(password, ok):
    assert (passwords.password_problem(password) is None) is ok


def test_session_tokens_are_random_and_hashed_with_the_key():
    a, b = new_session_token(), new_session_token()
    assert a != b and len(a) >= 43
    assert hash_token(a, b"k" * 32) != hash_token(a, b"j" * 32)
    assert len(hash_token(a, b"k" * 32)) == 32


def test_auth_secret_required_and_never_in_repr():
    with pytest.raises(SettingsError, match="AUTH_SECRET_KEY"):
        create_app(make_settings(auth_secret_key=None))
    with pytest.raises(SettingsError):
        Settings(auth_secret_key="too-short")
    s = make_settings()
    assert s.auth_secret_key not in repr(s)


@pytest.mark.parametrize("bad", [{"auth_session_ttl_minutes": 1}, {"auth_max_failed_logins": 0}])
def test_auth_settings_validated(bad):
    with pytest.raises(SettingsError):
        make_settings(**bad)


class _Conn:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


def test_unknown_email_still_runs_a_password_verification(monkeypatch):
    calls = []
    monkeypatch.setattr(auth_service.repo, "find_login_candidate", lambda conn, email: None)
    monkeypatch.setattr(auth_service.passwords, "burn_verification", lambda pw: calls.append(pw))
    with pytest.raises(Exception) as exc:
        auth_service.login(_Conn(), make_settings(), email="nobody@example.test", password="pw")
    assert exc.value.code == "invalid_credentials" and calls == ["pw"]


def test_failed_login_counter_is_committed(monkeypatch):
    class Candidate:
        user_id, password_hash, is_active, locked, tenant_id = 1, passwords.hash_password("x" * 12), True, False, 2
    recorded = []
    monkeypatch.setattr(auth_service.repo, "find_login_candidate", lambda conn, email: Candidate)
    monkeypatch.setattr(auth_service.repo, "record_failed_login", lambda *a: recorded.append(a[1:]))
    conn = _Conn()
    with pytest.raises(Exception):
        auth_service.login(conn, make_settings(), email="a@example.test", password="y" * 12)
    assert recorded == [(1, 5, 15)] and conn.commits == 1


def test_permission_dependency_denies_missing_permission(monkeypatch):
    from app.auth import permissions
    monkeypatch.setitem(permissions.ROLE_PERMISSIONS, Role.MEMBER, frozenset({P.VIEW_ANALYTICS}))
    app = create_app(make_settings())
    sign_in_as(app, Role.MEMBER)
    with TestClient(app) as c:
        r = c.get("/api/v1/predictions/model-info")
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
        assert r.json()["error"]["request_id"] == r.headers["x-request-id"]


def test_unauthenticated_requests_never_reach_the_database(monkeypatch):
    from app.api import deps

    def boom():
        raise AssertionError("database touched")
    monkeypatch.setattr(deps, "get_auth_connection", boom)
    monkeypatch.setattr(deps, "get_connection", boom)
    with TestClient(create_app(make_settings())) as c:
        for url in ("/api/v1/overview/kpis", "/api/v1/auth/me", "/api/v1/tenant/members"):
            r = c.get(url)
            assert r.status_code == 401 and r.json()["error"]["code"] == "not_authenticated"
