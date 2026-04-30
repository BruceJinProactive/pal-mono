# Plan: Parallel scenario execution in eval runner

Last updated: 2026-04-29
Status: Proposed

## Context

`services/eval_service/_runner.py::_run_eval_background` executes scenarios
**sequentially** inside a single `for scenario in scenarios:` loop (around
line 212). Each iteration `await`s a full driver conversation
(`_run_scenario_for_mode`) plus LLM-judge evaluation (`evaluate_scenario`)
before the next scenario starts. Evaluators within a scenario already fan out
via `asyncio.gather` (`_evaluators.py:97-112`), and per-run
(`_schedule_eval_background`) runs are backgrounded — but scenarios inside a
run are strictly serial.

A typical run has N scenarios × (~multi-turn LLM conversation +
evaluator fan-out). Wall-clock time is ~N × per-scenario latency. Nothing
about the scenarios themselves is inherently serial: each scenario creates a
fresh `InProcessDriver` (and thus a fresh conversation) and writes
independent `EvalResult` rows keyed by `scenario_id`. The only shared state
is the `EvalRun` row's progress counters.

The repository already anticipates concurrent updates — see
`EvalRunRepositoryAsync.update_counts` docstring: *"This method may be called
concurrently by scenario workers during a run. Callers are responsible for
serialising updates at the service layer … no locking is implemented here."*
This plan finally uses that contract.

## Goal

Run up to `max_concurrency` scenarios in parallel inside one eval run, cutting
wall-clock time by roughly `max_concurrency` × (minus LLM/DB
contention), while preserving:

- Per-scenario result isolation (one failing scenario must not poison others).
- Correct final `passed_count` / `failed_count` / `overall_score`.
- The existing `update_counts` progress-visibility behaviour (counters move
  monotonically as scenarios complete, not only at the end).
- Cancellation semantics (`cancel_eval_run` still cancels the whole run).
- ADR-019 session ownership — long-lived parallel workers own their own
  `AsyncSession` rather than sharing the outer one.

## Non-goals

- Parallelism *across* eval runs. Different `eval_run_id`s already run
  concurrently via `_schedule_eval_background`; nothing changes there.
- Parallelising evaluators within a scenario — already done in
  `_evaluators.py`.

## Design

### Configuration

`max_concurrency` is a **function/API parameter**, not an env var. Threaded
through the call stack:

- `RunEvalRequest.max_concurrency: int | None` (Pydantic field, `ge=1, le=64`, default `None`).
- `create_eval_run(..., max_concurrency: int | None = None)`.
- `_schedule_eval_background(..., max_concurrency: int | None = None)`.
- `_run_eval_background(..., max_concurrency: int | None = None)`.

Resolution rule (`_resolve_max_concurrency`):

- `None` → `_DEFAULT_MAX_CONCURRENCY` (currently `4`).
- Else → `max(1, max_concurrency)` (values < 1 clamped).
- `driver_mode` is accepted for future per-mode defaults but is currently
  unused. Voice mode honours the same cap as text modes — see the "Voice
  mode" note below.

Why a parameter instead of env:

- Tests pass the cap directly — no `monkeypatch.setenv` / global state leaks
  between tests.
- Per-request tuning possible (admin UI can expose it; scheduled runs can
  pick a conservative cap while interactive debugging uses `1`).
- No deployment redeploy needed to change concurrency for a specific run.

### Structure

Extract the per-scenario body into:

```python
async def _run_one_scenario(
    scenario: EvalScenario,
    driver_mode: str,
    recipient_id: str,
    channel: str,
    eval_run_id: uuid.UUID,
) -> tuple[bool, bool]:  # (completed_cleanly, passed)
    """Own session. Runs + evaluates one scenario, writes its EvalResult rows,
    commits. Returns (True, passed) on success, (False, False) on exception
    (already logged & rolled back in its own session)."""
```

This helper:

1. Opens its **own** `AsyncSessionLocal()` context.
2. Calls `_run_scenario_for_mode(...)` passing that session (important for
   voice mode, which writes via `VoiceResultCollector`).
3. Calls `evaluate_scenario(record)`.
4. Writes all `EvalResult` rows via a fresh `EvalResultRepositoryAsync`.
5. Commits and returns `(True, scenario_passed)`.
6. On exception: rolls back, logs with `eval_run_id`, returns `(False, False)`.

### Fan-out loop

Replace the `for scenario in scenarios:` block with:

```python
max_concurrency = _resolve_max_concurrency(driver_mode)
sem = asyncio.Semaphore(max_concurrency)
counter_lock = asyncio.Lock()
passed_count = 0
failed_count = 0

async def _worker(scenario: EvalScenario) -> None:
    nonlocal passed_count, failed_count
    async with sem:
        ok, passed = await _run_one_scenario(
            scenario, driver_mode, recipient_id, channel, eval_run_id
        )
    # Counter + progress update under lock, on the outer session.
    async with counter_lock:
        if ok and passed:
            passed_count += 1
        else:
            failed_count += 1
        completed = passed_count + failed_count
        score = passed_count / completed if completed else 0.0
        await run_repo.update_counts(
            eval_run_id,
            scenario_count=completed,
            passed_count=passed_count,
            failed_count=failed_count,
            overall_score=score,
        )
        await session.commit()

await asyncio.gather(*(_worker(s) for s in scenarios))
```

