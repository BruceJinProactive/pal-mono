# Short-Term Memory

Current project context. Read this before starting any work.

Last updated: 2026-06-10

---

## Active Work

- **Contract-to-account onboarding PRD** (started 2026-06-10) - Product plan for replacing manual pre-go-live onboarding across contract signing, account creation, ToS acceptance, Slack/Folk/Notion visibility, and FDE handoff. -> `docs/plans/onboarding/contract-account-tos-handoff-prd.md`

- **Tool-result ElastiCache migration** (started 2026-06-01) - Moving recent
  tool-result context from process-local `pal-agents` memory to shared
  ElastiCache so cross-pod follow-up turns can see prior tool outputs.
  Current pal-mono slices add reusable Redis/Valkey env-backed cache settings,
  a Redis client factory, a best-effort tool-result cache adapter with
  per-family allowlists for compact cached payloads, and message-service
  background writes for streaming/non-streaming `tool_call` events. The current
  pal-mono read slice hydrates non-empty ElastiCache results onto
  `RuntimeContext.previous_tool_results` before `PalAgent.run(...)` while
  leaving the process-local pal-agents fallback untouched on cache misses.
  Current validation adds cross-pod-style write/read coverage and failure-mode
  tests for Redis read errors in non-streaming and streaming chat paths. ->
  `docs/plans/tool-result-elasticache-migration.md`

- **Eval runner parallel scenarios** (2026-04-29) — Scenarios within an eval run now execute concurrently, bounded by `max_concurrency` (request parameter on `RunEvalRequest` / `create_eval_run`; default 4). Applies uniformly to all driver modes including voice — each voice scenario owns an isolated LiveKit room, orchestrator, TTS engine, and egress pipeline, so concurrency is bounded by caller infra (worker pool, rate limits), not by shared in-process state. Each worker owns its own `AsyncSession`; counter updates on the outer session are serialised via `asyncio.Lock`. → `docs/plans/conversation-eval/parallel-scenario-execution-plan.md`

- **LiveKit migration** (started 2025-02) — Vapi is fully removed at the code level: `tools/vapi_tool/` and `api/routes/integrations/vapi/` source files are deleted, `VoiceProvider` enum is LiveKit-only (explicitly rejects `"vapi"`), and the `assistant-request` webhook is gone. Residual legacy only: `conversations.vapi_control_url` column (kept for historical data) and a few stale docstrings/log strings in `services/number_service/_implementation.py`, `api/routes/internal/_voice.py`, and admin routes. Remaining LiveKit work: `services/voice_service/providers/livekit/` not yet created, plus later migration phases TBD. → `docs/plans/livekit-migration/`

- **Eval scenarios DB migration** (started 2026-04-23) — Migrating eval YAML scenario files from filesystem to `eval_scenarios` DB table. Table + repository shipped (record: `docs/records/2026-04-23-eval-scenarios-table.md`). PR #4087 migrated eval tests to DB. 2026-05-01 (PAL-10278): added pal-agents case-spec JSON → scenario YAML converter + generated Sonny's BBQ corpus (`services/eval_service/scripts/convert_case_specs.py`, `services/eval_service/scenarios/ordering/sonnys_bbq.yaml`); output is forward-compatible with `eval_scenarios.raw_yaml` so the converter can be reused in-memory by the seed script. Remaining: API endpoints for scenario CRUD, seed/backfill script (which will absorb `sonnys_bbq.yaml`), retire YAML filesystem fallback.

