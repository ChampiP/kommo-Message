"""
Tests for AmojoSession: in-memory token/UUID caching, on-demand refresh,
single-flight recovery, and 401/403 Kommo session coordination.
"""
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
import requests

from app.core.config import DEFAULT_HTTP_TIMEOUT
from app.services.amojo import AmojoSession, AmojoError


class TestAmojoSession(unittest.TestCase):

    def setUp(self):
        self.mock_session = MagicMock()
        self.mock_session_provider = MagicMock(return_value=self.mock_session)
        self.mock_auth_recovery = MagicMock()
        self.amojo = AmojoSession(
            session_provider=self.mock_session_provider,
            auth_recovery=self.mock_auth_recovery,
        )

    def _mock_success_response(self, token="test-token-123", account_id="acc-456"):
        res = MagicMock()
        res.status_code = 200
        res.json.return_value = {
            "response": {
                "chats": {
                    "session": {
                        "access_token": token,
                        "account": {"id": account_id},
                        "expired_at": 1750000000,
                    }
                }
            }
        }
        return res

    def test_background_refresh_not_running_by_default(self):
        self.assertIsNone(self.amojo._x_auth_token)
        self.assertIsNone(self.amojo._session_account_uuid)
        self.assertIsNone(self.amojo._refresh_thread)
        self.assertFalse(self.amojo._stop)

    def test_get_x_auth_token_lazy_fetch_and_caching(self):
        self.mock_session.post.return_value = self._mock_success_response("tok-1", "acc-1")

        # First call: fetches from /ajax/v1/chats/session
        tok1 = self.amojo.get_x_auth_token()
        self.assertEqual(tok1, "tok-1")
        self.assertEqual(self.mock_session.post.call_count, 1)

        # Second call: cached in memory, no HTTP call
        tok2 = self.amojo.get_x_auth_token()
        self.assertEqual(tok2, "tok-1")
        self.assertEqual(self.mock_session.post.call_count, 1)

        # Account UUID also populated
        uuid = self.amojo.get_session_account_uuid()
        self.assertEqual(uuid, "acc-1")
        self.assertEqual(self.mock_session.post.call_count, 1)

    def test_invalidate_clears_cache_and_forces_refresh(self):
        self.mock_session.post.side_effect = [
            self._mock_success_response("tok-1", "acc-1"),
            self._mock_success_response("tok-2", "acc-2"),
        ]

        tok1 = self.amojo.get_x_auth_token()
        self.assertEqual(tok1, "tok-1")

        self.amojo.invalidate()
        self.assertIsNone(self.amojo._x_auth_token)
        self.assertIsNone(self.amojo._session_account_uuid)

        tok2 = self.amojo.get_x_auth_token()
        self.assertEqual(tok2, "tok-2")
        self.assertEqual(self.mock_session.post.call_count, 2)

    def test_recover_token_refreshes_when_matching_failed_token(self):
        self.mock_session.post.side_effect = [
            self._mock_success_response("tok-1", "acc-1"),
            self._mock_success_response("tok-2", "acc-2"),
        ]

        initial = self.amojo.get_x_auth_token()
        self.assertEqual(initial, "tok-1")

        recovered = self.amojo.recover_token(failed_token="tok-1")
        self.assertEqual(recovered, "tok-2")
        self.assertEqual(self.amojo.get_x_auth_token(), "tok-2")
        self.assertEqual(self.amojo.get_session_account_uuid(), "acc-2")

    def test_recover_token_ignores_stale_failed_token(self):
        self.mock_session.post.side_effect = [
            self._mock_success_response("tok-1", "acc-1"),
            self._mock_success_response("tok-2", "acc-2"),
        ]

        self.amojo.get_x_auth_token()  # tok-1
        self.amojo.recover_token(failed_token="tok-1")  # updates to tok-2

        # Stale recovery call from another thread
        recovered = self.amojo.recover_token(failed_token="tok-1")
        self.assertEqual(recovered, "tok-2")
        self.assertEqual(self.mock_session.post.call_count, 2)

    def test_recover_token_single_flight_concurrent(self):
        self.mock_session.post.return_value = self._mock_success_response("tok-1", "acc-1")
        self.amojo.get_x_auth_token()  # initial token
        self.assertEqual(self.mock_session.post.call_count, 1)

        refresh_count = 0

        def slow_post(*args, **kwargs):
            nonlocal refresh_count
            refresh_count += 1
            time.sleep(0.05)
            return self._mock_success_response("tok-2", "acc-2")

        self.mock_session.post.side_effect = slow_post

        threads = []
        results = [None] * 10

        def worker(index):
            results[index] = self.amojo.recover_token(failed_token="tok-1")

        for i in range(10):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(refresh_count, 1)
        for res in results:
            self.assertEqual(res, "tok-2")
        self.assertEqual(self.amojo.get_x_auth_token(), "tok-2")

    def test_amojo_recovers_kommo_session_on_401(self):
        res_401 = MagicMock()
        res_401.status_code = 401

        res_200 = self._mock_success_response("tok-fresh", "acc-fresh")

        new_session = MagicMock()
        new_session.post.return_value = res_200

        self.mock_session.post.return_value = res_401
        self.mock_auth_recovery.return_value = new_session

        token = self.amojo.get_x_auth_token()

        self.mock_auth_recovery.assert_called_once_with(self.mock_session)
        new_session.post.assert_called_once()
        self.assertEqual(token, "tok-fresh")

    def test_amojo_does_not_retry_500(self):
        res_500 = MagicMock()
        res_500.status_code = 500
        self.mock_session.post.return_value = res_500

        with self.assertRaises(AmojoError):
            self.amojo.get_x_auth_token()

        self.mock_auth_recovery.assert_not_called()

    def test_get_credentials_atomic_fetch_and_caching(self):
        self.mock_session.post.return_value = self._mock_success_response("tok-atomic", "acc-atomic")

        # First call: fetches via chats/session
        tok, uuid = self.amojo.get_credentials()
        self.assertEqual(tok, "tok-atomic")
        self.assertEqual(uuid, "acc-atomic")
        self.assertEqual(self.mock_session.post.call_count, 1)

        # Second call: returns cached values without calling post again
        tok2, uuid2 = self.amojo.get_credentials()
        self.assertEqual(tok2, "tok-atomic")
        self.assertEqual(uuid2, "acc-atomic")
        self.assertEqual(self.mock_session.post.call_count, 1)

        # get_x_auth_token and get_session_account_uuid match
        self.assertEqual(self.amojo.get_x_auth_token(), "tok-atomic")
        self.assertEqual(self.amojo.get_session_account_uuid(), "acc-atomic")
        self.assertEqual(self.mock_session.post.call_count, 1)

    def test_recover_session_returns_consistent_pair_single_flight_concurrent(self):
        self.mock_session.post.return_value = self._mock_success_response("tok-1", "acc-1")
        self.amojo.get_credentials()
        self.assertEqual(self.mock_session.post.call_count, 1)

        refresh_count = 0

        def slow_post(*args, **kwargs):
            nonlocal refresh_count
            refresh_count += 1
            time.sleep(0.05)
            return self._mock_success_response("tok-2", "acc-2")

        self.mock_session.post.side_effect = slow_post

        threads = []
        results = [None] * 10

        def worker(index):
            results[index] = self.amojo.recover_session(failed_token="tok-1")

        for i in range(10):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(refresh_count, 1)
        for res in results:
            self.assertEqual(res, ("tok-2", "acc-2"))
        self.assertEqual(self.amojo.get_credentials(), ("tok-2", "acc-2"))

    def test_recover_session_ignores_stale_token(self):
        self.mock_session.post.side_effect = [
            self._mock_success_response("tok-1", "acc-1"),
            self._mock_success_response("tok-2", "acc-2"),
        ]

        self.amojo.get_credentials()
        self.amojo.recover_session(failed_token="tok-1")

        # Stale recovery call
        recovered = self.amojo.recover_session(failed_token="tok-1")
        self.assertEqual(recovered, ("tok-2", "acc-2"))
        self.assertEqual(self.mock_session.post.call_count, 2)

    def test_amojo_propagates_http_timeout(self):
        self.mock_session.post.return_value = self._mock_success_response("tok-t", "acc-t")
        self.amojo.get_credentials()

        self.mock_session.post.assert_called_once()
        self.assertEqual(self.mock_session.post.call_args[1].get("timeout"), DEFAULT_HTTP_TIMEOUT)

    def test_amojo_propagates_http_timeout_on_recovery(self):
        res_401 = MagicMock()
        res_401.status_code = 401
        res_200 = self._mock_success_response("tok-fresh", "acc-fresh")

        new_session = MagicMock()
        new_session.post.return_value = res_200

        self.mock_session.post.return_value = res_401
        self.mock_auth_recovery.return_value = new_session

        self.amojo.get_credentials()

        self.assertEqual(self.mock_session.post.call_args[1].get("timeout"), DEFAULT_HTTP_TIMEOUT)
        self.assertEqual(new_session.post.call_args[1].get("timeout"), DEFAULT_HTTP_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
