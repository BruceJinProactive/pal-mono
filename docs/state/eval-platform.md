# Eval Platform — System State

**Last updated**: 2026-05-11
**Status**: Phases 1–2 shipped; small follow-ups tracked in `docs/plans/conversation-eval/phase2-followups-plan.md`
**Historical design docs**: see `docs/records/2026-*-eval-*.md` and the original proposal / requirements / implementation-plan in git history under `docs/plans/conversation-eval/` (graduated 2026-04-28).

This is a living reference for the eval platform architecture. For user-facing workflows (authoring scenarios, running evals, reading scorecards) see the FDE guide: `docs/state/eval-platform-fde-guide.md`.

---

## Purpose

Run reproducible, scored test scenarios against Palona agents:

- **Pre-launch**: verify a new restaurant agent meets quality thresholds before going live.
- **Regression**: re-run scenarios after prompt, POS, or platform changes and catch regressions.
- **Voice-native**: run real LiveKit calls end-to-end (STT → LLM → tools → TTS) so audio-specific failures (latency, interruptions, STT errors) are measurable.

---

## Architecture at a Glance

```
┌───────────────────────────────────────────────────────────────┐
│  POST /v1/eval/run { project_id, scenarios?, driver_mode }    │
│  api/routes/eval/_implementation.py::trigger_eval_run         │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│  services/eval_service/_runner.py                              │
│    create_eval_run → _run_eval_background (FastAPI bg task)    │
│      → resolve scenarios (DB or YAML fallback)                 │
│      → _run_scenario_for_mode                                  │
│          ├── text  → InProcessDriver (in-proc message_service) │
│          └── voice → _voice_eval_runner (LiveKit room + caller)│
│      → evaluate_scenario (DeepEval + custom evaluators)        │
│      → write rows to eval_results                              │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│  GET /v1/eval/runs/{run_id}  → status + per-metric results     │
│  GET /v1/eval/scorecard/{project_id} → aggregate pass rates    │
└───────────────────────────────────────────────────────────────┘
```

---

## API Surface

Mounted at `/v1/eval` (prefix from `api/routes/endpoints.py::EVAL`). All routes live in `api/routes/eval/__init__.py` + `_implementation.py`.

| Method | Path | Handler | Purpose |
|--------|------|---------|---------|
| POST | `/run` | `trigger_eval_run` | Kick off a new eval run (202 Accepted, runs in background) |
| GET | `/runs` | `list_eval_runs_handler` | List runs with filters (project, status, date range) |
| GET | `/runs/{run_id}` | `get_eval_run_with_results` | Run status + per-scenario per-metric results |
| POST | `/runs/{run_id}/cancel` | `cancel_eval_run_handler` | Cancel a pending/running run |
| GET | `/scorecard/{project_id}` | `get_project_scorecard` | Aggregated recent-run pass rates per metric |

Full API design history: `docs/records/2026-03-31-eval-api-routes.md`.

---

## Database Tables

All exported in `db/tables/__init__.py`; Alembic migrations under `db/migrations/versions/`.

| Table | File | Purpose |
|-------|------|---------|
| `eval_scenarios` | `db/tables/eval_scenarios.py` | Scenario definitions (DB-backed; superseded filesystem YAML) |
| `eval_runs` | `db/tables/eval_runs.py` | Run lifecycle: status (`pending`/`running`/`completed`/`failed`/`cancelled`), counters, overall score |
| `eval_results` | `db/tables/eval_results.py` | Append-only per-scenario per-metric verdicts (`metric_name`, `score`, `passed`, `reason`, `raw_output`) |
| `agent_config_snapshots` | `db/tables/agent_config_snapshots.py` | Content-addressed (PK = fingerprint) snapshots of every distinct agent configuration seen. Upsert via `AgentConfigSnapshotRepository.get_or_create`. |
| `tool_call_records` | `db/tables/tool_call_records.py` | Captured tool calls per conversation (used by `tool_call_args` evaluator) |

Fingerprint columns on `conversations` (`agent_fingerprint`, `prompt_fingerprint`) let every voice and chat conversation link back to its exact agent config.