- **Eval context modifier for phone injection** (started 2026-04-25) — After removing `"api"` from the `customer_phone` channel list (PR #4086), API-channel evals get `customer_phone=None`. Adding an optional `context_modifier` callback on `get_chat_response_async` that only the eval `InProcessDriver` uses, to inject phone into RuntimeContext without polluting the public `Message.Metadata` schema. Also lays groundwork for future overrides (e.g. `spec_modifier`). → `docs/plans/conversation-eval/eval-context-modifier-plan.md` (partially shipped in PR #4092).

- **Frozen analytics/change-log dataclasses** (started 2026-04) — PAL-10000 through PAL-10012 converting analytics, monitoring, order, catering, message, lead, tool-call, change-log, integration, change-field payloads into frozen dataclasses. Most shipped on main; watch for remaining PAL-101xx follow-ups and consumer migrations.

## Recently Landed

- 2026-05-28: **Voice SLO metrics.** Added OTel SLO counters and duration histograms for `Voice call close` and `Chat turn bridge`: `voice.call.close`, `voice.call.close.duration`, `chat.completions.turn.bridge`, and `chat.completions.turn.bridge.duration`. Voice close now distinguishes `conversation_not_found`, `db_close_failed`, and `phone_call_missing` from true close success; chat bridge distinguishes success from empty output, fallback, cancellation, and request/response persistence failures. → `docs/records/2026-05-28-voice-slo-metrics.md`
- 2026-05-05: **Eval Langfuse trace boundary per scenario** (PAL-10344). Every scenario (test case) in an eval run now produces its own Langfuse trace; all turns of a scenario nest under a single "Eval Scenario" root observation and share one `trace_id`. Filterable via `eval_run:<uuid>` / `scenario:<id>` tags. Fixes a silent trace-leak caused by `asyncio.create_task` snapshotting the originating FastAPI request's auto-instrumented OTel span context. New helper: `services/eval_service/_tracing.py::scenario_trace_boundary`. → `docs/records/2026-05-05-eval-langfuse-trace-boundary.md`. Long-term memory updated with the `asyncio.create_task` + OTel footgun pattern — likely recurs elsewhere.
- 2026-05-01: **Eval case-spec converter** (PAL-10278). `services/eval_service/scripts/convert_case_specs.py` turns pal-agents case-spec JSON into `EvalScenario` YAML; generated `services/eval_service/scenarios/ordering/sonnys_bbq.yaml` (5,288 lines, do not hand-edit). Pure/stateless, reusable by the future `eval_scenarios` seed script. → `docs/records/2026-05-01-eval-case-spec-converter.md`
- 2026-04-28: **StatsD → OTel metrics migration**. Removed `utils/dd.py` (DogStatsd). All metrics now use OTel `increment_counter` / `record_histogram` / `record_duration` from `utils/otel.py`, exported via OTLP. `datadog` package removal is a separate PR.
- 2026-04-28: **Eval `spec_modifier` for order-submission safety** — `InProcessDriver` now installs `apply_eval_safety` by default via a new `spec_modifier` hook on `message_service.get_chat_response_async`. Forces `toast.submit_orders=False` and `adora.force_payment_link=True` regardless of DB config. → `docs/records/2026-04-28-eval-spec-modifier.md`
- 2026-04-28: **Eval platform docs graduated — Phase 1 + Phase 2 + system state**.
  - New `docs/state/eval-platform.md` — living architecture reference (API, DB tables, driver modes, evaluators, fingerprinting, fragile zones).
  - New `docs/state/eval-platform-fde-guide.md` — user-facing workflow guide (moved from `docs/plans/`).
  - New records: `docs/records/2026-04-28-eval-platform-phase1-completion.md`, `docs/records/2026-04-28-eval-platform-phase2-completion.md`.
  - Historical design docs moved to records: `2026-03-01-eval-platform-proposal.md`, `...-requirements.md`, `...-implementation-plan.md`, `...-timeline.md`.
  - Removed from `docs/plans/conversation-eval/`: 13 P1 plans, `prompt-traceability-plan.md`, `phase2-audio-native-proposal.md` (all shipped).
  - Remaining active plans: `phase2-followups-plan.md` (audio_quality wiring, DUAL_CHANNEL recording, DirectDriver), `rubric-by-scenario-type-plan.md`, `eval-context-modifier-plan.md` (spec_modifier in PR #4104), `langfuse-integration-plan.md` (new draft).
- 2026-04-25: **Datadog LLMObs → Langfuse/OTel migration** (PAL-10113, PR #4090). ADR-013 superseded. LLM observability now uses Langfuse SDK v4 (`@observe` decorators in `agent/agent.py`, `agent/framework/agno.py`, tool `_implementation.py` files). General tracing moves to OpenTelemetry (Grafana Tempo).
- 2026-04-24: Langfuse dependency added (PAL-10112, PR #4089) — precursor to the LLMObs migration.
- 2026-04-23: `eval_scenarios` table landed → `docs/records/2026-04-23-eval-scenarios-table.md`.
- 2026-04-08: Eval AI-driven turns + `tool_call_records` table → `docs/records/2026-04-08-eval-ai-driven-turns.md`, `docs/records/2026-04-08-tool-call-records-table.md`.
- 2026-04-01: `ChangeResourceType` enum migration → `docs/records/2026-04-01-changeresourcetype-enum-migration.md`.
- 2026-03-31: Eval API routes → `docs/records/2026-03-31-eval-api-routes.md`.
- 2026-03-28: Eval platform Wave 3 (runner, evaluators, config snapshot) shipped → `docs/records/2026-03-28-eval-platform-schema.md`. `pal-agents` DeepEval metrics integrated (now on v0.2.265).
- 2026-03-27: Voice config language refactoring complete (3-PR series) — PR1: Pydantic validators. PR2: SQLAlchemy CHECK constraints. PR3: Alembic migration for data cleanup + removed legacy handling. All voice configs now lowercase, no more combined languages or triage.
- 2026-03-19: Plans audit — graduated 4 completed plans to records, removed stale checkpoint auth plan
  - Monitoring config restructure → `docs/records/2026-03-09-monitoring-config-restructure.md`
  - PromptV2 capability system → `docs/records/2026-01-21-prompt-v2-capability-system.md`
  - Billing notifications V1 → `docs/records/2025-12-04-billing-notifications-v1.md`
  - Google business hours updater → `docs/records/2025-11-14-business-updater-google-hours.md`
  - Checkpoint auth migration removed (feature deprecated → `docs/records/2026-03-17-deprecate-checkpoint-service.md`)
  - Operations: signal sources V1 → `docs/records/2025-12-23-signal-sources-v1.md`
  - Operations: monitoring system V1 → `docs/records/2025-12-29-monitoring-system-v1.md`
  - Operations: routines system V1 → `docs/records/2025-12-30-routines-system-v1.md`
- 2026-03-17: Fixed chat streaming session ownership so long-lived/cancelled streams close async DB sessions explicitly and do not rely on request dependency teardown

## Recent Resolutions

- **DB connection pool leaks** (2026-03-17) — All known leak sources fixed. PR #3716 fixed 5 patterns (fire-and-forget tasks, bare sessions, generator break). PR #3725 fixed streaming session lifecycle (`chat_completions.py`, `chat.py` now own sessions via `AsyncSessionLocal()` inside generators). Keep the streaming ownership pattern from ADR-019; do not regress to request-scoped sessions inside long-lived generators. → `docs/records/2026-03-17-db-connection-leak-fixes.md`, `docs/records/2026-03-17-chat-stream-session-lifecycle.md`, ADR-019

## Don't Touch (fragile / in-progress)

- `agent/agent.py` Langfuse `@observe` tracing — trace isolation depends on the current structure (decorator on the top-level processing function + the inner streaming generator wrapper). Do not collapse or reorder these without understanding the trace tree implications.
- Do not reintroduce `ddtrace.llmobs` / Datadog LLMObs instrumentation — that pathway was removed as part of the 2026-04-25 migration. `utils/dd.py` has been deleted; all metrics are now in `utils/otel.py`.

## Upcoming

- Billing V2/V3 — multi-channel notifications with EventBridge, throttling, SMS → `docs/plans/notifications/v2-architecture.md`
