"""Pure-ASGI middleware: request id + last-resort error boundary, request body size guard."""

import json
import logging
import re
import uuid

from app.core.errors import error_body

logger = logging.getLogger("app.middleware")

REQUEST_ID_HEADER = b"x-request-id"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


async def _send_json(send, status, body, extra_headers=()):
    payload = json.dumps(body).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode())] + list(extra_headers),
    })
    await send({"type": "http.response.body", "body": payload})


class RequestIdMiddleware:
    """Assigns a request id (a valid incoming X-Request-ID is reused), returns it in the
    X-Request-ID response header, and turns any unhandled exception into a generic
    500 error envelope (no stack trace in the response; full trace in the log)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        incoming = dict(scope.get("headers") or []).get(REQUEST_ID_HEADER, b"").decode("latin-1")
        request_id = incoming if _VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        header = (REQUEST_ID_HEADER, request_id.encode())
        started = False

        async def send_with_id(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = [h for h in message.get("headers", []) if h[0].lower() != REQUEST_ID_HEADER]
                message = {**message, "headers": headers + [header]}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            logger.exception("unhandled error [request_id=%s]", request_id)
            if started:
                raise
            await _send_json(send, 500,
                             error_body("internal_error", "An unexpected error occurred.", request_id),
                             [header])


class OriginCheckMiddleware:
    """CSRF defence for cookie-authenticated requests (in addition to SameSite=Lax cookies).

    A state-changing request (POST/PUT/PATCH/DELETE) that carries an Origin header is
    rejected with 403 unless the origin is in the CORS allowlist or is the API's own origin
    (Swagger UI). Browsers always send Origin on cross-origin fetches and form posts, so a
    page on another site cannot drive the API with the victim's cookie. Requests without
    Origin (curl, server-to-server) carry no ambient browser cookie and pass through.
    """

    UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, app, allowed_origins):
        self.app = app
        self.allowed = {o.rstrip("/").lower() for o in allowed_origins}

    def _allowed(self, origin: str, host: str) -> bool:
        origin = origin.rstrip("/").lower()
        if origin in self.allowed:
            return True
        scheme, _, netloc = origin.partition("://")
        return scheme in ("http", "https") and bool(host) and netloc == host.lower()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in self.UNSAFE_METHODS:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        origin = headers.get(b"origin")
        if origin is not None and not self._allowed(origin.decode("latin-1"),
                                                    headers.get(b"host", b"").decode("latin-1")):
            rid = scope.get("state", {}).get("request_id")
            logger.warning("rejected cross-origin %s %s [request_id=%s]", scope.get("method"),
                           scope.get("path"), rid)
            return await _send_json(send, 403, error_body(
                "csrf_rejected", "Cross-origin request rejected.", rid))
        await self.app(scope, receive, send)


class BodySizeLimitMiddleware:
    """Rejects request bodies larger than `max_bytes` with 413. Uses Content-Length when
    present; otherwise (chunked uploads) reads the body up to the limit before the app
    sees it and replays it. Bodies are small (64 KB limit), so buffering is cheap."""

    BODY_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def _reject(self, scope, send):
        rid = scope.get("state", {}).get("request_id")
        await _send_json(send, 413, error_body(
            "payload_too_large", f"Request body exceeds {self.max_bytes} bytes.", rid))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in self.BODY_METHODS:
            return await self.app(scope, receive, send)

        length = dict(scope.get("headers") or []).get(b"content-length")
        if length is not None:
            try:
                too_large = int(length) > self.max_bytes
            except ValueError:
                too_large = True
            if too_large:
                return await self._reject(scope, send)

        chunks, total = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            total += len(body)
            if total > self.max_bytes:
                return await self._reject(scope, send)
            chunks.append(body)
            if not message.get("more_body", False):
                break

        body, replayed = b"".join(chunks), False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