Repositories: `db/repositories/eval_run_repository.py`, `eval_result_repository.py`, `agent_config_snapshot_repository.py`. All async-only, inject `AsyncSession` via constructor, use `flush()`+`refresh()` (callers own transactions).

Historical design: `docs/records/2026-03-28-eval-platform-schema.md`, `docs/records/2026-04-23-eval-scenarios-table.md`, `docs/records/2026-04-08-tool-call-records-table.md`.

---

## Driver Modes

Selected by `driver_mode` on the run request, dispatched in `services/eval_service/_driver_factory.py`.

| Mode | Status | File | Transport | What it tests |
|------|--------|------|-----------|---------------|
| `http` (InProcessDriver) | ✅ Default for text | `services/eval_service/_inprocess_driver.py` | Calls `message_service.get_chat_response_async` in-process (no HTTP) | Full agent pipeline: prompt → LLM → tools → DB |
| `voice` | ✅ Shipped | `services/eval_service/_voice_eval_runner.py` + `_synthetic_caller.py` | LiveKit room with real agent + synthetic TTS caller | End-to-end voice: STT, LLM, tools, TTS, turn-taking, interruptions |
| `direct` (DirectDriver) | ❌ `NotImplementedError` | `_driver_factory.py:58` | Would wrap LiveKit's `AgentSession.run()` + `mock_tools()` | Fastest unit-style agent reasoning tests (deferred) |

### InProcessDriver

