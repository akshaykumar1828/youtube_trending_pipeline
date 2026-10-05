"""Authentication, RBAC and tenant isolation against the real database (no auth overrides).

The API runs as yt_auth_rw / yt_app_ro exactly as in production. The admin connection is
used ONLY by the test harness, to inspect stored rows, simulate expiry and clean up every
account created here (emails pytest-*@example.test).
"""

import hashlib
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api_support import BACKEND, TEST_AUTH_SECRET, make_settings
from app.auth.tokens import hash_token
from app.db.auth_engine import get_auth_connection
from app.db.config import admin_settings
from app.main import create_app

PASSWORD = "correct horse battery staple"
TEST_EMAILS = "pytest-%@example.test"
ALLOWED_ORIGIN = "http://localhost:5173"


# --- harness ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def admin():
    engine = create_engine(admin_settings().url, connect_args={"connect_timeout": 5})
    _cleanup(engine)
    yield engine
    _cleanup(engine)
    engine.dispose()


def _cleanup(engine):
    with engine.begin() as c:
        c.execute(text("""DELETE FROM auth.tenants WHERE id IN (
            SELECT m.tenant_id FROM auth.memberships m JOIN auth.users u ON u.id = m.user_id
            WHERE u.email LIKE :p)"""), {"p": TEST_EMAILS})
        c.execute(text("DELETE FROM auth.users WHERE email LIKE :p"), {"p": TEST_EMAILS})


def admin_query(admin, sql, **params):
    with admin.begin() as c:
        return c.execute(text(sql), params).all()


@pytest.fixture(scope="module")
def app(admin):
    return create_app(make_settings())


def client_for(app) -> TestClient:
    # https base URL: the session cookie is Secure, so the client only returns it over https.
    return TestClient(app, base_url="https://testserver")


def new_email(tag="user") -> str:
    return f"pytest-{uuid.uuid4().hex[:12]}-{tag}@example.test"


def register(app, tag="owner", **extra):
    client = client_for(app)
    email = new_email(tag)
    r = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD,
                                                   "display_name": tag.title(), **extra})
    assert r.status_code == 201, r.text
    return client, email, r.json()["data"]


def add_member(owner_client, app, role, tag=None):
    email = new_email(tag or role.lower())
    r = owner_client.post("/api/v1/tenant/members", json={
        "email": email, "display_name": role.title(), "password": PASSWORD, "role": role})
    assert r.status_code == 201, r.text
    client = client_for(app)
    assert client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    return client, email, r.json()["data"]


def error_code(r):
    return r.json()["error"]["code"]


# --- registration -------------------------------------------------------------------------

def test_register_creates_tenant_with_owner_and_signs_in(app):
    client, email, data = register(app, tenant_name="Acme Analytics")
    assert data["user"]["email"] == email and data["user"]["role"] == "OWNER"
    assert sorted(data["user"]["permissions"]) == ["MAKE_PREDICTION", "MANAGE_USERS", "VIEW_ANALYTICS"]
    assert data["tenant"]["name"] == "Acme Analytics"
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["data"] == data


def test_session_cookie_flags_and_token_never_in_body(app):
    client = client_for(app)
    r = client.post("/api/v1/auth/register", json={"email": new_email(), "password": PASSWORD,
                                                   "display_name": "Cookie"})
    cookie = r.headers["set-cookie"]
    token = client.cookies.get("yt_session")
    assert token and len(token) >= 43
    for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/api", "Max-Age=28800"):
        assert flag.lower() in cookie.lower(), flag
    assert token not in r.text
    assert r.headers["cache-control"] == "no-store"


def test_password_is_argon2id_hashed_and_session_token_is_hmac_only(app, admin):
    client, email, _ = register(app)
    (pw_hash,), = admin_query(admin, "SELECT password_hash FROM auth.users WHERE email = :e", e=email)
    assert pw_hash.startswith("$argon2id$") and PASSWORD not in pw_hash
    token = client.cookies.get("yt_session")
    rows = admin_query(admin, """SELECT s.token_hash FROM auth.sessions s JOIN auth.users u ON u.id = s.user_id
                                 WHERE u.email = :e""", e=email)
    assert [bytes(r.token_hash) for r in rows] == [hash_token(token, TEST_AUTH_SECRET.encode())]
    assert token.encode() not in bytes(rows[0].token_hash)


