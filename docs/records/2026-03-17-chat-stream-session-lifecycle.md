# Chat Stream Session Lifecycle Fix

**Date:** 2026-03-17
**Author:** Codex
**Issue:** SQLAlchemy async pooled connections were still being garbage-collected in chat streaming paths after the earlier transaction-release fix.

## Problem

The earlier mitigation in `services/message_service/_implementation.py` reduced how long chat and voice flows pinned a database connection by committing before long-running LLM work. That helped transaction scope, but it did not change session ownership.

The two public chat streaming entrypoints still accepted request-scoped `AsyncSession` objects and held them inside long-lived `StreamingResponse` generators:

- `api/routes/chat/chat.py`
- `api/routes/chat/chat_completions.py`

When the client disconnected or the stream was cancelled, cleanup timing depended on framework dependency teardown rather than the generator itself. That is the shape most consistent with SQLAlchemy warnings like:

`The garbage collector is trying to clean up non-checked-in connection ...`

## Solution

Move async session ownership to the streaming route layer.

Both chat entrypoints now:

- create their own `AsyncSessionLocal()` when no explicit session is injected
- hold that session inside an async context manager owned by the generator
- roll back on exceptions before exiting the managed session context

This keeps the session lifetime aligned with the actual stream lifetime instead of the request handler lifetime.

## Files Changed

- `api/routes/chat/chat.py`
- `api/routes/chat/chat_completions.py`
- `tests/api/routes/test_chat_stream_cancellation.py`

## Key Decision

Keep the lower-level service API compatible by allowing optional injected sessions for tests and internal callers, but make the public routes responsible for owning long-lived streaming sessions.

That avoids a wider refactor while fixing the leak at the boundary where lifetime mismatches occur.

## Validation

Targeted streaming and cancellation tests passed:

```bash
uv run pytest -q tests/api/routes/test_chat_stream_cancellation.py tests/api/routes/chat/test_chat_completions.py
```

Added test coverage confirms:

- existing injected-session test paths still work
- unmanaged route calls create a session
- cancelled streams still exit cleanly
- managed session contexts are exited on cancellation

## Follow-Up

If the same warning still appears after this patch, the next most likely suspects are other long-lived async request paths that keep request-scoped sessions across streaming or background work, especially voice/Vapi handlers.
