# Langfuse ↔ Eval Platform Integration Plan

**Status:** Draft
**Owner:** TBD
**Started:** 2026-04-28
**Related:**
- PR #4090 (PAL-10113) — Datadog LLMObs → Langfuse/OTel migration
- PR #4099 (PAL-10112) — Langfuse session data in `message_service`
- `docs/state/eval-platform.md` — eval platform architecture reference
- `docs/records/2026-04-28-eval-platform-phase1-completion.md` § "Prompt traceability (chat parity)"

---

## TL;DR

Langfuse is already tracing every LLM call and tool span for production traffic (and, incidentally, for every eval run — since evals go through `agent/agent.py`). We are currently **not using any of it in the eval loop**. This plan wires Langfuse into `services/eval_service/` as a **complement** to the existing evaluator/scorecard stack, focused on three wins:

1. **Deep-link from a failed eval row to the exact Langfuse trace.**
2. **Push DeepEval + custom evaluator scores to Langfuse** as trace `scores` for regression dashboards over time.
3. **Tag eval traces** with `eval_run_id`, `scenario_id`, `scenario_version`, `turn_index`, `agent_id` so prod vs. eval traffic is separable and queryable.

Non-goals: replacing DeepEval / custom evaluators, moving scenarios off the `eval_scenarios` Postgres table, replacing `_prompt_traceability.py`, or instrumenting voice-specific signals (those stay in OTel/Tempo).

---

## Motivation

Today, when an eval fails:

- We have `tool_call_records`, a config snapshot (`_snapshot.py`), and the evaluator's pass/fail + score.
- We do **not** have a turnkey view of the underlying LLM calls: prompts, token counts, model latency, tool result payloads, intermediate reasoning.
- Debugging means replaying the conversation locally or grepping logs.

Meanwhile, Langfuse already has all of that for every turn — we just haven't tagged the traces with eval identifiers and haven't linked them from eval results. This is low-hanging fruit.

Secondary motivation: Langfuse's **Scores API** gives us longitudinal dashboards (metric x scenario x agent x model over time) essentially for free once we push scores into it. Today our regression view is a SQL query against `eval_results`.

---

## Current State

### Langfuse wiring (already in place)

- SDK v4 client via `langfuse.get_client()`.
- `@observe` decorators on:
  - `agent/agent.py` — top-level processing + streaming generator wrapper (flagged fragile in `docs/memory/short-term.md`; **do not restructure**).
  - `agent/framework/agno.py`
  - Tool `_implementation.py` files (~15 tools).
- `services/message_service/_tracing.py` — `langfuse_message_span()` root context manager that propagates `session_id`, `user_id`, `tags`, and `metadata` via `propagate_attributes(...)`.

### Eval platform (already in place)

