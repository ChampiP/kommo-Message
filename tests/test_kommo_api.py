"""
Tests for kommo_api: one-shot 401/403 recovery on Kommo API and Amojo recipient endpoints,
ensuring non-auth errors and repeated failures are not retried.
"""
import unittest
from unittest.mock import MagicMock, patch
import requests

from app.core.config import DEFAULT_HTTP_TIMEOUT
from app.services.kommo_api import (
    get_crm_account_id,
    get_talk_by_chat_id,
    get_recipient_id,
)


class TestKommoApiRecovery(unittest.TestCase):

    def setUp(self):
        self.mock_session = MagicMock()
        self.mock_auth = MagicMock()
        self.mock_amojo = MagicMock()

    def test_get_crm_account_id_success(self):
        res = MagicMock()
        res.status_code = 200
        res.json.return_value = {"id": 12345}
        self.mock_session.get.return_value = res

        account_id = get_crm_account_id(self.mock_session, auth=self.mock_auth)
        self.assertEqual(account_id, 12345)
        self.mock_auth.recover_session.assert_not_called()

    def test_get_crm_account_id_one_shot_401_recovery(self):
        res_401 = MagicMock()
        res_401.status_code = 401

        res_200 = MagicMock()
        res_200.status_code = 200
        res_200.json.return_value = {"id": 54321}

        new_session = MagicMock()
        new_session.get.return_value = res_200

        self.mock_session.get.return_value = res_401
        self.mock_auth.recover_session.return_value = new_session

        account_id = get_crm_account_id(self.mock_session, auth=self.mock_auth)

        self.assertEqual(account_id, 54321)
        self.mock_auth.recover_session.assert_called_once_with(failed_session=self.mock_session)
        new_session.get.assert_called_once()

    def test_get_crm_account_id_one_shot_403_recovery(self):
        res_403 = MagicMock()
        res_403.status_code = 403

        res_200 = MagicMock()
        res_200.status_code = 200
        res_200.json.return_value = {"id": 999}

        new_session = MagicMock()
        new_session.get.return_value = res_200

        self.mock_session.get.return_value = res_403
        self.mock_auth.recover_session.return_value = new_session

        account_id = get_crm_account_id(self.mock_session, auth=self.mock_auth)
        self.assertEqual(account_id, 999)
        self.mock_auth.recover_session.assert_called_once()

    def test_get_crm_account_id_does_not_retry_twice(self):
        res_401 = MagicMock()
        res_401.status_code = 401
        res_401.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized", response=res_401)

        new_session = MagicMock()
        new_session.get.return_value = res_401

        self.mock_session.get.return_value = res_401
        self.mock_auth.recover_session.return_value = new_session

        with self.assertRaises(requests.HTTPError):
            get_crm_account_id(self.mock_session, auth=self.mock_auth)

        self.assertEqual(self.mock_auth.recover_session.call_count, 1)

    def test_get_crm_account_id_does_not_retry_500(self):
        res_500 = MagicMock()
        res_500.status_code = 500
        res_500.raise_for_status.side_effect = requests.HTTPError("500 Server Error", response=res_500)
        self.mock_session.get.return_value = res_500

        with self.assertRaises(requests.HTTPError):
            get_crm_account_id(self.mock_session, auth=self.mock_auth)

        self.mock_auth.recover_session.assert_not_called()

    def test_get_crm_account_id_does_not_retry_network_error(self):
        self.mock_session.get.side_effect = requests.ConnectionError("Connection refused")

        with self.assertRaises(requests.ConnectionError):
            get_crm_account_id(self.mock_session, auth=self.mock_auth)

        self.mock_auth.recover_session.assert_not_called()

    def test_get_talk_by_chat_id_one_shot_401_recovery(self):
        res_401 = MagicMock()
        res_401.status_code = 401

        res_200 = MagicMock()
        res_200.status_code = 200
        res_200.json.return_value = {
            "_embedded": {
                "talks": [
                    {"id": 11, "contact_id": 22, "chat_id": "target-chat"}
                ]
            }
        }

        new_session = MagicMock()
        new_session.get.return_value = res_200

        self.mock_session.get.return_value = res_401
        self.mock_auth.recover_session.return_value = new_session

        talk = get_talk_by_chat_id(self.mock_session, "target-chat", auth=self.mock_auth)
        self.assertEqual(talk["crm_dialog_id"], 11)
        self.assertEqual(talk["crm_contact_id"], 22)
        self.mock_auth.recover_session.assert_called_once_with(failed_session=self.mock_session)

    def test_get_talk_by_chat_id_does_not_retry_500(self):
        res_500 = MagicMock()
        res_500.status_code = 500
        res_500.raise_for_status.side_effect = requests.HTTPError("500 Internal Error", response=res_500)
        self.mock_session.get.return_value = res_500

        with self.assertRaises(requests.HTTPError):
            get_talk_by_chat_id(self.mock_session, "chat-1", auth=self.mock_auth)

        self.mock_auth.recover_session.assert_not_called()

    @patch("requests.get")
    def test_get_recipient_id_one_shot_401_recovery(self, mock_get):
        res_401 = MagicMock()
        res_401.status_code = 401

        res_200 = MagicMock()
        res_200.status_code = 200
        res_200.json.return_value = [
            {"id": "msg-1", "recipient": {"id": "rec-recovered"}}
        ]

        mock_get.side_effect = [res_401, res_200]
        self.mock_amojo.recover_session.return_value = ("new-token", "new-uuid")

        rid = get_recipient_id("old-token", "old-uuid", "chat-xyz", amojo=self.mock_amojo)

        self.assertEqual(rid, "rec-recovered")
        self.mock_amojo.recover_session.assert_called_once_with(failed_token="old-token")
        self.assertEqual(mock_get.call_count, 2)
        # Check that retry used the new token and uuid
        retry_call_args = mock_get.call_args_list[1]
        self.assertIn("new-uuid", retry_call_args[0][0])
        self.assertEqual(retry_call_args[1]["headers"]["X-Auth-Token"], "new-token")

    @patch("requests.get")
    def test_get_recipient_id_does_not_retry_twice(self, mock_get):
        res_401 = MagicMock()
        res_401.status_code = 401
        res_401.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized", response=res_401)

        mock_get.side_effect = [res_401, res_401]
        mock_amojo = MagicMock(spec=["recover_token", "get_session_account_uuid"])
        mock_amojo.recover_token.return_value = "new-token"
        mock_amojo.get_session_account_uuid.return_value = "new-uuid"

        with self.assertRaises(requests.HTTPError):
            get_recipient_id("old-token", "old-uuid", "chat-xyz", amojo=mock_amojo)

        self.assertEqual(mock_amojo.recover_token.call_count, 1)

    @patch("requests.get")
    def test_get_recipient_id_does_not_retry_500(self, mock_get):
        res_500 = MagicMock()
        res_500.status_code = 500
        res_500.raise_for_status.side_effect = requests.HTTPError("500 Server Error", response=res_500)
        mock_get.return_value = res_500

        with self.assertRaises(requests.HTTPError):
            get_recipient_id("tok", "uuid", "chat-xyz", amojo=self.mock_amojo)

        self.mock_amojo.recover_token.assert_not_called()
        self.mock_amojo.recover_session.assert_not_called()

    def test_get_crm_account_id_propagates_http_timeout(self):
        res = MagicMock()
        res.status_code = 200
        res.json.return_value = {"id": 12345}
        self.mock_session.get.return_value = res

        get_crm_account_id(self.mock_session, auth=self.mock_auth)

        self.mock_session.get.assert_called_once()
        self.assertEqual(self.mock_session.get.call_args[1].get("timeout"), DEFAULT_HTTP_TIMEOUT)

    def test_get_crm_account_id_propagates_http_timeout_on_recovery(self):
        res_401 = MagicMock()
        res_401.status_code = 401
        res_200 = MagicMock()
        res_200.status_code = 200
        res_200.json.return_value = {"id": 54321}

        new_session = MagicMock()
        new_session.get.return_value = res_200

        self.mock_session.get.return_value = res_401
        self.mock_auth.recover_session.return_value = new_session

        get_crm_account_id(self.mock_session, auth=self.mock_auth)

        self.assertEqual(self.mock_session.get.call_args[1].get("timeout"), DEFAULT_HTTP_TIMEOUT)
        self.assertEqual(new_session.get.call_args[1].get("timeout"), DEFAULT_HTTP_TIMEOUT)

    def test_get_talk_by_chat_id_propagates_http_timeout(self):
        res = MagicMock()
        res.status_code = 200
        res.json.return_value = {
            "_embedded": {"talks": [{"id": 1, "contact_id": 2, "chat_id": "c1"}]}
        }
        self.mock_session.get.return_value = res

        get_talk_by_chat_id(self.mock_session, "c1", auth=self.mock_auth)

        self.mock_session.get.assert_called_once()
        self.assertEqual(self.mock_session.get.call_args[1].get("timeout"), DEFAULT_HTTP_TIMEOUT)

    def test_get_talk_by_chat_id_propagates_http_timeout_on_recovery(self):
        res_401 = MagicMock()
        res_401.status_code = 401
        res_200 = MagicMock()
        res_200.status_code = 200
        res_200.json.return_value = {
            "_embedded": {"talks": [{"id": 1, "contact_id": 2, "chat_id": "c1"}]}
        }

        new_session = MagicMock()
        new_session.get.return_value = res_200

        self.mock_session.get.return_value = res_401
        self.mock_auth.recover_session.return_value = new_session

        get_talk_by_chat_id(self.mock_session, "c1", auth=self.mock_auth)

        self.assertEqual(self.mock_session.get.call_args[1].get("timeout"), DEFAULT_HTTP_TIMEOUT)
        self.assertEqual(new_session.get.call_args[1].get("timeout"), DEFAULT_HTTP_TIMEOUT)

    @patch("requests.get")
    def test_get_recipient_id_propagates_http_timeout(self, mock_get):
        res = MagicMock()
        res.status_code = 200
        res.json.return_value = [{"id": "m1", "recipient": {"id": "r1"}}]
        mock_get.return_value = res

        get_recipient_id("tok", "uuid", "c1", amojo=self.mock_amojo)

        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args[1].get("timeout"), DEFAULT_HTTP_TIMEOUT)

    @patch("requests.get")
    def test_get_recipient_id_propagates_http_timeout_on_recovery(self, mock_get):
        res_401 = MagicMock()
        res_401.status_code = 401
        res_200 = MagicMock()
        res_200.status_code = 200
        res_200.json.return_value = [{"id": "m1", "recipient": {"id": "r-rec"}}]

        mock_get.side_effect = [res_401, res_200]
        self.mock_amojo.recover_session.return_value = ("new-tok", "new-uuid")

        get_recipient_id("tok", "uuid", "c1", amojo=self.mock_amojo)

        self.assertEqual(mock_get.call_args_list[0][1].get("timeout"), DEFAULT_HTTP_TIMEOUT)
        self.assertEqual(mock_get.call_args_list[1][1].get("timeout"), DEFAULT_HTTP_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
