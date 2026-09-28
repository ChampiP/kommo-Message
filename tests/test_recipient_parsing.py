"""
Tests for recipient parsing and extraction from Amojo messages.
"""
import unittest
from unittest.mock import patch, MagicMock

from app.services.kommo_api import get_recipient_id, _extract_messages


class TestRecipientParsing(unittest.TestCase):

    def test_extract_messages_shapes(self):
        msg = {"id": "1", "text": "hello"}

        # Direct list
        self.assertEqual(_extract_messages([msg]), [msg])

        # Dict with messages
        self.assertEqual(_extract_messages({"messages": [msg]}), [msg])

        # Dict with items
        self.assertEqual(_extract_messages({"items": [msg]}), [msg])

        # Dict with _embedded
        self.assertEqual(_extract_messages({"_embedded": {"messages": [msg]}}), [msg])
        self.assertEqual(_extract_messages({"_embedded": {"items": [msg]}}), [msg])

        # Dict with response
        self.assertEqual(_extract_messages({"response": {"messages": [msg]}}), [msg])

        # Empty / invalid
        self.assertEqual(_extract_messages({}), [])
        self.assertEqual(_extract_messages(None), [])
        self.assertEqual(_extract_messages("string"), [])

    @patch("requests.get")
    def test_get_recipient_id_recipient_object(self, mock_get):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = [
            {
                "id": "msg-1",
                "recipient": {"id": "rec-12345", "name": "Client"},
            }
        ]
        mock_get.return_value = mock_res

        rid = get_recipient_id("mock_token", "mock_uuid", "chat-001")
        self.assertEqual(rid, "rec-12345")

    @patch("requests.get")
    def test_get_recipient_id_uuid_field(self, mock_get):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = [
            {
                "id": "msg-1",
                "recipient": {"uuid": "rec-uuid-67890"},
            }
        ]
        mock_get.return_value = mock_res

        rid = get_recipient_id("mock_token", "mock_uuid", "chat-001")
        self.assertEqual(rid, "rec-uuid-67890")

    @patch("requests.get")
    def test_get_recipient_id_scalar_string(self, mock_get):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = [
            {
                "id": "msg-1",
                "recipient": "rec-scalar-111",
            }
        ]
        mock_get.return_value = mock_res

        rid = get_recipient_id("mock_token", "mock_uuid", "chat-001")
        self.assertEqual(rid, "rec-scalar-111")

    @patch("requests.get")
    def test_get_recipient_id_direct_field(self, mock_get):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = [
            {
                "id": "msg-1",
                "recipient_id": "rec-direct-222",
            }
        ]
        mock_get.return_value = mock_res

        rid = get_recipient_id("mock_token", "mock_uuid", "chat-001")
        self.assertEqual(rid, "rec-direct-222")

    @patch("requests.get")
    def test_get_recipient_id_receiver_object(self, mock_get):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = [
            {
                "id": "msg-1",
                "receiver": {"id": "rec-receiver-333"},
            }
        ]
        mock_get.return_value = mock_res

        rid = get_recipient_id("mock_token", "mock_uuid", "chat-001")
        self.assertEqual(rid, "rec-receiver-333")

    @patch("requests.get")
    def test_get_recipient_id_no_recipient_returns_none(self, mock_get):
        # Reproduces the real Kommo Amojo payload where author is set but recipient is None
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = [
            {
                "id": "msg-1",
                "author": {"id": "author-uuid-1", "name": "ChampIP"},
                "recipient": None,
            },
            {
                "id": "msg-2",
                "author": {"id": "author-uuid-1", "name": "ChampIP"},
                "recipient": None,
            },
        ]
        mock_get.return_value = mock_res

        rid = get_recipient_id("mock_token", "mock_uuid", "chat-no-recipient")
        self.assertIsNone(rid)

    @patch("requests.get")
    def test_get_recipient_id_empty_messages(self, mock_get):
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = []
        mock_get.return_value = mock_res

        rid = get_recipient_id("mock_token", "mock_uuid", "chat-empty")
        self.assertIsNone(rid)


if __name__ == "__main__":
    unittest.main()
