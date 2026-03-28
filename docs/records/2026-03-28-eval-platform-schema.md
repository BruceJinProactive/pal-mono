# Eval Platform Schema — DB Models + Fingerprint Columns

**Date**: 2026-03-28
**Author**: Jacob Wang
**Status**: Implemented

## Context

The eval platform needs database tables to track evaluation runs, per-scenario results, and agent configuration snapshots. Additionally, the Conversation table needs fingerprint columns to link voice calls to the exact agent/prompt version that handled them.

Without these tables, there is no way to:
- Store eval run metadata (status, counts, scores, timing)
- Record per-scenario evaluation results with metric scores
- Capture point-in-time agent configuration for reproducibility
- Trace which agent version handled a given conversation

## Decision

Add three new SQLAlchemy models and two new columns to the existing Conversation model.

### New Tables

**`eval_runs`** — Tracks evaluation run lifecycle:
- UUID primary key, references `project_id` and `account_id`
- `status` (pending/running/completed/failed), `triggered_by` (api/scheduler/ci)
- Aggregate counts: `scenario_count`, `passed_count`, `failed_count`, `overall_score`
- Timestamps: `started_at`, `completed_at`, `created_at`, `updated_at`
- `agent_fingerprint` (nullable) links to the agent config snapshot used

**`eval_results`** — Per-scenario metric scores:
- UUID primary key, `eval_run_id` indexed UUID referencing `eval_runs` (no DB-level FK per codebase convention)
- `scenario_id` (string), `metric_name`, `score` (float), `passed` (bool)
- `raw_output` (JSONB) for full evaluator output
- `conversation_id` (nullable) links to the conversation if one was created

**`agent_config_snapshots`** — Immutable agent config at point-in-time:
- `fingerprint` (SHA-256 hex, 64 chars) as primary key — NOT a UUID
- `agent_id`, `project_id`, `system_prompt_hash`, `system_prompt_text`
- `config_snapshot` (JSONB) — full stable config used for fingerprint computation
- `first_seen_at`, `last_seen_at` — tracks when this config was active

### Conversation Table Changes

Two new nullable indexed columns on `conversations`:
- `agent_fingerprint VARCHAR(64)` — links to `agent_config_snapshots.fingerprint`
- `prompt_fingerprint VARCHAR(64)` — hash of the prompt text used

Both are nullable and indexed for efficient querying. Additive-only change, no risk to existing data.

## Consequences

### Benefits
- Structured storage for eval results enables dashboards, trend analysis, and regression detection
- Fingerprint-based snapshots allow exact reproduction of agent behavior at any point in time
- Conversation-level fingerprints enable "which config version handled this call?" queries

### Tradeoffs
- Three new tables increase schema surface area
- `agent_config_snapshots` uses a string PK (fingerprint) rather than UUID — intentional for content-addressable lookup
- Alembic migrations must be generated with Docker before merge

## Related
- `db/tables/eval_runs.py`, `db/tables/eval_results.py`, `db/tables/agent_config_snapshots.py`
- `db/tables/conversations.py` — fingerprint columns
- `services/agent_service/_fingerprint.py` — computes the fingerprints (separate PR)
- `docs/plans/conversation-eval/` — full eval platform design
