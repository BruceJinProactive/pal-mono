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

## Database tables dropped (PAL-9360)

- **Tables:** `checklists`, `checkpoints`, `checkpoint_runs` dropped via Alembic migration `49a119d0677f`
- **Table models:** `db/tables/checklists.py`, `db/tables/checkpoints.py`, `db/tables/checkpoint_runs.py` deleted
- **Exports:** Removed from `db/tables/__init__.py`
- **Downgrade:** Migration includes full table and `checkstatus` enum type recreation
- **`checkstatus` enum type:** Dropped in the same migration.

## What was preserved

- **Migrations:** All existing migration files left untouched.
- **Python `CheckStatus` enum:** Kept in `db/tables/types.py` — to be removed in follow-up PR with `CHECKLIST` from `ResourceType`.
- **RBAC resource type enum:** `CHECKLIST` in `resource_role_assignment_repository.py` — to be removed in follow-up PR.
- **Routine comparison mode:** `"checklist"` literal in `api/schemas/operations/routine.py` is a routine feature, not the checklist service.
