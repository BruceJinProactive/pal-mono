# Deprecate Checkpoint Service

**Date:** 2026-03-17

## Summary

Removed the checkpoint service and all related code. The checkpoint feature was built between October–December 2025 and has been dormant since December 4, 2025. It is being replaced by the monitoring system.

## What was removed

- **Service layer:** `services/checkpoint_service/` (5 files)
- **API routes:** All `/checkpoints/` endpoints and `/checklists/history` endpoint
- **API schemas:** `api/schemas/admin/checkpoint.py`, checkpoint-related schemas from `checklist.py` and `camera.py`
- **Repository:** `db/repositories/checkpoint_repository.py`
- **Builders:** `build_checkpoint` and `build_checkpoint_result` from `api/routes/admin/_builder.py`
- **Vision service:** `create_checkpoint` function
- **Checklist service:** `get_checklist_history` and `get_batch_checklist_history` (depended on checkpoints)

## What was preserved

- **Database tables:** `checkpoints` and `checkpoint_runs` table models remain in `db/tables/` to prevent Alembic from generating a drop-table migration. The actual tables still exist in the database.
- **Migrations:** All existing migration files left untouched.

## Lines removed

~4,893 lines across 19 files.
