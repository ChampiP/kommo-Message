# Remove hardcoded test URLs and sanitize Git history

## Goal
Remove the test-specific Kommo URL and all hardcoded service URLs from runtime configuration, then rewrite repository history so the test URL is absent before pushing.

## Tasks
- [ ] Replace runtime URL defaults with required environment configuration.
- [ ] Remove hardcoded WebSocket and documentation provider URLs.
- [ ] Verify no test URL remains in the worktree or reachable Git history.
- [ ] Commit the configuration/documentation changes.
- [ ] Rewrite local history, force-push the sanitized branch, and verify the remote.

## Acceptance criteria
- Runtime URLs come from environment variables; no test-domain default remains in code.
- No user test domain or other unnecessary URL remains in tracked files or Git history.
- `.env` remains local and untracked.
- The sanitized branch is pushed to origin after explicit history rewrite.
- A rollback reference is recorded before rewriting history.
