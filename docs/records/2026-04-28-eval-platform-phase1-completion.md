# Eval Platform Phase 1 — Completion Record

**Date**: 2026-04-28
**Status**: Implemented
**Supersedes plans**: 13 plan files under `docs/plans/conversation-eval/` (P1-B1a–d, P1-B2a–b, P1-C1a–d, P1-C2, P1-E1, P1-inprocess-driver, prompt-traceability)

## Context

Phase 1 of the Voice AI Evaluation Platform (see `docs/plans/conversation-eval/proposal.md` and `implementation-plan.md`) is fully shipped. Individual Notion-task plans that guided implementation have served their purpose and are retired here. Each is summarized below with its landing file(s) so reviewers can trace the decision trail without keeping one-off plan files alive in `docs/plans/`.

Parent records already exist for the larger subsystems; this record covers the remaining granular tasks.

- `docs/records/2026-03-28-eval-platform-schema.md` — DB schema + Wave 3 runner
- `docs/records/2026-03-31-eval-api-routes.md` — API routes
- `docs/records/2026-04-08-eval-ai-driven-turns.md` — user simulator
- `docs/records/2026-04-08-tool-call-records-table.md` — tool-call capture
- `docs/records/2026-04-23-eval-scenarios-table.md` — scenarios DB migration

## What shipped (plan → code)

### B1 — Agent/prompt fingerprinting

| Plan | Shipped in |
|------|-----------|
| `P1-B1a` compute_agent_fingerprint() | `services/agent_service/_fingerprint.py` |
| `P1-B1b` build_with_hash() / build_with_fingerprint() | `services/agent_service/_raw_config.py::RawConfig.build_with_fingerprint` |
| `P1-B1c` fingerprint columns on Conversation | `db/tables/conversations.py` (`agent_fingerprint`, `prompt_fingerprint`); migration `db/migrations/versions/2026-03-28_00bdc822b20e_*` |
| `P1-B1d` wire fingerprints into voice init + events | `api/routes/internal/_voice.py` (Step 9 calls `build_with_fingerprint` and stamps the conversation) |

### B2 — Scenario format

| Plan | Shipped in |
|------|-----------|
| `P1-B2a` Pydantic models + YAML loader | `services/eval_service/schema.py`, `services/eval_service/_scenario_loader.py` |
| `P1-B2b` Author 10+ generic scenarios | `services/eval_service/scenarios/generic/*.yaml` |

Later moved to DB via `eval_scenarios` table — see `docs/records/2026-04-23-eval-scenarios-table.md`.

### C1 — Eval DB tables and repositories

| Plan | Shipped in |
|------|-----------|
| `P1-C1a` EvalRun + EvalResult + AgentConfigSnapshot models | `db/tables/eval_runs.py`, `db/tables/eval_results.py`, `db/tables/agent_config_snapshots.py`; migration `db/migrations/versions/2026-03-28_00bdc822b20e_*` |
| `P1-C1b` EvalRunRepository | `db/repositories/eval_run_repository.py` |
| `P1-C1c` EvalResultRepository | `db/repositories/eval_result_repository.py` |
| `P1-C1d` AgentConfigSnapshotRepository (get-or-create) | `db/repositories/agent_config_snapshot_repository.py` |

### C2 — Eval runner + evaluators + result storage

| Plan | Shipped in |
|------|-----------|
| `P1-C2` | `services/eval_service/_runner.py`, `services/eval_service/_evaluators.py`, `services/eval_service/evaluators/*` |

### D1 — In-process driver + user simulator

| Plan | Shipped in |
|------|-----------|
| `P1-inprocess-driver` | `services/eval_service/_inprocess_driver.py`, `services/eval_service/_user_simulator.py`, `services/eval_service/_driver_factory.py` |

Eliminated the HTTP-to-self round-trip and the `EVAL_API_BASE_URL` env-var footgun on LAT.

### E1 — Agent config snapshot on call init

| Plan | Shipped in |
|------|-----------|
| `P1-E1` | `api/routes/internal/_voice.py` fires background `upsert_agent_config_snapshot(...)` (`services/eval_service/_snapshot.py`) after fingerprinting. |

### Prompt traceability (chat parity)

| Plan | Shipped in |
|------|-----------|
| `prompt-traceability-plan.md` | `services/message_service/_implementation.py::_fingerprint_conversation` — fire-and-forget background task on `/v1/chat/` that stamps `conversations.agent_fingerprint` + `prompt_fingerprint` and upserts the snapshot. Eval runs now inherit fingerprinting automatically since they route through message_service via `InProcessDriver`. |

## What did NOT graduate (still active plans)

Kept in `docs/plans/conversation-eval/`:

- `proposal.md`, `requirements.md`, `implementation-plan.md`, `timeline.md` — umbrella design docs, still referenced.
- `fde-guide.md` — user-facing guide, not a plan.
- `phase2-audio-native-proposal.md` — Phase 2 still in progress.
- `rubric-by-scenario-type-plan.md` — not yet implemented; `judge_adapter.py::_build_judge_config()` still uses the single ordering rubric.
- `eval-context-modifier-plan.md` — phone injection shipped (PR #4092); `spec_modifier` follow-up still open (PR #4104).
- `langfuse-integration-plan.md` — drafted 2026-04-28, not started.

## Notes

- Full plan text is preserved in git history; the files are removed from `docs/plans/` to keep the plans directory focused on active and upcoming work.
- Fragile zones carried over from this work are captured in `docs/memory/short-term.md` — in particular, the `@observe` decorator structure in `agent/agent.py`.
