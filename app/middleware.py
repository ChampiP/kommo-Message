"""Pure ASGI middleware: request id correlation and one access log per request."""
import logging
import re
import time
import uuid

from app.logging_config import get_logger, request_id_var

logger = get_logger("app.access")

_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_SKIP_PATHS = {"/health"}


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        request_id = inbound if _VALID_ID.match(inbound) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        status = 500
        start = time.perf_counter()

        async def send_wrapper(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", []).append(
                    (b"x-request-id", request_id.encode())
                )
            await send(message)

        path = scope["path"]
        method = scope["method"]
        client = scope.get("client")

        def log(level, **kw):
            logger.log(
                level,
                f"{method} {path} {status}",
                extra={
                    "event.action": "http.request",
                    "http.request.method": method,
                    "url.path": path,
                    "http.response.status_code": status,
                    "event.duration_ms": round((time.perf_counter() - start) * 1000, 2),
                    "client.ip": client[0] if client else None,
                    "event.outcome": "success" if status < 500 else "failure",
                },
                stacklevel=2,
                **kw,
            )

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            status = 500
            log(logging.ERROR, exc_info=True)
            raise
        else:
            if path not in _SKIP_PATHS:
                log(logging.INFO)
        finally:
            request_id_var.reset(token)
