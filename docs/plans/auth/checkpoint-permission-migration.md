# Checkpoint Permission Migration

## Overview
This document tracks the migration of checkpoint endpoints from internal `_check_account_access` calls to route-level `require_checkpoint_permission` decorators.

## Migration Status

### Endpoints WITH Decorators (Already Migrated)
| Route | Decorator | Permission |
|-------|-----------|------------|
| `GET /projects/{project_id}/checkpoints` | `require_project_permission` | `project.read` |
| `POST /projects/{project_id}/checkpoints` | `require_project_permission` | `project.write` |
| `GET /checklists/{checklist_id}/checkpoints` | `require_checklist_permission` | `account.read` |

### Endpoints to Migrate (checkpoint_id in path)
| Route | Function | Current Auth | Target Decorator |
|-------|----------|--------------|------------------|
| `PATCH /checkpoints/{checkpoint_id}` | `update_checkpoint` | `_check_account_access` | `require_checkpoint_permission("project.write")` |
| `DELETE /checkpoints/{checkpoint_id}` | `delete_checkpoint` | `_check_account_access` | `require_checkpoint_permission("project.write")` |
| `POST /checkpoints/{checkpoint_id}/compare` | `compare_checkpoint` | `_check_account_access` | `require_checkpoint_permission("project.write")` |
| `POST /checkpoints/{checkpoint_id}/compare-camera` | `compare_camera_checkpoint_handler` | `_check_account_access` | `require_checkpoint_permission("project.read")` |
| `GET /checkpoints/{checkpoint_id}/results` | `list_checkpoint_results_by_checkpoint` | `_check_account_access` | `require_checkpoint_permission("project.read")` |

### Endpoints That Cannot Use Simple Decorators

These endpoints have parameters that don't fit the standard `{resource_id}` path pattern:

| Route | Parameter | Issue | Current Solution |
|-------|-----------|-------|------------------|
| `POST /checkpoints/runs` | `checkpoint_id` (form) | ID is in form data, not path | Internal `_check_account_access` via checkpoint lookup |
| `GET /checkpoints/results` | `project_id` (query) | Uses project_id not checkpoint_id | Internal `_check_account_access` via project lookup |
| `GET /checkpoints/runs/{run_id}` | `run_id` | Need run -> checkpoint -> project chain | Internal `_check_account_access` via run lookup |
| `PATCH /checkpoints/runs/{run_id}/review` | `run_id` | Need run -> checkpoint -> project chain | Internal `_check_account_access` via run lookup |
| `DELETE /checkpoints/runs/{run_id}` | `run_id` | Need run -> checkpoint -> project chain | Internal `_check_account_access` via run lookup |
| `DELETE /checkpoints/submissions/{submission_id}/runs` | `submission_id` | Need submission -> checkpoint -> project chain | Internal `_check_account_access` via first run lookup |

### Why These Can't Be Migrated

1. **Form-based parameters**: The `require_*_permission` decorators expect the resource ID to be a path parameter. Form data parameters require custom handling.

2. **Indirect resource references**: Endpoints using `run_id` or `submission_id` need to traverse the resource hierarchy (run -> checkpoint -> project -> account) which requires database lookups that can't be done in a simple decorator.

3. **Query parameters**: The `project_id` query parameter requires different handling than path parameters.

### Possible Future Solutions

1. **Create specialized decorators**:
   - `require_checkpoint_run_permission` - accepts `run_id`, looks up checkpoint internally
   - `require_checkpoint_submission_permission` - accepts `submission_id`, looks up first run's checkpoint

2. **Generic resource lookup decorator**:
   - A more flexible decorator that accepts a lookup function to resolve the resource chain

3. **Keep internal checks**: For complex cases, the internal `_check_account_access` pattern is acceptable and explicit.

## Implementation Files

- `db/repositories/resource_role_assignment_repository.py` - Add `CHECKPOINT` to `ResourceType` enum
- `services/auth_service/config.py` - Add `"checkpoints": "projects"` to `RESOURCE_HIERARCHY`
- `services/auth_service/dependencies.py` - Add `require_checkpoint_permission` function
- `services/auth_service/__init__.py` - Export `require_checkpoint_permission`
- `api/routes/operation/__init__.py` - Update route decorators
- `api/routes/operation/_checkpoint.py` - Remove redundant `_check_account_access` calls
