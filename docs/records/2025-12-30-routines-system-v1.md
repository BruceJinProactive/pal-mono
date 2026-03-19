# Restaurant Routines System V1

> **Date:** 2025-12-30

## Summary

Implemented a 3-tier routines system for managing recurring restaurant operations (opening/closing procedures, food safety compliance, cleaning tasks) with staff accountability, evidence collection, and AI-powered photo verification.

## What Was Built

### Tier 1: Standard (what to do)

- **`routines`** table: id, project_id, name, category, description, is_active, created_at, updated_at
- **`routine_items`** table: id, routine_id, name, description, input_type, is_required, position, reference_image_url, ai_rules (JSONB), created_at, updated_at

### Tier 2: Workflow (when to do it)

- **`routine_schedules`** table: id, routine_id, frequency, start_time, end_time, timezone, days_of_week, is_active, created_at, updated_at
- **`routine_executions`** table: id, schedule_id, routine_id, scheduled_start, scheduled_end, status, assigned_user_id, created_at, updated_at
- EventBridge integration for automated execution generation

### Tier 3: Evidence (proof of completion)

- **`routine_submissions`** table: id, execution_id, status, submitted_by, submitted_at, reviewed_by, review_notes, created_at, updated_at
- **`routine_item_responses`** table: id, submission_id, routine_item_id, status, image_url, ai_result (JSONB), ai_passed, notes, created_at, updated_at
- AI/LLM evaluation via `routine_submission_service/_llm.py` and `vision_service/`

### Services (4 service modules)

| Service | Purpose |
|---------|---------|
| `routine_service/` | Routine + item CRUD, template management |
| `routine_schedule_service/` | Schedule CRUD, execution auto-generation |
| `routine_execution_service/` | Execution lifecycle, status transitions |
| `routine_submission_service/` | Submission workflow, AI photo evaluation via _llm.py |

### Repositories (4)

`routine_repository`, `routine_schedule_repository`, `routine_execution_repository`, `routine_submission_repository` — all async.

### API Surface

Full CRUD in `api/routes/operation/_routines.py` covering routines, items, schedules, executions, and submissions with photo upload and AI verification.

## What Was Deferred

- **Tier 4: Escalation (Alerts)** — overdue/missed/flagged alerts described in PRD but not fully wired as autonomous alert routing. Covered by separate operations notifications PRD.
- Corporate template system (copy-on-customize across locations)
- Input types beyond photo (checkbox, number, text, multi-select)

## Key Files

| Component | File |
|-----------|------|
| DB tables | `db/tables/routines.py`, `routine_items.py`, `routine_schedules.py`, `routine_executions.py`, `routine_submissions.py`, `routine_item_responses.py` |
| API routes | `api/routes/operation/_routines.py` |
| Services | `services/routine_service/`, `routine_schedule_service/`, `routine_execution_service/`, `routine_submission_service/` |
| AI evaluation | `services/routine_submission_service/_llm.py`, `services/vision_service/` |
| EventBridge | `events/_eventbridge.py`, `events/schema.py` |

## Origin

Plan: `docs/plans/operations/routines/` (PRD + TDD, now archived)
