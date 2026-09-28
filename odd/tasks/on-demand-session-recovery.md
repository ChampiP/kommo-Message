# On-demand session recovery

## Goal
Avoid unnecessary Kommo login notifications by keeping the in-memory session and renewing Kommo/Amojo credentials only after authentication failure.

## Scope
- Keep one shared Kommo `requests.Session` in memory.
- Remove periodic Kommo and Amojo refresh loops from the runtime path.
- On HTTP 401/403, coordinate one relogin/refresh and retry the failed operation once.
- Cache the Amojo token instead of requesting a new token for every endpoint call.
- Prevent concurrent requests from performing duplicate relogins.
- Add focused tests for caching, one-shot retry, and concurrent recovery.

## Non-goals
- Persisting sessions across process restarts.
- Changing Kommo/Amojo endpoint contracts.
- Retrying arbitrary network errors or non-authentication failures.
- Introducing a distributed lock for multiple application processes.

## Tasks
- [x] 1. Update Kommo authentication ownership and one-shot recovery locking.
- [x] 2. Cache Amojo credentials and refresh only on demand.
- [x] 3. Integrate one-shot 401/403 retries at the API boundary.
- [x] 4. Add regression tests and run the focused/full test gates.

## Acceptance evidence
- No background login/token refresh is started during normal runtime (verified in `app/main.py` lifespan and `tests/test_auth.py`, `tests/test_amojo.py`).
- Repeated successful calls reuse the same session and Amojo token (verified in `test_get_session_caches_and_reuses_session` and `test_get_x_auth_token_lazy_fetch_and_caching`).
- A 401/403 causes at most one coordinated recovery and one retry (verified in `tests/test_kommo_api.py`, `tests/test_amojo.py`, `tests/test_chats_route.py`).
- Concurrent expiration does not cause duplicate recovery operations (verified via single-flight concurrency tests in `tests/test_auth.py` and `tests/test_amojo.py`).
- Existing tests and new session lifecycle tests pass (46/46 passed in pytest and unittest discover).

## Delivery evidence
- Commit: `710655c feat(auth): recover sessions only on authentication failure`
- Focused/full verification: `python -m unittest discover -s tests -v` — 46 tests passed.
- Runtime harness: N/A; this change has no separate runtime harness beyond the application lifespan and HTTP client tests.
- Rollback boundary: revert the commit to restore periodic Kommo/Amojo refresh behavior.
