# Eval API Routes + Conversation Fingerprint Surfacing

**Date**: 2026-03-31
**Author**: Jacob Wang
**Status**: Implemented

## Context

The eval service (P1-C2) was shipped with background task runner, evaluators, and result storage, but had no API surface. Users couldn't trigger eval runs or retrieve results without direct DB access. Additionally, `agent_fingerprint` and `prompt_fingerprint` were stored on every voice call (P1-B1) but never exposed through the admin conversation API.

## Changes

### Eval API Routes (P1-C3)

Three new endpoints under `/v1/eval/`:

- `POST /v1/eval/run` — triggers an evaluation run for a project, returns 202 with run ID. Delegates to `create_eval_run()` which kicks off a background task.
- `GET /v1/eval/runs/{run_id}` — returns run status (pending/running/completed/failed) plus all per-scenario metric results.
- `GET /v1/eval/scorecard/{project_id}` — aggregated scorecard across recent runs with per-metric pass rates.

Request schema (`RunEvalRequest`): `project_id`, `account_id`, `driver` (http|direct), `triggered_by` (max 20 chars, matching DB column).

### Conversation Fingerprint Surfacing

Added `agent_fingerprint: str | None` and `prompt_fingerprint: str | None` to both `Conversation` and `ConversationDetail` response schemas, wired through `_builder.py`.

## Files

- `api/routes/eval/__init__.py`, `api/routes/eval/_implementation.py` — routes
- `api/schemas/eval/requests.py`, `api/schemas/eval/responses.py` — schemas
- `api/schemas/admin/conversation.py`, `api/routes/admin/_builder.py` — fingerprint fields
- `tests/api/routes/eval/test_eval_routes.py` — 8 tests

## Related

- P1-C2: `services/eval_service/_runner.py` — service layer these routes delegate to
- P1-B1: `services/agent_service/_fingerprint.py` — computes fingerprints stored on conversations
- `docs/plans/conversation-eval/implementation-plan.md` — full eval platform design