def test_register_duplicate_email_is_case_insensitive_409(app):
    _, email, _ = register(app)
    r = client_for(app).post("/api/v1/auth/register", json={
        "email": email.upper(), "password": PASSWORD, "display_name": "Dup"})
    assert r.status_code == 409 and error_code(r) == "email_taken" and r.json()["error"]["field"] == "email"


@pytest.mark.parametrize("change, field", [
    ({"password": "short"}, "password"),
    ({"password": "x" * 129}, "password"),
    ({"email": "not-an-email"}, "email"),
    ({"display_name": "   "}, "display_name"),
    ({"tenant_id": str(uuid.uuid4())}, "tenant_id"),  # the browser cannot pick a tenant
    ({"role": "OWNER"}, "role"),
])
def test_register_validation(app, change, field):
    body = {"email": new_email(), "password": PASSWORD, "display_name": "V", **change}
    r = client_for(app).post("/api/v1/auth/register", json=body)
    assert r.status_code == 422 and error_code(r) == "invalid_request"
    assert r.json()["error"]["field"] == field
    if "password" in change:
        assert change["password"] not in r.text  # input is never echoed


def test_registration_can_be_disabled(admin):
    closed = create_app(make_settings(auth_registration_enabled=False))
    r = client_for(closed).post("/api/v1/auth/register", json={
        "email": new_email(), "password": PASSWORD, "display_name": "X"})
    assert r.status_code == 403 and error_code(r) == "registration_closed"


# --- login / logout / sessions ------------------------------------------------------------

