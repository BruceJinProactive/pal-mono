# Eval Langfuse trace boundary per scenario

**Date**: 2026-05-05
**Status**: Implemented
**Related**: `docs/records/2026-04-25-langfuse-otel-migration.md` (if present), `services/message_service/_tracing.py`

## Problem

Every scenario and every turn inside a single eval run shared the **same Langfuse `trace_id`**. The Langfuse UI showed one gigantic trace per eval run instead of one trace per test case, making per-scenario debugging effectively impossible.

`session_id` was already correct (one per scenario, because it's set from the freshly-created `conversation_id` in `services/message_service/_tracing.py::langfuse_message_span`). Only `trace_id` was leaking across scenarios.

## Root cause

Two-part interaction between OTel auto-instrumentation and `asyncio.create_task`:

1. **Service is booted via `opentelemetry-instrument`.** `pyproject.toml` pulls in `opentelemetry-distro` + `opentelemetry-instrumentation-fastapi` (and `-starlette`, `-asyncpg`, `-httpx`, `-sqlalchemy`, …). The distro auto-instruments FastAPI at startup, so **every HTTP handler runs inside an auto-created root OTel span**. There is no explicit `FastAPIInstrumentor().instrument_app(app)` call — it's invisible in the source tree.
2. **`asyncio.create_task` snapshots contextvars.** `services/eval_service/_runner.py::create_eval_run` kicks off work with `asyncio.create_task(_run_eval_background(...))` from the `POST /evals/runs` handler. That snapshot includes the OTel span context of the originating request. The HTTP response returns and the FastAPI span ends, but the captured `SpanContext` (trace_id + span_id) is still sitting in the background task's context — OTel doesn't clear `trace_id` when a span ends.

Inside `_run_eval_background`, scenarios fan out via `asyncio.gather(*(_worker(s) for s in scenarios))`. Every `_worker` inherits the same leaked context. Each turn calls `services/message_service/_tracing.py::langfuse_message_span` → `lf.start_as_current_observation(...)`. Langfuse SDK v4 is OTel-backed, so it sees the leaked parent context and attaches every new observation as a **child of the original POST's (now-ended) span** → all observations share that trace_id.

Net effect: one eval run = one Langfuse trace, with hundreds of turn-level spans from unrelated scenarios all nested under it.

## Fix

Enforce a scenario-level trace boundary that (a) strips the leaked OTel context and (b) opens an explicit scenario-level root observation so turns nest sensibly.

### New: `services/eval_service/_tracing.py`

`scenario_trace_boundary(eval_run_id, scenario_id)` — context manager that:

1. `otel_context.attach(otel_context.Context())` — detach the inherited (leaked) OTel context. Any observation created inside the `with` block starts with an empty parent context.
2. `lf.start_as_current_observation(name="Eval Scenario", as_type="span", input={"scenario_id": ...})` — open the scenario's root observation. Every subsequent `langfuse_message_span` in this async context sees this as the active parent and becomes a child, sharing its `trace_id`.
3. `propagate_attributes(tags=[f"eval_run:{eval_run_id}", f"scenario:{scenario_id}"], metadata={...})` — makes the resulting trace filterable in the Langfuse UI by eval run or scenario. This plugs the separate gap that there was previously no direct link from a Langfuse trace back to its eval run.

The module docstring explains the asyncio+OTel footgun in detail so the next person doesn't delete the `attach(Context())` thinking it's redundant.

### Edited: `services/eval_service/_runner.py::_worker`

Wraps the scenario execution (`async with sem: await _run_one_scenario(...)`) in `scenario_trace_boundary(...)`. The semaphore acquisition stays inside the boundary so the scenario span covers the real work only.

## Resulting Langfuse shape

| Level | Count per eval run | Langfuse identifier |
|---|---|---|
| Eval run | 1 | no native grouping — filter via tag `eval_run:<uuid>` |
| Scenario (test case) | N | N distinct `trace_id`s, N distinct `session_id`s, tagged `scenario:<id>` |
| Turn | M per scenario | child observations under the scenario's `trace_id` |

`session_id` (= `conversation_id`, set in `services/message_service/_tracing.py`) now lines up 1:1 with `trace_id` at the scenario level.

## Why not the alternatives

- **Detach at the background-task boundary only** (no explicit scenario span): gives one trace per **turn** rather than one per scenario, because each `langfuse_message_span` would start with an empty parent context and become its own root. Loses the "all turns of one test case grouped" property that makes the Langfuse UI useful for scenario debugging.
- **Only add tags, don't detach**: tags help filtering but the underlying trace_id still leaks across scenarios.
- **Scenario span without detach**: the scenario span would itself become a child of the leaked FastAPI trace → still one trace per eval run.

Both pieces are required.

## Broader lesson (also captured in `docs/memory/long-term.md`)

Any `asyncio.create_task(...)` spawned from an HTTP handler inherits the FastAPI request's OTel context. Long-lived background work that produces its own traces (Langfuse, explicit OTel spans, tool spans) must call `otel_context.attach(otel_context.Context())` at the task boundary (or at whatever logical sub-unit boundary matches the desired trace granularity) to avoid silently sharing a `trace_id` with the originating HTTP request. This is not specific to Langfuse — any OTel-based tracing is affected.

Other `asyncio.create_task(...)` fire-and-forget sites in the codebase likely share this behavior; they don't produce Langfuse traces today so the symptom is invisible, but worth auditing if/when we extend tracing to those paths.

## Verification

- `./scripts/validate.sh --check` → clean (black, ruff, isort, pyright, lint-imports, toml-sort).
- Manual verification post-merge: run an eval with ≥2 scenarios, confirm in Langfuse that each scenario appears as a distinct trace with `tag:eval_run:<uuid>` and `tag:scenario:<id>`, and all turns nest under the "Eval Scenario" root.
