# DB Connection Pool Leak Fixes

**Date:** 2026-03-17
**Issue:** AsyncAdaptedQueuePool connection leaks causing pool exhaustion in PRD/LAT

## Problem

CloudWatch logs showed SQLAlchemy GC cleanup warnings:

```
The garbage collector is trying to clean up non-checked-in connection
<AdaptedConnection <asyncpg.connection.Connection object at 0x7fd4b74e8e50>>,
which will be terminated.
```

In LAT, this escalated to full pool exhaustion (102 QueuePool timeout errors). In PRD, 45 GC-cleaned connections were observed during the 8:30-9:30 AM EST window, combined with OpenAI API timeouts that amplified the issue.

### Root Cause: Three Async Session Leak Patterns

1. **`async for session in get_db_async(): ... break`** — The `break` suspends the async generator without calling `.aclose()`, so the `async with` inside `get_db_async()` never exits and the connection is never returned to the pool. It relies on GC to eventually clean up.

2. **Bare `AsyncSessionLocal()` without `async with`** — Calling `await session.close()` in a `finally` block does NOT call `__aexit__` on the session factory's context manager, so the underlying connection may not be returned to the pool.

3. **`asyncio.create_task()` without stored references** — The task object can be garbage-collected before completion if no strong reference exists, killing the task mid-execution and abandoning any checked-out connections.

## Solution

### Connection Leak Fixes

| File | Pattern | Fix |
|------|---------|-----|
| `services/monitoring_service/_implementation.py` | `async for session in get_db_async(): ... break` | `async with AsyncSessionLocal() as session:` |
| `api/routes/admin/_onboarding.py` | `async_session = AsyncSessionLocal()` (bare) | `async with AsyncSessionLocal() as async_session:` |

### Task GC Prevention

| File | Pattern | Fix |
|------|---------|-----|
| `services/monitoring_service/_implementation.py` | `asyncio.create_task(coro)` (no reference) | Module-level `_background_tasks` set + `_schedule_background_task()` helper |
| `api/routes/chat/chat.py` | `asyncio.create_task(generate_and_send())` (no reference) | Module-level `_background_tasks` set + done callback |
| `api/routes/internal/_voice.py` | `_task = asyncio.create_task(...)` (local var) | Module-level `_background_tasks` set + done callback |

### Logging & Metrics Improvements

| File | Improvement |
|------|-------------|
| `services/monitoring_service/_implementation.py` | `statsd` histogram `monitoring.rerun.duration_ms` and counters `monitoring.rerun.completed`/`failed`/`fatal_error` with `media_type` and `error_type` tags. Structured `extra` dict on all log calls. |
| `api/routes/chat/chat.py` | `_on_done` callback logs task exceptions with `exc_info` |
| `api/routes/internal/_voice.py` | `_on_done` callback logs task exceptions with `conversation_id` context |

## The Correct Pattern

Background tasks that need their own DB session should use:

```python
# Module-level set prevents GC of in-flight tasks
_background_tasks: set[asyncio.Task] = set()

async def _my_background_task():
    async with AsyncSessionLocal() as session:  # guarantees __aexit__ and pool return
        try:
            await do_work(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

# When scheduling:
task = asyncio.create_task(_my_background_task())
_background_tasks.add(task)
task.add_done_callback(_background_tasks.discard)
```

**Never use:**
- `async for session in get_db_async(): ... break` — generator leak
- `session = AsyncSessionLocal()` without `async with` — no `__aexit__`
- `asyncio.create_task(coro)` without storing the reference — GC risk

## Tests

| Test File | Tests |
|-----------|-------|
| `tests/services/monitoring_service/test_session_leak.py` | 5 tests: context manager on success/error, no get_db_async, _background_tasks exists, no bare create_task |
| `tests/api/routes/admin/test_onboarding_session_leak.py` | 2 tests: uses `async with AsyncSessionLocal`, context manager protocol |
| `tests/api/routes/chat/test_task_gc.py` | 2 tests: _background_tasks set exists, no bare create_task |
| `tests/api/routes/internal/test_voice_task_gc.py` | 2 tests: _background_tasks set exists, no local _task variable |

## Validation

All 11 tests pass locally. Pool configuration unchanged (size=30, max_overflow=50, pool_timeout=30).

## References

- SQLAlchemy async session docs: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- Python asyncio task references: https://docs.python.org/3/library/asyncio-task.html#creating-tasks
- Existing pattern: `api/routes/integrations/slack/_interactions.py` (`_background_tasks` set + `_schedule_background_task`)
