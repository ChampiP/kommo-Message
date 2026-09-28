"""
Tests for credential and token redaction in logs.
"""
import logging
import unittest
from app.logging_config import (
    redact_text,
    redact_data,
    SensitiveDataFilter,
    RedactingFormatter,
)


class TestRedaction(unittest.TestCase):

    def test_redact_sensitive_text_patterns(self):
        # Key-value / JSON style
        raw = 'csrf_token="def50200secret123" and access_token: "jwt.token.here"'
        redacted = redact_text(raw)
        self.assertNotIn("def50200secret123", redacted)
        self.assertNotIn("jwt.token.here", redacted)
        self.assertIn("[REDACTED]", redacted)

        # x_auth_token and refresh_token
        raw2 = "x_auth_token=abc-123-uuid refresh_token=secret_refresh_val"
        redacted2 = redact_text(raw2)
        self.assertNotIn("abc-123-uuid", redacted2)
        self.assertNotIn("secret_refresh_val", redacted2)

        # Bearer token
        raw3 = "Authorization: Bearer secret_bearer_token_xyz"
        redacted3 = redact_text(raw3)
        self.assertNotIn("secret_bearer_token_xyz", redacted3)
        self.assertIn("Bearer [REDACTED]", redacted3)

        # Cookies string
        raw4 = "session_id=sess12345; csrf_token=csrf999; other=ok"
        redacted4 = redact_text(raw4)
        self.assertNotIn("sess12345", redacted4)
        self.assertNotIn("csrf999", redacted4)
        self.assertIn("other=ok", redacted4)

    def test_redact_nested_dict(self):
        payload = {
            "chat_id": "6029a3cb-0bdf-41b7-87fa-1433241a34c9",
            "csrf_token": "secret_csrf",
            "access_token": "secret_access",
            "refresh_token": "secret_refresh",
            "x_auth_token": "secret_xauth",
            "password": "my_password",
            "nested": {
                "session_id": "sess_secret",
                "safe_field": 12345,
            },
            "token_list": [
                {"token": "secret_item", "status": "active"}
            ],
        }

        redacted = redact_data(payload)

        self.assertEqual(redacted["chat_id"], "6029a3cb-0bdf-41b7-87fa-1433241a34c9")
        self.assertEqual(redacted["csrf_token"], "[REDACTED]")
        self.assertEqual(redacted["access_token"], "[REDACTED]")
        self.assertEqual(redacted["refresh_token"], "[REDACTED]")
        self.assertEqual(redacted["x_auth_token"], "[REDACTED]")
        self.assertEqual(redacted["password"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["session_id"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["safe_field"], 12345)

    def test_redacting_formatter(self):
        formatter = RedactingFormatter("%(asctime)s [%(levelname)s] %(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="User login with csrf_token=%s and password=%s",
            args=("def50200_secret_token", "super_secret_pass"),
            exc_info=None,
        )

        formatted = formatter.format(record)
        self.assertNotIn("def50200_secret_token", formatted)
        self.assertNotIn("super_secret_pass", formatted)
        self.assertIn("[REDACTED]", formatted)

    def test_sensitive_data_filter_dict_args(self):
        filter_ = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Session data: %(csrf_token)s",
            args=({"csrf_token": "secret123", "chat_id": "c1"},),
            exc_info=None,
        )

        filter_.filter(record)
        self.assertEqual(record.args["csrf_token"], "[REDACTED]")
        self.assertEqual(record.args["chat_id"], "c1")


if __name__ == "__main__":
    unittest.main()