- Accepts an optional `context_modifier: Callable[[RuntimeContext], None]` hook that eval-only callers use to inject `customer_phone` into the runtime context without polluting the public `Message.Metadata` schema. History: `docs/plans/conversation-eval/eval-context-modifier-plan.md` (active; `spec_modifier` counterpart in PR #4104).
- Replaces the earlier `HTTPDriver` that made HTTP calls to `/v1/chat/` against itself — eliminated the `EVAL_API_BASE_URL` footgun. History: `docs/records/2026-04-08-eval-ai-driven-turns.md`.

### Voice runner

- `LiveKitRoomOrchestrator` (in pal-agents `pal_agents.evals.voice.room_orchestrator`) creates a room, dispatches the production agent, and connects a synthetic caller built on `pal_agents.evals.voice.tts_engine` + `personas`.
- Metrics are accumulated upstream by `pal-livekit-agent-cloud/infra/metrics.py::MetricsAccumulator` and delivered to pal-mono via `VoiceEndCallRequest.call_metrics`; consumed by `services/eval_service/_voice_result_collector.py`.
- Supports AI-driven turns via `_user_simulator.py` — an LLM persona generates the next caller utterance from transcript + scenario goal.

---

## Scenario Format

Loaded by `services/eval_service/_scenario_loader.py`; schema in `services/eval_service/schema.py`.

Sources (in priority order):

1. `eval_scenarios` DB table (PK `id`, scoped by `project_id`, versioned).
2. YAML files under `services/eval_service/scenarios/` (generic scenarios; filesystem fallback being retired).

A scenario contains: scripted turns or an AI-driven persona seed, expected outcomes (`task_completed`, `hallucination`), optional `context` (ground-truth facts), channel, and optional tool-call expectations.

---

## Evaluators

Live in `services/eval_service/evaluators/`. Wired into `services/eval_service/_evaluators.py::evaluate_scenario`.

### Text / transcript evaluators (always run)

| Module | Metric(s) | Notes |
|--------|-----------|-------|
| `judge_adapter.py` | LLM judge rubric (currently a single "Toast ordering" rubric; multi-rubric split planned — see `rubric-by-scenario-type-plan.md`) | Uses DeepEval judges |
| `tool_call_args.py` | `tool_call_args` | Compares captured tool calls from `tool_call_records` against scenario expectations. Toast tools use purpose-built argument matchers; `call_transfer` and `send_support_email` use generic subset argument matching. |

### Voice-only evaluators (when `record.is_voice`)

| Module | Metric | Source signal | Wired? |
|--------|--------|---------------|--------|
| `interruption.py` | `interruption` | `CallMetricsReport.interruptions` from `overlapping_speech` events | ✅ |
| `latency_silence.py` | `latency_silence` | Turn timestamps from `CallMetricsReport` | ✅ |
| `stt_accuracy.py` | `stt_accuracy` | Whisper WER vs. production Deepgram transcript | ✅ |
| `speech_rate.py` | `speech_rate` | `whisper-timestamped` words-per-minute per turn | ✅ |
| `speech_fidelity.py` | `speech_fidelity` | LALM-as-Judge (GPT-4o audio) comparing spoken vs. intended text | ✅ |
| `audio_quality.py` | `audio_quality` | `librosa` SNR, clipping, DC offset | ❌ Module exists; not imported by runner (see follow-ups plan) |

Historical rationale: `docs/records/2026-04-28-eval-platform-phase2-completion.md`.

---

## Fingerprinting & Traceability

Every voice call and chat message fingerprints its agent configuration so eval runs (and production calls) can be linked back to a reproducible agent spec.

- `services/agent_service/_fingerprint.py::compute_agent_fingerprint` — deterministic SHA-256 of stable config (prompt text, model, tools, flags; excludes timestamps).
- `services/agent_service/_raw_config.py::RawConfig.build_with_fingerprint` — wraps `build()` and also returns `(agent_fp, prompt_fp, config_dict)`.
- Chat: `services/message_service/_implementation.py::_fingerprint_conversation` — fire-and-forget background task that stamps `conversations.agent_fingerprint` + `prompt_fingerprint` and upserts `agent_config_snapshots`.
- Voice: `api/routes/internal/_voice.py` init fingerprints + `services/eval_service/_snapshot.py::upsert_agent_config_snapshot`.

Eval runs inherit fingerprinting automatically since they route through `message_service` (text) or the same voice init path.

---

## Key Files & Entry Points

```
api/routes/eval/                                 ← REST surface
services/eval_service/
  _runner.py                                     ← orchestration + background task
  _driver_factory.py                             ← driver_mode dispatch
  _inprocess_driver.py                           ← text driver
  _voice_eval_runner.py, _synthetic_caller.py    ← voice driver
  _voice_result_collector.py                     ← voice call → ConversationRecord
  _user_simulator.py                             ← AI-driven turn generation
  _scenario_loader.py, schema.py                 ← scenarios
  _evaluators.py                                 ← evaluator dispatch
  _snapshot.py                                   ← agent_config_snapshot upsert
  _prompt_traceability.py                        ← prompt-diff helpers
  evaluators/                                    ← individual metric implementations
db/tables/eval_{runs,results,scenarios}.py
db/tables/agent_config_snapshots.py
db/tables/tool_call_records.py
db/repositories/eval_{run,result}_repository.py
db/repositories/agent_config_snapshot_repository.py
```

Upstream in the `pal-livekit-agent-cloud` repo:

```
infra/metrics.py          ← MetricsAccumulator (per-turn STT/LLM/TTS, interruptions)
models/types.py           ← CallMetricsReport, TurnLatency, InterruptionEvent
session/handlers.py       ← subscribes to LiveKit events, sends report on shutdown
```

---

## Known Gaps / Active Work

Tracked in `docs/plans/conversation-eval/`:

- `phase2-followups-plan.md` — `audio_quality` wiring, `DUAL_CHANNEL_AGENT` stereo recording, `DirectDriver`.
- `rubric-by-scenario-type-plan.md` — split single ordering rubric into `ordering` / `info_inquiry` / `refusal` / `handoff` profiles.
- `eval-context-modifier-plan.md` — `spec_modifier` follow-up (PR #4104 open) to prevent real order submission during evals.
- `langfuse-integration-plan.md` — tag eval traces, push scores to Langfuse, deep-link from failed results.

---

## Fragile Zones

- `agent/agent.py` `@observe` decorator structure — trace isolation for Langfuse depends on the current decorator layout. Do not restructure. (See `docs/memory/short-term.md`.)
- `services/eval_service/_inprocess_driver.py` — the `context_modifier` plumbing is load-bearing for eval-only phone injection. Don't leak it to production callers of `get_chat_response_async`.
