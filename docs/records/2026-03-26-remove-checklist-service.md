# Remove Checklist Service

**Date:** 2026-03-26

## Summary

Removed the remaining checklist service and all related code. The checklist feature has been fully replaced by the routine system. This completes the deprecation started in the earlier checkpoint service removal (2026-03-17).

## What was removed

- **Service layer:** `services/checklist_service/` (`__init__.py`, `_implementation.py`)
- **API routes:** 5 checklist endpoints from `api/routes/operation/` (CRUD for checklists)
- **API schemas:** `api/schemas/admin/checklist.py`
- **Repository:** `db/repositories/checklist_repository.py`
- **Auth references:** `require_checklist_permission`, `"checklists"` from `VALID_RESOURCE_TYPES`, `RESOURCE_HIERARCHY`, and resolution logic
- **Tests:** Checklist-specific tests in auth service test suite

## What was preserved

- **Database tables:** `checklists`, `checkpoints`, and `checkpoint_runs` table models remain in `db/tables/` to prevent Alembic from generating drop-table migrations.
- **Database table exports:** Kept in `db/tables/__init__.py` for the same reason.
- **Migrations:** All existing migration files left untouched.
- **RBAC resource type enum:** `CHECKLIST` in `resource_role_assignment_repository.py` preserved for existing DB data.
- **Routine comparison mode:** `"checklist"` literal in `api/schemas/operations/routine.py` is a routine feature, not the checklist service.

## Lines removed

~1,004 lines across 14 files.
