# Postmortem: Database Connection Pool Exhaustion

**Date of incident:** 2026-03-06
**Date of postmortem:** 2026-03-17
**Severity:** High (degraded service, silent request failures)
**Duration:** ~24 hours (escalating throughout the day, peak impact 17:00-00:00 UTC)
**Environment:** PRD, LAT

---

## Summary

On March 6th, the production database connection pool experienced progressive exhaustion due to async connection leaks. Connections were checked out of SQLAlchemy's `AsyncAdaptedQueuePool` but never returned, causing the garbage collector to forcibly terminate 1,806 leaked connections in PRD over the course of the day. This resulted in failed transactions, closed connections mid-flight, and silently dropped chat responses and voice call post-processing.

---

## Impact

- **1,806 connections** leaked and GC-terminated in PRD on March 6th
- **362 connections/hour** leaked at peak (23:00 UTC)
- At least **1 confirmed transaction failure**: `InterfaceError: cannot call Transaction.rollback(): the underlying connection is closed` in `get_chat_response_stream` at 01:10 UTC
- **4 "Event loop is closed" errors** — background tasks killed before DB sessions were returned
- **Silent degradation**: chat responses and voice call evaluations dropped without user-facing errors
- Both **PRD** and **LAT** affected; STG had minor impact (17 leaks)

---

## Timeline

| Time (UTC) | Event |
|---|---|
| **Mar 2, 21:52** | [PAL-7637] merged: added fire-and-forget `asyncio.create_task()` for evaluation events in `_voice.py` — **introduced Leak #3** |
| **Mar 3, 15:43** | `fba88d5a` merged: major expansion of `end_voice_call` (+505 lines) — analytics, phone records, Stripe metering — **massively increased traffic through leaky voice path** |
| **Mar 3, 15:47–22:16** | PRs #3608-#3612: four rapid-fire session handling fixes in `_voice.py` — team was seeing DB errors but treating symptoms |
| **Mar 3** | PRD pool leaks: **1,302/day** (up from 507 on Mar 2) |
| **Mar 4** | PRD pool leaks: **1,439/day** |
| **Mar 5** | PRD pool leaks: **1,596/day** |
| **Mar 6, 01:10** | `InterfaceError` in `get_chat_response_stream` — connection closed mid-transaction during message commit |
| **Mar 6, 04:32** | "Event loop is closed" errors — background tasks GC'd before completion |
| **Mar 6, 17:00–23:00** | Leak rate escalated: 114/hr -> 193/hr -> 208/hr -> **362/hr** |
| **Mar 6 (end of day)** | PRD pool leaks: **1,806/day** |
| **Mar 17** | Root cause identified and fixed in `fix/db-connection-pool-leaks` branch |

---

## Root Cause

Three distinct async patterns caused connections to leak from the pool:

### Pattern 1: Fire-and-forget `asyncio.create_task()` (3 locations)

```python
# Task can be garbage-collected before completion, killing its DB session
asyncio.create_task(some_coroutine_with_db_session())
```

When the task reference goes out of scope (local variable or no assignment at all), Python's GC can collect the task object, cancelling the coroutine mid-execution. Any DB connection held by that coroutine is abandoned — never committed, never rolled back, never returned to the pool.

**Affected files:**
- `api/routes/chat/chat.py` — `generate_and_send()` (highest traffic)
- `api/routes/internal/_voice.py` — `_publish_livekit_evaluation_event()` (introduced Mar 2)
- `services/monitoring_service/_implementation.py` — `_rerun_monitoring_analysis_background()`

### Pattern 2: Bare `AsyncSessionLocal()` without context manager (1 location)

```python
# If exception occurs before finally block, connection leaks
async_session = AsyncSessionLocal()
try:
    ...
finally:
    await async_session.close()  # close() != __aexit__(), may not return to pool
```

**Affected file:** `api/routes/admin/_onboarding.py`

### Pattern 3: `async for` generator with `break` (1 location)

```python
# break suspends generator without calling .aclose(), connection never returned
async for session in get_db_async():
    ...
    break  # generator cleanup relies on GC
```

**Affected file:** `services/monitoring_service/_implementation.py`

---

## Why It Didn't Cause Outages Before March 2nd

The leaky code paths were either **brand new** or **low traffic** before March 2nd:

1. **Leak #3 (voice evaluation)** was introduced on March 2nd in [PAL-7637]. Before this, `end_voice_call` didn't have fire-and-forget background tasks.

2. **March 3rd massively amplified the voice path** — `fba88d5a` added analytics extraction, phone call records, and Stripe metering to every voice call, increasing the amount of work (and DB session time) inside the leaky fire-and-forget pattern.

3. **Leak #2 (chat)** existed before but at lower traffic volumes, the GC could reclaim abandoned tasks fast enough to keep the pool above water.

4. **Leaks #4 and #5** (monitoring rerun, onboarding) were low-traffic paths that contributed background noise but never enough to tip the pool over.

