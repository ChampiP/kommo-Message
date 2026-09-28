# Organize application modules under app

## Goal
Move runtime configuration and the optional WebSocket client into the application package while preserving API behavior, Docker startup, environment handling, and test coverage.

## Tasks
- [x] Move configuration ownership to `app/core/config.py` and update imports.
- [x] Move the WebSocket client to `app/services/ws_client.py` and remove the root-level implementation.
- [x] Update Docker packaging and verify imports/build/runtime behavior.
- [x] Commit the refactor on `main`.

## Acceptance criteria
- No active application import depends on root-level `config.py`.
- Runtime configuration remains environment-driven with the same required variables and failure behavior.
- The WebSocket client implementation lives under `app/services/`.
- Docker builds and the service remains healthy.
- Focused tests pass and no endpoint contract changes occur.

## Evidence
- Configuration moved to `app/core/config.py` with `app/core/__init__.py`. All active imports updated (`app/services/kommo_api.py`, `app/services/auth.py`, `app/services/amojo.py`, `app/main.py`).
- WebSocket client moved to `app/services/ws_client.py`.
- Root `config.py` and `ws_client.py` removed; neither is importable from root.
- Dockerfile updated to remove root `config.py` copy; packaging verified via Docker build and runtime container healthcheck.
- Unit test suite passes without regressions (18/18 tests pass).
- Refactor committed on `main` after independent verification.
