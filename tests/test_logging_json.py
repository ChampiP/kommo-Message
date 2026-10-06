"""
Tests for the JSON log formatter and the request-context middleware.
"""
import asyncio
import json
import logging
import sys
import unittest

from fastapi import FastAPI

from app.logging_config import JsonFormatter, request_id_var
from app.middleware import RequestContextMiddleware


def make_record(msg="hello", exc_info=None, extra=None, level=logging.INFO):
    return logging.makeLogRecord(
        {
            "name": "test.logger",
            "levelno": level,
            "levelname": logging.getLevelName(level),
            "msg": msg,
            "args": (),
            "exc_info": exc_info,
            "pathname": __file__,
            "filename": "test_logging_json.py",
            "lineno": 1,
            "funcName": "make_record",
            **(extra or {}),
        }
    )


def fmt(record):
    out = JsonFormatter().format(record)
    assert "\n" not in out
    return json.loads(out)


class TestJsonFormatter(unittest.TestCase):
    def test_core_keys(self):
        data = fmt(make_record())
        for key in (
            "@timestamp", "log.level", "log.logger", "message", "service.name",
            "process.pid", "process.thread.name", "log.origin.file.name",
            "log.origin.file.line", "log.origin.function",
        ):
            self.assertIn(key, data)
        self.assertEqual(data["message"], "hello")
        self.assertEqual(data["log.level"], "INFO")
        self.assertTrue(data["@timestamp"].endswith("Z"))

    def test_redacts_message_and_extra(self):
        data = fmt(
            make_record(
                msg="login access_token=abc123",
                extra={"access_token": "abc", "detail": {"password": "p"}},
            )
        )
        self.assertNotIn("abc123", data["message"])
        self.assertEqual(data["access_token"], "[REDACTED]")
        self.assertEqual(data["detail"]["password"], "[REDACTED]")

    def test_extra_does_not_overwrite_core(self):
        data = fmt(make_record(extra={"service.name": "evil"}))
        self.assertNotEqual(data["service.name"], "evil")

    def test_exc_info(self):
        try:
            raise ValueError("boom password=hunter2")
        except ValueError:
            data = fmt(make_record(exc_info=sys.exc_info(), level=logging.ERROR))
        self.assertEqual(data["error.type"], "ValueError")
        self.assertIn("boom", data["error.message"])
        self.assertNotIn("hunter2", data["error.message"])
        self.assertIn("Traceback", data["error.stack_trace"])
        self.assertNotIn("hunter2", data["error.stack_trace"])

    def test_request_id(self):
        self.assertNotIn("http.request.id", fmt(make_record()))
        token = request_id_var.set("rid-1")
        try:
            self.assertEqual(fmt(make_record())["http.request.id"], "rid-1")
        finally:
            request_id_var.reset(token)


def build_client():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ok")
    def ok():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    return app


class Response:
    def __init__(self, status_code, headers):
        self.status_code = status_code
        self.headers = headers


class Client:
    """Minimal ASGI caller (fastapi's TestClient needs httpx2, which is not installed)."""

    def __init__(self, app):
        self.app = app

    def get(self, url, headers=None):
        path, _, query = url.partition("?")
        raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
            "query_string": query.encode(), "headers": raw,
            "client": ("127.0.0.1", 5000), "server": ("testserver", 80),
        }
        sent = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        async def call():
            try:
                await self.app(scope, receive, send)
            except Exception:
                sent.append({"type": "http.response.start", "status": 500, "headers": []})

        asyncio.run(call())
        start = next(m for m in sent if m["type"] == "http.response.start")
        hdrs = {k.decode().lower(): v.decode() for k, v in start["headers"]}
        return Response(start["status"], hdrs)


class TestRequestContextMiddleware(unittest.TestCase):
    def setUp(self):
        self.client = Client(build_client())

    def test_generates_request_id(self):
        r = self.client.get("/ok")
        self.assertRegex(r.headers["x-request-id"], r"^[0-9a-f]{32}$")

    def test_echoes_valid_id(self):
        r = self.client.get("/ok", headers={"X-Request-ID": "abc-123._X"})
        self.assertEqual(r.headers["x-request-id"], "abc-123._X")

    def test_replaces_invalid_id(self):
        for bad in ("has space", "a" * 129):
            r = self.client.get("/ok", headers={"X-Request-ID": bad})
            self.assertNotEqual(r.headers["x-request-id"], bad)

    def test_access_record(self):
        with self.assertLogs("app.access", level="INFO") as cm:
            self.client.get("/ok?token=secret", headers={"X-Request-ID": "rid-9"})
        rec = cm.records[0]
        self.assertEqual(rec.getMessage(), "GET /ok 200")
        self.assertEqual(rec.__dict__["event.action"], "http.request")
        self.assertEqual(rec.__dict__["http.request.method"], "GET")
        self.assertEqual(rec.__dict__["url.path"], "/ok")
        self.assertEqual(rec.__dict__["http.response.status_code"], 200)
        self.assertEqual(rec.__dict__["event.outcome"], "success")
        self.assertIsInstance(rec.__dict__["event.duration_ms"], float)
        self.assertIn("client.ip", rec.__dict__)
        # request id is visible to the formatter while the record is emitted
        self.assertNotIn("secret", JsonFormatter().format(rec))

    def test_health_not_logged(self):
        with self.assertNoLogs("app.access", level="INFO"):
            r = self.client.get("/health")
        self.assertIn("x-request-id", r.headers)

    def test_unhandled_exception_logged(self):
        with self.assertLogs("app.access", level="ERROR") as cm:
            r = self.client.get("/boom")
        self.assertEqual(r.status_code, 500)
        rec = cm.records[0]
        self.assertEqual(rec.levelno, logging.ERROR)
        self.assertEqual(rec.__dict__["http.response.status_code"], 500)
        self.assertEqual(rec.__dict__["event.outcome"], "failure")
        self.assertIsNotNone(rec.exc_info)

    def test_request_id_in_log_line(self):
        captured = []

        class H(logging.Handler):
            def emit(self, record):
                captured.append(JsonFormatter().format(record))

        lg = logging.getLogger("app.access")
        h = H()
        lg.addHandler(h)
        try:
            self.client.get("/ok", headers={"X-Request-ID": "rid-7"})
        finally:
            lg.removeHandler(h)
        self.assertEqual(json.loads(captured[0])["http.request.id"], "rid-7")


if __name__ == "__main__":
    unittest.main()
