# Short-Term Memory

Current project context. Read this before starting any work.

Last updated: 2026-03-27

---

## Active Work

- **LiveKit migration** (started 2025-02) — Migrating voice AI from Vapi to LiveKit. LiveKit is now the active voice system (dependencies, tools, SIP integration, VoiceProvider enum all in place). Vapi routes removed. Remaining: `services/voice_service/providers/livekit/` not yet created, some later migration phases TBD. → `docs/plans/livekit-migration/`

- **Eval platform Wave 3** (started 2026-03-28) — Eval service runner, evaluators, config snapshot. Wave 3 shipped as PR #3840. Now integrating pal-agents DeepEval metrics (v0.2.210) to replace custom LLM judges. → `docs/plans/eval-platform-proposal.md`

- **Eval scenarios DB migration** (started 2026-04-23) — Migrating eval YAML scenario files from filesystem to `eval_scenarios` DB table. Table created; next: repository, service layer rewrite, API endpoints, seed script. → `docs/plans/eval-scenarios-db-migration.md`

## Recently Landed

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

- `agent/agent.py` LLMObs bootstrap — trace isolation depends on current structure

## Upcoming

- Billing V2/V3 — multi-channel notifications with EventBridge, throttling, SMS → `docs/plans/notifications/v2-architecture.md`
