"""
Tests for the chat tokens route behavior and HTTP status codes.
"""
import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from app.api.routes.chats import get_chat_tokens
from app.services.auth import AuthError
from app.services.amojo import AmojoError


class TestChatsRoute(unittest.TestCase):

    def setUp(self):
        self.mock_auth = MagicMock()
        self.mock_session = MagicMock()
        self.mock_auth.get_session.return_value = self.mock_session

        self.mock_amojo = MagicMock()
        self.mock_amojo.get_credentials.return_value = (
            "mock_x_auth_token",
            "mock_account_uuid",
        )

    @patch("app.services.kommo_api.get_recipient_id")
    @patch("app.services.kommo_api.get_talk_by_chat_id")
    @patch("app.services.kommo_api.get_crm_account_id")
    def test_get_chat_tokens_success(self, mock_account, mock_talk, mock_recipient):
        mock_account.return_value = 123456
        mock_talk.return_value = {"crm_dialog_id": 111, "crm_contact_id": 222}
        mock_recipient.return_value = "rec-success-123"

        result = get_chat_tokens(
            chat_id="test-chat-id",
            auth=self.mock_auth,
            amojo=self.mock_amojo,
        )

        self.assertEqual(result["recipient_id"], "rec-success-123")
        self.assertEqual(result["crm_dialog_id"], 111)
        self.assertEqual(result["crm_contact_id"], 222)
        self.assertEqual(result["crm_account_id"], 123456)
        self.assertEqual(result["x_auth_token"], "mock_x_auth_token")
        self.assertEqual(result["session_account_uuid"], "mock_account_uuid")
        self.assertEqual(self.mock_amojo.get_credentials.call_count, 2)

    @patch("app.services.kommo_api.get_recipient_id")
    @patch("app.services.kommo_api.get_talk_by_chat_id")
    @patch("app.services.kommo_api.get_crm_account_id")
    def test_get_chat_tokens_no_recipient_returns_payload_with_none(
        self, mock_account, mock_talk, mock_recipient
    ):
        mock_account.return_value = 123456
        mock_talk.return_value = {"crm_dialog_id": 111, "crm_contact_id": 222}
        mock_recipient.return_value = None

        with self.assertLogs("app.api.routes.chats", level="WARNING") as log_ctx:
            result = get_chat_tokens(
                chat_id="test-chat-no-recipient",
                auth=self.mock_auth,
                amojo=self.mock_amojo,
            )

        self.assertIsNone(result["recipient_id"])
        self.assertEqual(result["crm_dialog_id"], 111)
        self.assertEqual(result["crm_contact_id"], 222)
        self.assertEqual(result["crm_account_id"], 123456)
        self.assertEqual(result["x_auth_token"], "mock_x_auth_token")
        self.assertEqual(result["session_account_uuid"], "mock_account_uuid")
        self.assertTrue(
            any("Recipient metadata unavailable for chat_id=test-chat-no-recipient" in msg for msg in log_ctx.output)
        )

    @patch("app.services.kommo_api.get_talk_by_chat_id")
    @patch("app.services.kommo_api.get_crm_account_id")
    def test_get_chat_tokens_talk_not_found_returns_404(
        self, mock_account, mock_talk
    ):
        mock_account.return_value = 123456
        mock_talk.side_effect = ValueError("chat_id test-chat not found in inbox")

        with self.assertRaises(HTTPException) as ctx:
            get_chat_tokens(
                chat_id="test-chat",
                auth=self.mock_auth,
                amojo=self.mock_amojo,
            )

        self.assertEqual(ctx.exception.status_code, 404)

    @patch("app.services.kommo_api.get_recipient_id")
    @patch("app.services.kommo_api.get_talk_by_chat_id")
    @patch("app.services.kommo_api.get_crm_account_id")
    def test_get_chat_tokens_upstream_error_returns_502(
        self, mock_account, mock_talk, mock_recipient
    ):
        mock_account.return_value = 123456
        mock_talk.return_value = {"crm_dialog_id": 111, "crm_contact_id": 222}
        mock_recipient.side_effect = RuntimeError("Upstream connection reset")

        with self.assertRaises(HTTPException) as ctx:
            get_chat_tokens(
                chat_id="test-chat",
                auth=self.mock_auth,
                amojo=self.mock_amojo,
            )

        self.assertEqual(ctx.exception.status_code, 502)

    def test_get_chat_tokens_auth_unavailable_returns_503(self):
        self.mock_auth.get_session.side_effect = AuthError("Cannot reach Kommo")

        with self.assertRaises(HTTPException) as ctx:
            get_chat_tokens(
                chat_id="test-chat",
                auth=self.mock_auth,
                amojo=self.mock_amojo,
            )

        self.assertEqual(ctx.exception.status_code, 503)

    def test_get_chat_tokens_amojo_unavailable_returns_503(self):
        self.mock_amojo.get_credentials.side_effect = AmojoError("Amojo timeout")

        with self.assertRaises(HTTPException) as ctx:
            get_chat_tokens(
                chat_id="test-chat",
                auth=self.mock_auth,
                amojo=self.mock_amojo,
            )

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("Sesión Amojo no disponible", ctx.exception.detail)

    def test_get_chat_tokens_initial_amojo_autherror_returns_503(self):
        self.mock_amojo.get_credentials.side_effect = AuthError("Kommo relogin failed during token fetch")

        with self.assertRaises(HTTPException) as ctx:
            get_chat_tokens(
                chat_id="test-chat",
                auth=self.mock_auth,
                amojo=self.mock_amojo,
            )

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("Sesión Amojo no disponible", ctx.exception.detail)

    @patch("app.services.kommo_api.get_recipient_id")
    @patch("app.services.kommo_api.get_talk_by_chat_id")
    @patch("app.services.kommo_api.get_crm_account_id")
    def test_get_chat_tokens_final_amojo_autherror_returns_503(
        self, mock_account, mock_talk, mock_recipient
    ):
        mock_account.return_value = 123456
        mock_talk.return_value = {"crm_dialog_id": 111, "crm_contact_id": 222}
        mock_recipient.return_value = "rec-123"

        # Initial call returns credentials, final call raises AuthError
        self.mock_amojo.get_credentials.side_effect = [
            ("tok-1", "uuid-1"),
            AuthError("Kommo auth failed on final token read"),
        ]

        with self.assertRaises(HTTPException) as ctx:
            get_chat_tokens(
                chat_id="test-chat",
                auth=self.mock_auth,
                amojo=self.mock_amojo,
            )

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("Sesión Amojo no disponible", ctx.exception.detail)

    @patch("app.services.kommo_api.get_recipient_id")
    @patch("app.services.kommo_api.get_talk_by_chat_id")
    @patch("app.services.kommo_api.get_crm_account_id")
    def test_get_chat_tokens_final_amojo_amojoerror_returns_503(
        self, mock_account, mock_talk, mock_recipient
    ):
        mock_account.return_value = 123456
        mock_talk.return_value = {"crm_dialog_id": 111, "crm_contact_id": 222}
        mock_recipient.return_value = "rec-123"

        # Initial call returns credentials, final call raises AmojoError
        self.mock_amojo.get_credentials.side_effect = [
            ("tok-1", "uuid-1"),
            AmojoError("Amojo service failed on final read"),
        ]

        with self.assertRaises(HTTPException) as ctx:
            get_chat_tokens(
                chat_id="test-chat",
                auth=self.mock_auth,
                amojo=self.mock_amojo,
            )

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("Sesión Amojo no disponible", ctx.exception.detail)

    @patch("app.services.kommo_api.get_recipient_id")
    @patch("app.services.kommo_api.get_talk_by_chat_id")
    @patch("app.services.kommo_api.get_crm_account_id")
    def test_get_chat_tokens_passes_recovery_handlers_to_api_layer(
        self, mock_account, mock_talk, mock_recipient
    ):
        mock_account.return_value = 123456
        mock_talk.return_value = {"crm_dialog_id": 111, "crm_contact_id": 222}
        mock_recipient.return_value = "rec-123"

        get_chat_tokens(
            chat_id="test-chat",
            auth=self.mock_auth,
            amojo=self.mock_amojo,
        )

        mock_account.assert_called_once_with(self.mock_session, auth=self.mock_auth)
        mock_talk.assert_called_once_with(self.mock_session, "test-chat", auth=self.mock_auth)
        mock_recipient.assert_called_once_with(
            "mock_x_auth_token", "mock_account_uuid", "test-chat", amojo=self.mock_amojo
        )
        self.assertEqual(self.mock_amojo.get_credentials.call_count, 2)

    @patch("app.services.kommo_api.get_recipient_id")
    @patch("app.services.kommo_api.get_talk_by_chat_id")
    @patch("app.services.kommo_api.get_crm_account_id")
    def test_get_chat_tokens_returns_latest_amojo_token_after_recovery(
        self, mock_account, mock_talk, mock_recipient
    ):
        mock_account.return_value = 123456
        mock_talk.return_value = {"crm_dialog_id": 111, "crm_contact_id": 222}
        mock_recipient.return_value = "rec-123"

        # Simulate token recovery where get_credentials returns initial then refreshed credentials
        self.mock_amojo.get_credentials.side_effect = [
            ("old_token", "old_uuid"),
            ("recovered_token", "recovered_uuid"),
        ]

        result = get_chat_tokens(
            chat_id="test-chat",
            auth=self.mock_auth,
            amojo=self.mock_amojo,
        )

        mock_recipient.assert_called_once_with(
            "old_token", "old_uuid", "test-chat", amojo=self.mock_amojo
        )
        self.assertEqual(result["x_auth_token"], "recovered_token")
        self.assertEqual(result["session_account_uuid"], "recovered_uuid")
        self.assertEqual(self.mock_amojo.get_credentials.call_count, 2)


if __name__ == "__main__":
    unittest.main()
