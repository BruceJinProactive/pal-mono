# RBAC Permission System

> **Date:** 2025-12-04

## Summary

Implemented Role-Based Access Control (RBAC) with a dual-mode migration strategy. Rolled out in phases: Phase 1 added permission tables and decorators, Phase 2 added feature-flag-gated migration, and the launch flag was removed on Dec 4, 2025 (#2808) — making RBAC the sole authorization system.

## What Was Built

### Database (3 tables)

- **`permission`**: id, resource_type, action, description — defines granular permissions
- **`role_permission`**: role_id, permission_id — maps roles to permissions
- **`resource_role_assignment`**: user_id, resource_type, resource_id, role — assigns roles per resource
- Migration: `2025-11-03_312e97520412_create_rbac_tables.py`

### Authorization Service (`services/auth_service/`)

- `authorization.py` — Core permission checking logic
- `dependencies.py` — FastAPI dependency injection for auth context
- `resolution.py` — Resolves user roles/permissions from DB
- `config.py` — Auth service configuration

### Permission Decorators

Route-level decorators (`require_permission`, `require_project_permission`) applied across admin, operation, and catering routes. Some endpoints use internal checks for complex multi-resource authorization.

### Migration Timeline

1. **Nov 2, 2025**: RBAC planning and Phase 1 tasks
2. **Nov 3, 2025**: RBAC tables and models created (#2597)
3. **Nov 9, 2025**: Permission decorators added to endpoints
4. **Dec 2, 2025**: All REST APIs migrated to RBAC (#2800)
5. **Dec 4, 2025**: Launch flag removed — fully launched (#2808)
6. **Dec 9, 2025**: Dead code cleanup, UserContext simplified (#2843)

## Key Files

| Component | File |
|-----------|------|
| DB tables | `db/tables/permission.py`, `role_permission.py`, `resource_role_assignment.py` |
| Repositories | `db/repositories/permission_repository.py`, `role_permission_repository.py`, `resource_role_assignment_repository.py` |
| Auth service | `services/auth_service/authorization.py`, `dependencies.py`, `resolution.py` |
| State doc | `docs/state/auth.md` |

## Origin

Plan: `.claude/docs/auth/` (Phase 1/2 tasks, checkpoint migration — now archived)
