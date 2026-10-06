# Structured JSON logging

Branch: `chore/remove-background-refresh`

## Goal

Emit every log line (app and uvicorn) as one redacted JSON object with
request correlation, execution context, and structured error data.

Field naming follows Elastic Common Schema (flattened dot keys):
`@timestamp`, `log.level`, `log.logger`, `message`, `service.name`,
`process.pid`, `process.thread.name`, `log.origin.*`, `http.request.id`,
`error.type`, `error.message`, `error.stack_trace`, plus `extra=` fields.

## Tasks

- [x] 1. Remove unused periodic refresh loops — `efe59c1`
- [x] 2. JSON formatter + request-id context + access middleware + uvicorn routing, with tests — `ab31d36`
- [x] 3. Remove unused `ws_client.py` (raw `print` of WebSocket payloads) — `d9bb8c2`
- [x] 4. Verify full suite and commit — 76 passed; live uvicorn smoke run emitted only JSON lines, no duplicate access log