- `services/eval_service/_runner.py` — orchestrates `create_eval_run` → `_run_eval_background` → `_run_scenario_for_mode` → `_run_conversation`.
- `services/eval_service/_inprocess_driver.py` — calls the agent in-process (bypasses HTTP) for text evals.
- `services/eval_service/_voice_eval_runner.py` — voice path.
- `services/eval_service/_evaluators.py` + `evaluators/` — DeepEval adapter + custom evaluators (`tool_call_args`, `audio_quality`, `stt_accuracy`, etc.).
- `eval_scenarios` DB table (PR #4087) — source of truth for scenarios.
- `eval_runs` / `eval_results` tables — run metadata + per-metric scores.

### Gap

Zero references to `langfuse` in `services/eval_service/` or `tests/services/eval_service/`. Eval runs produce Langfuse traces by accident (because they go through the instrumented agent), but those traces are indistinguishable from production traffic and aren't linked from the eval result rows.

---

## Scope

### In scope

1. **Trace tagging** — every eval turn's Langfuse trace carries eval identifiers.
2. **Trace ID persistence** — store the Langfuse `trace_id` on the `eval_results` (or a new join) row so UI/CLI can deep-link.
3. **Score push** — after evaluators run, push scores to Langfuse via `langfuse.create_score(...)`.
4. **Env separation** — ensure dev/lat/stg eval runs are distinguishable (tag-based, same project, or a separate Langfuse project — decide in Phase 0).

### Out of scope

- Migrating scenarios to Langfuse Datasets (keep Postgres as source of truth).
- Replacing DeepEval or custom evaluators.
- Langfuse prompt registry (PromptV2 in DB is the source of truth).
- Voice-specific non-LLM signal instrumentation (stays OTel → Tempo).
- Changing `@observe` structure in `agent/agent.py` (explicitly fragile).

---

## Design

### Phase 0 — Decisions (before coding)

- [ ] **Same Langfuse project vs. separate `eval` project?**
  - Recommendation: **same project**, separated by a mandatory `environment:eval` tag + `eval_run_id` tag. Rationale: enables trivial prod-vs-eval comparison on the same scenario. Cost/quota should be evaluated — eval runs can be high-volume.
  - Fallback: separate project via `LANGFUSE_PROJECT_*` env vars if volume becomes a problem.
- [ ] **Trace granularity**: one Langfuse trace per **turn** or per **conversation**?
  - Production uses one trace per user message (per `message_service` invocation). Keep the same for evals — one trace per eval turn. The conversation is stitched via `session_id = conversation_id` (same as prod).
- [ ] **Score naming convention**: `eval.<metric_name>` vs. `<metric_name>`? Pick one and stick with it (recommend `eval.<metric_name>` to avoid clashing with any future prod-side scoring).

### Phase 1 — Tag eval traces

Add an eval-aware variant of `langfuse_message_span` or pass an `eval_context` dict down so the `InProcessDriver` can set additional `propagate_attributes` **before** the agent span starts.

Preferred shape: thread an `eval_context: EvalTraceContext | None` through `_run_conversation` → `InProcessDriver.send_message` → wrap the existing `langfuse_message_span` call with an additional `propagate_attributes(...)` that adds:

```python
tags=[
    "environment:eval",
    f"eval_run_id:{run_id}",
    f"scenario_id:{scenario_id}",
    f"scenario_version:{scenario_version}",
    f"turn_index:{turn_index}",
    f"mode:{mode}",                 # text / voice
],
metadata={
    "eval_run_id": str(run_id),
    "scenario_id": str(scenario_id),
    "scenario_version": scenario_version,
    "turn_index": turn_index,
    "driver": "inprocess" | "voice",
},
```

Voice path: same in `_voice_eval_runner.py`, wrapping whatever entry point triggers the agent span.

**Constraint:** do not touch `agent/agent.py` decorators. All tagging happens at the caller layer via `propagate_attributes`, which is how `message_service` already does it.

### Phase 2 — Capture and persist trace IDs

In `_inprocess_driver.py` (and voice equivalent), after the agent call returns, capture the current trace id:

```python
trace_id = lf.get_current_trace_id()   # or langfuse.get_client().get_current_trace_id()
```

Return it alongside the conversation turn result. `_run_conversation` collects per-turn trace IDs and persists them.

**Storage options (pick one):**

- **A. Add `langfuse_trace_id: str | None` to `eval_results`** — simplest, denormalized per (scenario, metric) row. Many rows repeat the trace id if a scenario has multiple metrics per turn.
- **B. New table `eval_turn_traces(run_id, scenario_id, turn_index, langfuse_trace_id, langfuse_session_id)`** — normalized, also useful for future per-turn artifacts (audio URIs, snapshots).
- **C. Add to `tool_call_records`** — wrong layer; trace id is per turn, not per tool call.

Recommendation: **B**. One migration, clean join, room to grow. If we're time-boxed, **A** is acceptable for a spike.

### Phase 3 — Push scores

After `evaluate_scenario()` returns in `_run_eval_background`, for each `EvalResult` row, call:

```python
from langfuse import get_client
lf = get_client()
lf.create_score(
    trace_id=turn_trace_id,           # or session-level if metric is conversation-scoped
    name=f"eval.{er.metric_name}",
    value=er.score,                   # float
    data_type="NUMERIC",
    comment=er.reason,                # evaluator's explanation, if any
)
```

Conversation-level metrics (e.g. `conversation_success`) attach to the **session** (`session_id`), not a single turn trace. Langfuse supports session-level scores via `session_id=`.

Batch/flush at end of run (`lf.flush()`), not per score, to keep latency low.

### Phase 4 — UI / CLI deep links

Minimal: expose `langfuse_trace_id` in the existing eval-run GET endpoint response (`api/routes/eval/_implementation.py::get_eval_results`). Frontend can render a link to `${LANGFUSE_BASE_URL}/project/${LANGFUSE_PROJECT_ID}/traces/${trace_id}`.

If there's a CLI / admin tool for inspecting runs, add the same link there.

### Phase 5 (optional, stretch) — Replay / diff tooling

Once trace IDs are persisted, we can:

- Pull full traces from Langfuse via API and diff two runs (e.g., model A vs. model B on the same scenario set).
- Auto-create Langfuse "Experiments" tagged with the config snapshot hash.

Defer unless Phase 1–4 prove the integration's value.

---

## Work Breakdown

Tracer-bullet: Phase 1 + a minimal slice of Phase 2 (option A) + Phase 3 on a single metric end-to-end first, then fan out.

| # | Task | Files | Est. |
|---|------|-------|------|
| 0 | Phase 0 decisions written up inline in this doc | this file | 0.5 d |
| 1 | `EvalTraceContext` dataclass + thread through runner → driver | `services/eval_service/_runner.py`, `_inprocess_driver.py` | 0.5 d |
| 2 | Wrap agent call with extra `propagate_attributes` for eval tags | `_inprocess_driver.py`, `_voice_eval_runner.py` | 0.5 d |
| 3 | Capture `trace_id` per turn, return from driver | `_inprocess_driver.py`, `_voice_eval_runner.py` | 0.5 d |
| 4 | Migration: `eval_turn_traces` table (option B) | `db/tables/eval_turn_traces.py`, `db/migrations/versions/` | 0.5 d |
| 5 | Persist per-turn trace IDs in `_run_conversation` | `_runner.py` | 0.5 d |
| 6 | Push per-metric scores to Langfuse after `evaluate_scenario` | `_runner.py` | 0.5 d |
| 7 | Session-level scores for conversation-scoped metrics | `_runner.py`, `_evaluators.py` | 0.5 d |
| 8 | Expose `langfuse_trace_id` in `get_eval_results` response | `api/routes/eval/_implementation.py`, `api/schemas/eval/` | 0.25 d |
| 9 | Tests: mock Langfuse client, verify tags + score calls | `tests/services/eval_service/` | 1 d |
| 10 | Docs: record + update `docs/state/` if architecture doc has an eval section | `docs/records/YYYY-MM-DD-langfuse-eval-integration.md` | 0.25 d |

**Rough total:** ~5 engineering days for Phases 1–4.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| High-volume eval runs blow Langfuse quota | Tag + monitor; if needed, move to a separate Langfuse project via env var. Consider sampling eval traces for large sweeps. |
| Langfuse outage blocks eval runs | All Langfuse calls must be non-blocking / swallow exceptions. Existing `@observe` is best-effort; keep that posture. Score push should be fire-and-forget with a final `flush(timeout=...)`. |
| Trace ID captured before agent finishes streaming | Capture **after** the agent call returns in the driver, not mid-stream. In-process driver awaits full completion anyway. |
| Regressing the `agent/agent.py` decorator structure | Do all tagging at the caller (driver) layer via `propagate_attributes`. Do not add/move `@observe` in the agent module. Explicit rule in `docs/memory/short-term.md`. |
| Score name collisions with future prod scoring | Namespace all eval-originated scores as `eval.<metric>`. |
| PII in trace metadata | Scenario payloads can contain test phone numbers / names. They already flow through prod Langfuse traces; no new exposure. Do not add raw customer data to tags (tags are indexed/searchable). |

---

## Open Questions

- [ ] Same Langfuse project or separate? (see Phase 0)
- [ ] Do we want to push a single **aggregate** score per run (`eval.overall_score`) as a session-level score, in addition to per-metric scores?
- [ ] Voice eval: is the agent span even created in the `_voice_eval_runner.py` path, or does it go through a different entry point that needs its own tagging?
- [ ] Do we need a rate limiter / sampler for very large scenario sweeps (>1k scenarios × N metrics)?
- [ ] Frontend: who owns adding the deep link, and does the eval UI exist yet?

---

## Success Criteria

- Running an eval produces Langfuse traces tagged with `environment:eval` and all eval identifiers.
- Every `eval_results` row can be joined to a Langfuse trace id (via `eval_turn_traces`).
- DeepEval + custom evaluator scores appear in the Langfuse UI, filterable by `eval_run_id` and `scenario_id`.
- A failed eval result in the UI (or API response) includes a one-click deep link to the Langfuse trace.
- No regression in eval run latency > 5% (Langfuse calls are async/fire-and-forget).
- No change in production Langfuse behavior.
