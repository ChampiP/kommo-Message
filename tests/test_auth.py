"""
Tests for KommoAuth: in-memory session reuse, single-flight 401/403 recovery,
and concurrency behavior.
"""
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
import requests

from app.services.auth import KommoAuth, AuthError


class TestKommoAuth(unittest.TestCase):

    def setUp(self):
        self.auth = KommoAuth()

    def test_background_refresh_not_running_by_default(self):
        self.assertIsNone(self.auth._session)
        self.assertIsNone(self.auth._refresh_thread)
        self.assertFalse(self.auth._stop)

    @patch("requests.Session")
    def test_get_session_caches_and_reuses_session(self, mock_session_cls):
        mock_session_instance = MagicMock()
        mock_session_instance.cookies.get.side_effect = lambda key: {
            "csrf_token": "test-csrf",
            "session_id": "test-session-id",
        }.get(key)
        auth_res = MagicMock()
        auth_res.status_code = 200
        mock_session_instance.post.return_value = auth_res
        mock_session_cls.return_value = mock_session_instance

        # First call should perform login
        s1 = self.auth.get_session()
        self.assertEqual(s1, mock_session_instance)
        self.assertEqual(mock_session_cls.call_count, 1)

        # Subsequent calls should return cached session without calling login again
        s2 = self.auth.get_session()
        self.assertEqual(s2, s1)
        self.assertEqual(mock_session_cls.call_count, 1)

    @patch.object(KommoAuth, "_perform_login")
    def test_recover_session_relogins_when_session_matches(self, mock_perform_login):
        s1 = MagicMock(name="session_1")
        s2 = MagicMock(name="session_2")
        mock_perform_login.side_effect = [s1, s2]

        initial = self.auth.get_session()
        self.assertEqual(initial, s1)
        self.assertEqual(mock_perform_login.call_count, 1)

        recovered = self.auth.recover_session(failed_session=s1)
        self.assertEqual(recovered, s2)
        self.assertEqual(mock_perform_login.call_count, 2)
        self.assertEqual(self.auth.get_session(), s2)

    @patch.object(KommoAuth, "_perform_login")
    def test_recover_session_ignores_stale_failed_session(self, mock_perform_login):
        s1 = MagicMock(name="session_1")
        s2 = MagicMock(name="session_2")
        mock_perform_login.side_effect = [s1, s2]

        self.auth.get_session()  # sets self._session = s1
        self.auth.recover_session(failed_session=s1)  # updates self._session = s2

        # A late thread reporting s1 as failed should get s2 without relogin
        res = self.auth.recover_session(failed_session=s1)
        self.assertEqual(res, s2)
        self.assertEqual(mock_perform_login.call_count, 2)

    @patch.object(KommoAuth, "_perform_login")
    def test_recover_session_single_flight_concurrent(self, mock_perform_login):
        s1 = MagicMock(name="session_1")
        s2 = MagicMock(name="session_2")

        login_count = 0

        def slow_login():
            nonlocal login_count
            login_count += 1
            time.sleep(0.05)  # simulate network delay to force contention
            return s2

        mock_perform_login.return_value = s1
        self.auth.get_session()  # initial session s1
        self.assertEqual(mock_perform_login.call_count, 1)

        mock_perform_login.side_effect = slow_login

        threads = []
        results = [None] * 10

        def worker(index):
            results[index] = self.auth.recover_session(failed_session=s1)

        for i in range(10):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Exactly 1 new login must have happened
        self.assertEqual(login_count, 1)
        for res in results:
            self.assertEqual(res, s2)
        self.assertEqual(self.auth.get_session(), s2)

    def test_invalidate_clears_session(self):
        dummy_session = MagicMock()
        self.auth._session = dummy_session
        self.auth.invalidate()
        self.assertIsNone(self.auth._session)

    @patch("requests.Session")
    def test_login_failure_raises_auth_error(self, mock_session_cls):
        mock_session_instance = MagicMock()
        mock_session_instance.cookies.get.return_value = None
        mock_session_instance.cookies.keys.return_value = []
        auth_res = MagicMock()
        auth_res.status_code = 401
        mock_session_instance.post.return_value = auth_res
        mock_session_cls.return_value = mock_session_instance

        with self.assertRaises(AuthError):
            self.auth.login()


if __name__ == "__main__":
    unittest.main()