The critical shift was that **every voice call** — the highest-traffic path — now ran through the fire-and-forget pattern. The pool drain rate exceeded the GC recovery rate, and it compounded throughout the day as traffic increased.

### Update (2026-03-18): Streaming Session Leak Identified

Investigation revealed a **sixth, dominant leak source**: the `BaseHTTPMiddleware` + `StreamingResponse` + `Depends(get_db_async)` interaction. Every streaming request through `POST /chat/completions` (used by LiveKit voice) and `POST /chat` leaked exactly 1 connection because:

- `BaseHTTPMiddleware` (added Feb 20, `2a18fba0`) causes dependency cleanup to fire when the handler returns the `StreamingResponse` object, before streaming begins.
- The streaming generator's `session` (from `Depends`) is closed before it's used.
- **Zero streaming traffic existed before March 3** — LiveKit voice calls were the first to use the `POST /chat/completions` streaming path. Datadog confirms "Completed streaming response after" logs first appeared March 3 (120 entries), with zero before that date.

This means `BaseHTTPMiddleware` was a latent condition since Feb 20, and LiveKit streaming traffic starting March 3 was the trigger. See ADR-019 (`docs/decisions/019-streaming-session-ownership.md`) for the fix.

---

## Resolution

### Immediate Fix (branch: `fix/db-connection-pool-leaks`)

| Commit | Fix |
|---|---|
| `3f35b306` | Fixed all 5 leak sources |
| `2bb59822` | Added test coverage for background task callbacks and statsd metrics |
| `dc56eae2` | Addressed CodeRabbit feedback, improved diff coverage |
| `2563b543` | Improved test coverage and formatting |
| `63b4b425` | Guarded statsd calls to prevent telemetry failures from masking successful runs |

**Specific fixes:**

| File | Before | After |
|---|---|---|
| `api/routes/chat/chat.py` | `asyncio.create_task(generate_and_send())` | Task tracked in module-level `_background_tasks` set with done callback |
| `api/routes/internal/_voice.py` | `_task = asyncio.create_task(...)` (local var) | Task tracked in module-level `_background_tasks` set with done callback |
| `services/monitoring_service/_implementation.py` | `asyncio.create_task(coro)` + `async for session in get_db_async()` | `_schedule_background_task()` helper + `async with AsyncSessionLocal()` |
| `api/routes/admin/_onboarding.py` | `async_session = AsyncSessionLocal()` | `async with AsyncSessionLocal() as async_session:` |
| `services/message_service/_implementation.py` | `user.id` accessed after commit (MissingGreenlet) | `user_id = user.id` captured before commit |

---

## Detection Gaps

1. **No monitoring on pool health** — the 1,806 GC warnings went unnoticed for days
2. **No lint rule against bare `asyncio.create_task()`** — the dangerous pattern was introduced in a reviewed PR
3. **Documentation recommended the dangerous pattern** — `api/routes/CLAUDE.md` showed fire-and-forget `create_task` as the correct background task pattern
4. **Rapid symptom-fixing masked the root cause** — four PRs in 3 hours on March 3rd fixed individual session errors without identifying the systemic task GC issue

---

## Action Items

### P0 — Immediate

| Action | Owner | Status |
|---|---|---|
| Fix remaining 3 bare `create_task` calls in `checkpoint_service` and `_onboarding.py` | | TODO |
| Create Datadog monitor on `"garbage collector is trying to clean up non-checked-in connection"` (warn >10/hr, critical >50/hr) | | TODO |

### P1 — This Sprint

| Action | Owner | Status |
|---|---|---|
| Create shared `utils/background_tasks.py` with `schedule()` function that handles task tracking, done callbacks, and error logging | | TODO |
| Add lint rule to `validate.sh` banning bare `asyncio.create_task` in `services/` and `api/` — enforce use of `utils.background_tasks.schedule()` | | TODO |
| Add lint rule banning `= AsyncSessionLocal()` without `async with` | | TODO |

### P2 — Next Sprint

| Action | Owner | Status |
|---|---|---|
| Update `api/routes/CLAUDE.md` background task pattern to use safe utility | | TODO |
| Add `docs/memory/long-term.md` entry for async task and session patterns | | TODO |
| Evaluate adding `pool_pre_ping=True` to SQLAlchemy engine config as defense-in-depth | | TODO |

---

## Lessons Learned

### What went well
- The SQLAlchemy GC warnings provided clear evidence of the leak in Datadog Flex logs
- The `_background_tasks` pattern from `slack/_interactions.py` was a proven solution already in the codebase
- Test coverage was added for each fix to prevent regression

### What went wrong
- A dangerous async pattern was introduced in a reviewed PR without being caught
- The team spent 3 hours on March 3rd fixing symptoms (session commit/rollback) instead of the root cause (task GC)
- No runtime alerting on connection pool health — the issue escalated for 4 days before investigation

### Where we got lucky
- Python's GC was aggressive enough to reclaim most leaked connections, preventing a full outage
- The highest-impact window (23:00 UTC) coincided with lower user-facing traffic
- No data corruption occurred despite transactions being killed mid-flight
