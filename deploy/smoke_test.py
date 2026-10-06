"""Real-HTTP smoke test of the running Docker stack, through nginx (no mocks, stdlib only).

    python deploy/smoke_test.py [--base http://localhost:8080]
    python deploy/smoke_test.py --persisted-login    # after a restart: that account still works

Creates throwaway accounts named smoke-*@example.test in the DEPLOYMENT database (never the
dev database). Passwords are generated per run and never printed; the last run's owner
credentials are kept in the OS temp directory for --persisted-login.
"""

import argparse
import json
import re
import secrets
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATE = Path(tempfile.gettempdir()) / "yt_trending_smoke_state.json"
RESULTS: list[tuple[str, bool, str]] = []


class Client:
    """Minimal browser stand-in: sends Origin like the SPA and keeps the session cookie.
    (Cookies are tracked by hand because the Secure cookie is set over http://localhost,
    which browsers accept but urllib's cookie jar does not.)"""

    def __init__(self, base: str):
        self.base, self.cookie = base.rstrip("/"), None

    def request(self, method, path, body=None, origin=None, cookie=True):
        headers = {"Origin": origin or self.base}
        data = None
        if body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        if cookie and self.cookie:
            headers["Cookie"] = f"yt_session={self.cookie}"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as err:
            resp = err
        raw = resp.read()
        set_cookie = resp.headers.get("Set-Cookie") or ""
        match = re.match(r"yt_session=([^;]*)", set_cookie)
        if match:
            self.cookie = match.group(1) or None
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = raw.decode("utf-8", "replace")
        return resp.status, resp.headers, payload, set_cookie


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  - ' + detail if detail else ''}")


def request_body(case_input):
    return {
        "title": case_input["video_title"], "description": case_input["video_description"],
        "tags": case_input["video_tags"].split(",") if case_input["video_tags"] else [],
        "channel_title": case_input["channel_title"], "category": case_input["video_category_id"],
        "country": case_input["country"], "duration_sec": case_input["video_duration_sec"],
        "channel_subscriber_count": case_input["channel_subscriber_count"],
        "channel_video_count": case_input["channel_video_count"],
        "channel_view_count": case_input["channel_view_count"],
    }


