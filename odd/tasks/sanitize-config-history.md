# Remove hardcoded test URLs and sanitize Git history

## Goal
Remove the test-specific Kommo URL and all hardcoded service URLs from runtime configuration, then rewrite repository history so the test URL is absent before pushing.

## Tasks
- [x] Replace runtime URL defaults with required environment configuration.
- [x] Remove hardcoded WebSocket and documentation provider URLs.
- [x] Verify no test URL remains in the worktree or reachable Git history.
- [x] Commit the configuration/documentation changes.
- [x] Rewrite local history, force-push the sanitized branch, and verify the remote.

## Acceptance criteria
- Runtime URLs come from environment variables; no test-domain default remains in code.
- No user test domain or other unnecessary URL remains in tracked files or Git history.
- `.env` remains local and untracked.
- The sanitized branch is pushed to origin after explicit history rewrite; the sanitized history is now published on `main`, remote feature branch was deleted, and only `main` remains locally/remotely.
- A temporary rollback reference was recorded before rewriting and removed after the remote was verified; unreachable old objects were pruned locally.

## Evidence

- Active local and remote history contains no user test domains, tunnel URLs, or concrete provider hosts.
- `origin/main` was force-updated to sanitized commit `e6f59dc`; the sanitized history is now published on `main` (fast-forwarded at `e57124f` and pushed to `origin/main`), remote feature branch was deleted, and only `main` remains locally/remotely.
- The pre-existing `.gitignore` change remains uncommitted and preserved.