def test_login_success_and_generic_failures(app):
    _, email, _ = register(app)
    client = client_for(app)
    wrong = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong password!!"})
    unknown = client.post("/api/v1/auth/login", json={"email": new_email(), "password": PASSWORD})
    for r in (wrong, unknown):
        assert r.status_code == 401 and error_code(r) == "invalid_credentials"
        assert "set-cookie" not in r.headers
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
    ok = client.post("/api/v1/auth/login", json={"email": f"  {email.upper()} ", "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["data"]["user"]["email"] == email
    assert client.get("/api/v1/auth/me").status_code == 200


def test_lockout_after_repeated_failures(app, admin):
    _, email, _ = register(app)
    client = client_for(app)
    for _ in range(5):
        r = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong password!!"})
        assert r.status_code == 401
    locked = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert locked.status_code == 429 and error_code(locked) == "too_many_attempts"
    # Lock expiry (simulated): the correct password works again and the counter resets.
    admin_query(admin, "UPDATE auth.users SET locked_until = now() - interval '1 second' WHERE email = :e "
                       "RETURNING id", e=email)
    assert client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    (count, until), = admin_query(admin, "SELECT failed_login_count, locked_until FROM auth.users "
                                         "WHERE email = :e", e=email)
    assert count == 0 and until is None


def test_logout_revokes_the_session_server_side(app, admin):
    client, email, _ = register(app)
    token = client.cookies.get("yt_session")
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 200 and r.json() == {"data": {"status": "logged_out"}}
    assert "max-age=0" in r.headers["set-cookie"].lower()
    assert client.get("/api/v1/auth/me").status_code == 401
    replay = client_for(app)
    replay.cookies.set("yt_session", token, domain="testserver", path="/api")
    assert replay.get("/api/v1/auth/me").status_code == 401  # a stolen copy is useless after logout
    assert admin_query(admin, """SELECT 1 FROM auth.sessions s JOIN auth.users u ON u.id = s.user_id
                                 WHERE u.email = :e""", e=email) == []
    assert client_for(app).post("/api/v1/auth/logout").status_code == 200  # idempotent


def test_expired_session_is_rejected(app, admin):
    client, email, _ = register(app)
    admin_query(admin, """UPDATE auth.sessions SET created_at = now() - interval '2 hours',
                              expires_at = now() - interval '1 hour'
                          WHERE user_id = (SELECT id FROM auth.users WHERE email = :e) RETURNING 1""", e=email)
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401 and error_code(r) == "not_authenticated"


def test_forged_or_garbage_cookie_is_rejected(app):
    client = client_for(app)
    for value in ("x", "A" * 43, "A" * 500):
        client.cookies.set("yt_session", value, domain="testserver", path="/api")
        assert client.get("/api/v1/meta/filters").status_code == 401


def test_login_replaces_previous_session(app, admin):
    client, email, _ = register(app)
    first = client.cookies.get("yt_session")
    assert client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    assert client.cookies.get("yt_session") != first
    (n,), = admin_query(admin, """SELECT count(*) FROM auth.sessions s JOIN auth.users u ON u.id = s.user_id
                                  WHERE u.email = :e""", e=email)
    assert n == 1


# --- protection inventory -----------------------------------------------------------------

PUBLIC_API = {("POST", "/api/v1/auth/register"), ("POST", "/api/v1/auth/login"), ("POST", "/api/v1/auth/logout")}


def _protected_routes(app):
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1"):
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            if (method, path) not in PUBLIC_API:
                yield method, path


def test_every_api_route_except_auth_entry_points_requires_a_session(app):
    client = client_for(app)
    routes = sorted(_protected_routes(app))
    assert len(routes) >= 17  # analytics, videos, predictions, me, tenant endpoints
    for method, path in routes:
        url = path.replace("{video_id}", "abc").replace("{user_id}", str(uuid.uuid4()))
        r = client.request(method, url, json={} if method in ("POST", "PATCH") else None)
        assert r.status_code == 401, (method, path, r.status_code)
        assert error_code(r) == "not_authenticated"


def test_health_endpoints_stay_public(app):
    client = client_for(app)
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code in (200, 503)  # never 401


def test_signed_in_user_reaches_analytics_and_predictions(app):
    client, _, _ = register(app)
    assert client.get("/api/v1/meta/filters").status_code == 200
    assert client.get("/api/v1/overview/kpis").status_code == 200
    r = client.get("/api/v1/predictions/model-info")
    assert r.status_code == 503 and error_code(r) == "model_unavailable"  # authorized; ML disabled here


# --- roles --------------------------------------------------------------------------------

def test_member_permissions(app):
    owner, _, _ = register(app)
    member, _, data = add_member(owner, app, "MEMBER")
    me = member.get("/api/v1/auth/me").json()["data"]["user"]
    assert me["role"] == "MEMBER" and sorted(me["permissions"]) == ["MAKE_PREDICTION", "VIEW_ANALYTICS"]
    assert member.get("/api/v1/overview/kpis").status_code == 200
    assert member.get("/api/v1/tenant").status_code == 200
    for r in (member.get("/api/v1/tenant/members"),
              member.post("/api/v1/tenant/members", json={"email": new_email(), "display_name": "x",
                                                          "password": PASSWORD, "role": "MEMBER"}),
              member.patch(f"/api/v1/tenant/members/{data['id']}", json={"role": "ADMIN"})):
        assert r.status_code == 403 and error_code(r) == "forbidden"


def test_admin_manages_members_but_not_owners(app):
    owner, _, owner_data = register(app)
    admin_client, _, admin_data = add_member(owner, app, "ADMIN")
    member_r = admin_client.post("/api/v1/tenant/members", json={
        "email": new_email("m"), "display_name": "M", "password": PASSWORD, "role": "MEMBER"})
    assert member_r.status_code == 201
    member_id = member_r.json()["data"]["id"]
    assert admin_client.get("/api/v1/tenant/members").status_code == 200
    promoted = admin_client.patch(f"/api/v1/tenant/members/{member_id}", json={"role": "ADMIN"})
    assert promoted.status_code == 200 and promoted.json()["data"]["role"] == "ADMIN"

    forbidden = [
        admin_client.post("/api/v1/tenant/members", json={
            "email": new_email(), "display_name": "O", "password": PASSWORD, "role": "OWNER"}),
        admin_client.patch(f"/api/v1/tenant/members/{member_id}", json={"role": "OWNER"}),
        admin_client.patch(f"/api/v1/tenant/members/{owner_data['user']['id']}", json={"is_active": False}),
        admin_client.patch(f"/api/v1/tenant/members/{owner_data['user']['id']}", json={"role": "MEMBER"}),
        admin_client.patch(f"/api/v1/tenant/members/{admin_data['id']}", json={"role": "OWNER"}),  # self
    ]
    for r in forbidden:
        assert r.status_code == 403 and error_code(r) == "forbidden", r.text


def test_nobody_changes_their_own_membership(app):
    owner, _, data = register(app)
    r = owner.patch(f"/api/v1/tenant/members/{data['user']['id']}", json={"role": "MEMBER"})
    assert r.status_code == 403
    assert owner.get("/api/v1/auth/me").json()["data"]["user"]["role"] == "OWNER"


def test_owner_can_grant_owner_and_be_demoted_by_another_owner(app):
    owner, _, owner_data = register(app)
    co_owner, _, _ = add_member(owner, app, "OWNER")
    r = co_owner.patch(f"/api/v1/tenant/members/{owner_data['user']['id']}", json={"role": "ADMIN"})
    assert r.status_code == 200 and r.json()["data"]["role"] == "ADMIN"


def test_role_change_applies_to_existing_sessions_immediately(app):
    owner, _, _ = register(app)
    member, _, data = add_member(owner, app, "MEMBER")
    assert member.get("/api/v1/tenant/members").status_code == 403
    owner.patch(f"/api/v1/tenant/members/{data['id']}", json={"role": "ADMIN"})
    assert member.get("/api/v1/tenant/members").status_code == 200
    owner.patch(f"/api/v1/tenant/members/{data['id']}", json={"role": "MEMBER"})
    assert member.get("/api/v1/tenant/members").status_code == 403


def test_deactivation_revokes_sessions_and_blocks_sign_in(app, admin):
    owner, _, _ = register(app)
    member, email, data = add_member(owner, app, "MEMBER")
    r = owner.patch(f"/api/v1/tenant/members/{data['id']}", json={"is_active": False})
    assert r.status_code == 200 and r.json()["data"]["is_active"] is False
    assert member.get("/api/v1/auth/me").status_code == 401
    assert admin_query(admin, "SELECT 1 FROM auth.sessions WHERE user_id = :u", u=data["id"]) == []
    login = client_for(app).post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 401 and error_code(login) == "invalid_credentials"  # no account-state leak
    owner.patch(f"/api/v1/tenant/members/{data['id']}", json={"is_active": True})
    assert client_for(app).post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200


def test_member_creation_duplicate_email_and_empty_patch(app):
    owner, email, _ = register(app)
    dup = owner.post("/api/v1/tenant/members", json={
        "email": email, "display_name": "D", "password": PASSWORD, "role": "MEMBER"})
    assert dup.status_code == 409 and error_code(dup) == "email_taken"
    _, _, data = add_member(owner, app, "MEMBER")
    empty = owner.patch(f"/api/v1/tenant/members/{data['id']}", json={})
    assert empty.status_code == 422


# --- tenant isolation ---------------------------------------------------------------------

def test_tenant_isolation(app, admin):
    owner_a, _, a = register(app, "a-owner")
    owner_b, _, b = register(app, "b-owner")
    _, email_b_member, b_member = add_member(owner_b, app, "MEMBER", "b-member")

    members_a = owner_a.get("/api/v1/tenant/members").json()["data"]
    assert [m["id"] for m in members_a] == [a["user"]["id"]]
    assert owner_a.get("/api/v1/tenant").json()["data"]["id"] == a["tenant"]["id"]

    # Cross-tenant ids look exactly like unknown ids, and nothing changes.
    for target in (b_member["id"], b["user"]["id"]):
        r = owner_a.patch(f"/api/v1/tenant/members/{target}", json={"is_active": False})
        assert r.status_code == 404 and error_code(r) == "not_found"
    unknown = owner_a.patch(f"/api/v1/tenant/members/{uuid.uuid4()}", json={"is_active": False})
    assert unknown.json()["error"]["message"] == r.json()["error"]["message"]
    (active,), = admin_query(admin, "SELECT is_active FROM auth.users WHERE email = :e", e=email_b_member)
    assert active is True

    # A browser-supplied tenant id is never used: ignored in the query string, rejected in bodies.
    assert owner_a.get("/api/v1/tenant", params={"tenant_id": b["tenant"]["id"]}).json()["data"]["id"] == \
        a["tenant"]["id"]
    assert owner_a.get("/api/v1/tenant/members", params={"tenant_id": b["tenant"]["id"]}).json()["data"] == \
        members_a
    smuggled = owner_a.post("/api/v1/tenant/members", json={
        "email": new_email(), "display_name": "S", "password": PASSWORD, "role": "MEMBER",
        "tenant_id": b["tenant"]["id"]})
    assert smuggled.status_code == 422
    created = owner_a.post("/api/v1/tenant/members", json={
        "email": new_email("a-member"), "display_name": "A M", "password": PASSWORD, "role": "MEMBER"})
    (tenant,), = admin_query(admin, "SELECT tenant_id FROM auth.memberships WHERE user_id = :u",
                             u=created.json()["data"]["id"])
    assert str(tenant) == a["tenant"]["id"]


def test_analytics_dataset_is_shared_not_per_tenant(app):
    owner_a, _, _ = register(app)
    owner_b, _, _ = register(app)
    assert owner_a.get("/api/v1/overview/kpis").json() == owner_b.get("/api/v1/overview/kpis").json()


# --- CSRF / origin ------------------------------------------------------------------------

def test_cross_origin_state_changes_are_rejected(app):
    owner, email, _ = register(app)
    evil = {"Origin": "https://evil.example"}
    for r in (owner.post("/api/v1/auth/logout", headers=evil),
              owner.post("/api/v1/tenant/members", headers=evil, json={
                  "email": new_email(), "display_name": "E", "password": PASSWORD, "role": "MEMBER"}),
              client_for(app).post("/api/v1/auth/login", headers={"Origin": "null"},
                                   json={"email": email, "password": PASSWORD})):
        assert r.status_code == 403 and error_code(r) == "csrf_rejected"
    assert owner.get("/api/v1/auth/me").status_code == 200  # the forged logout did nothing

    for origin in (ALLOWED_ORIGIN, "https://testserver"):  # the SPA, and the API's own docs page
        r = client_for(app).post("/api/v1/auth/login", headers={"Origin": origin},
                                 json={"email": email, "password": PASSWORD})
        assert r.status_code == 200


def test_spa_origin_gets_credentialed_cors(app):
    r = client_for(app).options("/api/v1/auth/login", headers={
        "Origin": ALLOWED_ORIGIN, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert r.headers["access-control-allow-credentials"] == "true"


# --- database privileges and migration ----------------------------------------------------

def test_auth_role_cannot_touch_analytics_or_raw_data(admin):
    rows = admin_query(admin, """
        SELECT n.nspname, c.relname
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('public', 'app') AND c.relkind IN ('r', 'v', 'm', 'p')
          AND (has_table_privilege('yt_auth_rw', c.oid, 'SELECT')
               OR has_table_privilege('yt_auth_rw', c.oid, 'INSERT, UPDATE, DELETE, TRUNCATE'))
    """)
    assert rows == []
    with get_auth_connection() as c:
        assert c.execute(text("SELECT has_schema_privilege('app', 'USAGE')")).scalar() is False
        assert c.execute(text("SHOW statement_timeout")).scalar() == "5s"
        assert c.execute(text("SELECT current_user")).scalar() == "yt_auth_rw"


def test_auth_role_privileges_are_minimal(admin):
    (flags,), = admin_query(admin, """
        SELECT ARRAY[
            has_table_privilege('yt_auth_rw', 'auth.users', 'DELETE'),
            has_table_privilege('yt_auth_rw', 'auth.tenants', 'DELETE'),
            has_table_privilege('yt_auth_rw', 'auth.memberships', 'DELETE'),
            has_table_privilege('yt_auth_rw', 'auth.users', 'TRUNCATE'),
            has_table_privilege('yt_auth_rw', 'auth.sessions', 'UPDATE'),
            has_schema_privilege('yt_auth_rw', 'auth', 'CREATE'),
            r.rolsuper, r.rolcreaterole, r.rolcreatedb, r.rolbypassrls]
        FROM pg_roles r WHERE r.rolname = 'yt_auth_rw'
    """)
    assert flags == [False] * 10


def test_read_only_analytics_role_cannot_read_auth(admin):
    (usage, users), = admin_query(admin, """
        SELECT has_schema_privilege('yt_app_ro', 'auth', 'USAGE'),
               has_table_privilege('yt_app_ro', 'auth.users', 'SELECT')""")
    assert usage is False and users is False


def test_auth_migrations_applied_with_matching_checksums(admin):
    applied = {r.version: r.checksum for r in admin_query(admin, "SELECT version, checksum FROM app.schema_migrations")}
    for version in ("005", "006"):
        (path,) = (BACKEND / "migrations").glob(f"{version}_*.sql")
        content = path.read_text(encoding="utf-8")
        assert applied[version] == hashlib.sha256(content.encode("utf-8")).hexdigest()