def run(base):
    anon = Client(base)
    tag = secrets.token_hex(4)
    password = secrets.token_urlsafe(18)

    # --- frontend and routing ------------------------------------------------------------
    status, headers, html, _ = anon.request("GET", "/", cookie=False)
    check("frontend: / serves the SPA", status == 200 and '<div id="root">' in html)
    check("frontend: CSP and nosniff headers", "default-src 'self'" in (headers.get("Content-Security-Policy") or "")
          and headers.get("X-Content-Type-Options") == "nosniff")
    check("frontend: index.html revalidated (no-cache)", headers.get("Cache-Control") == "no-cache")
    asset = re.search(r'src="(/assets/[^"]+\.js)"', html)
    status, headers, _, _ = anon.request("GET", asset.group(1), cookie=False)
    check("frontend: hashed assets cached immutable", status == 200
          and "immutable" in (headers.get("Cache-Control") or ""), asset.group(1))
    status, _, html2, _ = anon.request("GET", "/videos/abc?country=IN", cookie=False)
    check("frontend: SPA fallback for client routes", status == 200 and '<div id="root">' in html2)
    status, _, _, _ = anon.request("GET", "/docs", cookie=False)
    check("API docs not exposed in production", status == 404)

    # --- health ------------------------------------------------------------------------------
    status, _, live, _ = anon.request("GET", "/health/live", cookie=False)
    check("health: live", status == 200 and live == {"status": "ok"})
    status, _, ready, _ = anon.request("GET", "/health/ready", cookie=False)
    check("health: ready (db + read-only role + views)", status == 200 and ready["status"] == "ready"
          and ready["database"]["read_only"] is True and ready["database"]["role"] == "yt_app_ro",
          f"ml={ready.get('ml', {}).get('status')}")

    # --- unauthenticated -----------------------------------------------------------------------
    status, headers, err, _ = anon.request("GET", "/api/v1/overview/kpis", cookie=False)
    check("protected endpoint without session -> 401", status == 401
          and err["error"]["code"] == "not_authenticated")
    check("API responses are no-store", headers.get("Cache-Control") == "no-store")

    # --- register owner (same-origin, cookie) --------------------------------------------------
    owner = Client(base)
    owner_email = f"smoke-{tag}-owner@example.test"
    status, _, data, set_cookie = owner.request("POST", "/api/v1/auth/register", {
        "email": owner_email, "password": password, "display_name": "Smoke Owner",
        "tenant_name": f"Smoke {tag}"})
    flags = [f for f in ("HttpOnly", "Secure", "SameSite=lax", "Path=/api") if f.lower() in set_cookie.lower()]
    check("register creates OWNER and sets session cookie", status == 201 and owner.cookie
          and data["data"]["user"]["role"] == "OWNER" and len(flags) == 4, ", ".join(flags))
    check("session token never in response body", owner.cookie not in json.dumps(data))

    # --- login / analytics / prediction ------------------------------------------------------
    owner.cookie = None
    status, _, data, _ = owner.request("POST", "/api/v1/auth/login", {"email": owner_email, "password": password})
    check("login works", status == 200 and owner.cookie and data["data"]["user"]["email"] == owner_email)
    status, _, me, _ = owner.request("GET", "/api/v1/auth/me")
    check("me returns the identity", status == 200 and me["data"]["tenant"]["name"] == f"Smoke {tag}")
    status, _, meta, _ = owner.request("GET", "/api/v1/meta/filters")
    check("analytics: meta/filters", status == 200 and len(meta["data"]["countries"]) == 9,
          f"range {meta['data']['date_range']}")
    status, _, kpis, _ = owner.request("GET", "/api/v1/overview/kpis")
    check("analytics: overview KPIs", status == 200 and kpis["data"]["unique_videos"]["value"] > 0,
          f"unique_videos={kpis['data']['unique_videos']['value']}")
    status, _, vids, _ = owner.request("GET", "/api/v1/videos?page_size=5")
    check("analytics: video list", status == 200 and len(vids["data"]["items"]) == 5)

    reference = json.loads((REPO / "tests/fixtures/reference_predictions.json").read_text(encoding="utf-8"))
    mismatches = []
    for case in reference["cases"]:
        status, _, pred, _ = owner.request("POST", "/api/v1/predictions", request_body(case["input"]))
        if status != 200:
            mismatches.append(f"{case['name']}: HTTP {status}")
            continue
        got, exp = pred["data"], case["expected"]
        # The fixture was produced on Windows; LaBSE on the container's Linux CPU build differs in
        # the last float digits (text score ~4e-7 measured). The final probability is identical.
        pairs = [(got["high_performance_probability"], exp["high_performance_probability"], 1e-9),
                 (got["components"]["text"], exp["text_score"], 1e-6)]
        if any(abs(a - b) > tol for a, b, tol in pairs):
            mismatches.append(case["name"])
    check(f"predictions equal the reference outputs ({len(reference['cases'])} cases)",
          not mismatches, ", ".join(mismatches[:5]))

    # --- RBAC + tenant isolation ----------------------------------------------------------------
    member_email = f"smoke-{tag}-member@example.test"
    status, _, created, _ = owner.request("POST", "/api/v1/tenant/members", {
        "email": member_email, "display_name": "Smoke Member", "password": password, "role": "MEMBER"})
    check("owner adds a MEMBER", status == 201)
    member = Client(base)
    member.request("POST", "/api/v1/auth/login", {"email": member_email, "password": password})
    status, _, _, _ = member.request("GET", "/api/v1/overview/kpis")
    check("member: analytics allowed", status == 200)
    status, _, err, _ = member.request("GET", "/api/v1/tenant/members")
    check("member: member management forbidden (403)", status == 403 and err["error"]["code"] == "forbidden")

    other = Client(base)
    other.request("POST", "/api/v1/auth/register", {
        "email": f"smoke-{tag}-other@example.test", "password": password, "display_name": "Other Owner"})
    status, _, err, _ = other.request("PATCH", f"/api/v1/tenant/members/{created['data']['id']}", {"is_active": False})
    check("cross-tenant change rejected (404)", status == 404)
    status, _, members, _ = other.request("GET", "/api/v1/tenant/members")
    check("other tenant sees only its own members", status == 200 and len(members["data"]) == 1)

    # --- CSRF + logout ---------------------------------------------------------------------------
    status, _, err, _ = owner.request("POST", "/api/v1/auth/logout", origin="https://evil.example")
    check("cross-origin POST rejected (CSRF)", status == 403 and err["error"]["code"] == "csrf_rejected")
    token = owner.cookie
    status, _, _, set_cookie = owner.request("POST", "/api/v1/auth/logout")
    check("logout clears the cookie", status == 200 and "max-age=0" in set_cookie.lower())
    owner.cookie = token
    status, _, _, _ = owner.request("GET", "/api/v1/auth/me")
    check("old session token rejected after logout (401)", status == 401)

    STATE.write_text(json.dumps({"email": owner_email, "password": password}))
    return owner_email


def persisted_login(base):
    state = json.loads(STATE.read_text())
    client = Client(base)
    status, _, data, _ = client.request("POST", "/api/v1/auth/login", state)
    check("account created before restart can still sign in", status == 200
          and data["data"]["user"]["email"] == state["email"])
    status, _, kpis, _ = client.request("GET", "/api/v1/overview/kpis")
    check("analytics data present after restart", status == 200 and kpis["data"]["unique_videos"]["value"] > 0)
    status, _, pred, _ = client.request("POST", "/api/v1/predictions", request_body(json.loads(
        (REPO / "tests/fixtures/reference_predictions.json").read_text(encoding="utf-8"))["cases"][0]["input"]))
    check("prediction after restart", status == 200)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8080")
    parser.add_argument("--persisted-login", action="store_true")
    args = parser.parse_args()
    persisted_login(args.base) if args.persisted_login else run(args.base)
    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    sys.exit(1 if failed else 0)
