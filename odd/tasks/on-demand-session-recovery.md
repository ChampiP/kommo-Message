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
- Existing tests and new session lifecycle tests pass (64/64 passed in pytest and unittest discover).

## Delivery evidence
- Commit: `4c8a658 feat(auth): recover sessions only on authentication failure`
- Focused/full verification: `python -m unittest discover -s tests -v` — 64 tests passed.
- Runtime harness: N/A; this change has no separate runtime harness beyond the application lifespan and HTTP client tests.
- Rollback boundary: revert the commit to restore periodic Kommo/Amojo refresh behavior.

## Review correction
- Finding: Amojo-triggered Kommo relogin failures can raise `AuthError` through the route without the intended `503` mapping, and the final refreshed-credential read was outside error handling.
- Correction: Map both `AmojoError` and `AuthError` to `503` for initial and final Amojo credential reads; add route regression tests.
- Correction rollback boundary: revert only the route error-mapping change and its tests; the on-demand recovery behavior remains otherwise unchanged.

## Review hardening
- Add finite connect/read timeouts to every Kommo/Amojo HTTP call so recovery locks cannot be held indefinitely (`DEFAULT_HTTP_TIMEOUT = (5, 15)` in `app/core/config.py`).
- Return Amojo token and account UUID atomically under one lock (`get_credentials()`) and ensure `recover_session()` returns a consistent pair from a single lock acquisition.
- Require both a successful authorization status (200/302) and a session cookie (`session_id`) after Kommo login in `auth.py`.
- Add regression tests for timeout propagation, atomic credential reads, login validation, and both route AuthError paths across `tests/test_auth.py`, `tests/test_amojo.py`, `tests/test_kommo_api.py`, and `tests/test_chats_route.py`.
- Defer removal of unused legacy refresh methods and broader API decoupling as non-blocking follow-up cleanup.
- Follow-up correction evidence: `python -m unittest discover -s tests -v` — 64 tests passed (Commit: 06c0223 fix(auth): harden on-demand session recovery).