Why this shape:

- **Per-scenario session ownership** — result rows + conversation reads
  don't contend on the outer session. Follows ADR-019.
- **Counter updates stay on the outer session, serialised by
  `counter_lock`** — avoids the lost-update race the repo docstring warns
  about, and avoids opening yet another session per progress tick.
- **No `return_exceptions=True`** — `_run_one_scenario` already converts
  scenario failures into `(False, False)` returns, so any exception that
  escapes is a genuine runner bug that should propagate to the outer
  `try/except Exception` and fail the run (same as today's outer `except`).
- **`async with sem` scopes only the heavy work** — the counter/commit
  section is tiny and can proceed even if workers are queued on the
  semaphore.

### Cancellation

`cancel_eval_run` currently calls `task.cancel()` on the outer background
task. Cancelling that task will propagate a `CancelledError` into
`asyncio.gather`, which cancels all in-flight `_worker` tasks, which cancels
their inner coroutines. Each `_run_one_scenario` is inside a session
context manager, so the session closes cleanly. The outer `except
asyncio.CancelledError` path is unchanged.

### Voice mode

`run_voice_scenario` creates fully isolated per-scenario resources:
a fresh LiveKit room, `LiveKitRoomOrchestrator`, `TTSEngine`, call_id,
participant token, and (optionally) egress pipeline. Cleanup is in a
`finally:` block that tears down room, egress, orchestrator, TTS engine,
and LiveKit API client — each wrapped in its own `try/except` so one
failure does not leak the others. No shared mutable in-process state
exists between scenarios.

Therefore voice concurrency is bounded by **caller infrastructure**,
not by the eval runner:

- **LiveKit worker pool** — explicit dispatch via `agent_name`. If only
  N workers are available, LiveKit queues excess jobs; parallel scenarios
  beyond N simply wait, they do not fail.
- **Cartesia TTS / STT / LLM rate limits** — shared per API key.
- **LiveKit room quota** — each scenario holds one room for the call
  duration.

Operationally: a default of `4` is the same trade-off we accept for text
modes. Callers who know their pool size can pass a higher value; callers
with a single-worker deployment should pass `1`. The runner no longer
makes this decision on their behalf.

### Tests

`tests/services/eval_service/test_runner.py` currently asserts via
`update_counts.await_args` (last call) — insensitive to call order, so
those assertions still hold. New tests:

1. `test_scenarios_run_up_to_max_concurrency` — 6 scenarios with
   `max_concurrency=3`. Instrument `_run_scenario_for_mode` with a
   `Lock`/counter to assert in-flight concurrency hits 3 and never exceeds
   it.
2. `test_default_concurrency_when_none` — `_resolve_max_concurrency("http", None)`
   returns `_DEFAULT_MAX_CONCURRENCY`.
3. `test_voice_mode_honors_requested_concurrency` — voice returns the
   requested cap (no longer forced to 1); `None` → default.
4. `test_concurrency_clamped_to_one` — `0` and negative values clamp to 1.
5. `test_single_failure_does_not_affect_siblings` — 3+ scenarios, one
   raises. Final counters = N-1 passed, 1 failed.
6. `test_counter_updates_not_lost_under_concurrency` — 20 scenarios @
   `max_concurrency=8`, exact pass/fail totals (no lost updates from the
   counter race).

## Risks / tradeoffs

| Risk | Mitigation |
| --- | --- |
| LLM provider rate limits (simulator + judge) | Default `4`; env-tunable down to `1`. Follow-up could add adaptive backoff. |
| DB connection pool exhaustion (each worker opens its own session) | `4` workers + outer session = well inside the pool. If we raise the default later, re-evaluate. |
| Non-deterministic `update_counts` call sequence | Already acceptable — counters are absolute, not incremental; lock prevents lost writes. Tests don't assert intermediate order. |
| LiveKit worker / SIP pool exhaustion in voice mode | Excess scenarios queue at LiveKit, they do not fail; default cap 4 is conservative. Callers can pass `1` for single-worker deploys. |
| Shared mutable state in drivers/simulator | `InProcessDriver` is instantiated per-scenario inside `_run_scenario_for_mode`; `UserSimulator` likewise. No shared state observed. |

## Rollback

Single-commit change scoped to `services/eval_service/_runner.py`,
`api/schemas/eval/requests.py`, `api/routes/eval/_implementation.py`, and
tests. Revert to restore sequential behaviour. Callers can also pass
`max_concurrency=1` at request time to force serial execution without a
code revert.

## Follow-ups

- Typed `EvalSettings` if/when more knobs appear (e.g. per-project
  default concurrency, per-mode defaults).
- Admin UI exposure of `max_concurrency` on the run-trigger form.
- Observability: record peak in-flight concurrency and queue-wait time
  (esp. for voice, where LiveKit queuing is invisible to the runner).
