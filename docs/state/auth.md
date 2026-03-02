# Endpoints That Cannot Use Simple Permission Decorators

> **Last updated:** 2025-03-01

## Overview
This document catalogs all API endpoints that use internal authorization checks (`_check_*_access` functions) instead of route-level permission decorators. These endpoints have patterns that make simple decorator-based authorization impractical.

## Why These Can't Use Decorators

1. **Non-path parameters**: The resource ID is in form data, query params, or request body instead of the URL path
2. **Indirect resource references**: Need to traverse resource hierarchy (e.g., run_id -> checkpoint -> project)
3. **Dynamic resource types**: Endpoint accepts multiple resource types via a parameter
4. **Async session issues**: Some endpoints use AsyncSession but permission checking requires sync Session
5. **Admin-only operations**: Some endpoints require admin role, not resource-based permissions

---

## Checkpoint Endpoints (`api/routes/operation/_checkpoint.py`)

### Endpoints with run_id (need checkpoint lookup)

| Route | Parameter | Issue |
|-------|-----------|-------|
| `GET /checkpoints/runs/{run_id}` | `run_id` | Need run -> checkpoint -> project chain |
| `PATCH /checkpoints/runs/{run_id}/review` | `run_id` | Need run -> checkpoint -> project chain |
| `DELETE /checkpoints/runs/{run_id}` | `run_id` | Need run -> checkpoint -> project chain |

**Current solution**: Internal `_check_account_access` after looking up the run and checkpoint

**Potential decorator**: `require_checkpoint_run_permission(run_id)` that internally does:
```python
run = get_checkpoint_result(session, run_id)
checkpoint = get_checkpoint(session, run.checkpoint_id)
# then check permission on checkpoint
```

### Endpoints with submission_id

| Route | Parameter | Issue |
|-------|-----------|-------|
| `DELETE /checkpoints/submissions/{submission_id}/runs` | `submission_id` | Need submission -> first_run -> checkpoint chain |

**Current solution**: Get all runs for submission, use first run's checkpoint for auth

### Endpoints with form-based checkpoint_id

| Route | Parameter | Issue |
|-------|-----------|-------|
| `POST /checkpoints/runs` | `checkpoint_id` (form) | ID is in form data, not path |

**Current solution**: Internal `_check_account_access` after extracting from form

### Endpoints with query-based project_id

| Route | Parameter | Issue |
|-------|-----------|-------|
| `GET /checkpoints/results` | `project_id` (query) | Uses query param not path |

**Current solution**: Internal `_check_account_access` via project lookup

---

## Checklist Endpoints (`api/routes/operation/_checklist.py`)

### Batch history endpoint

| Route | Parameter | Issue |
|-------|-----------|-------|
| `GET /checklists/history` | `checklist_ids` (query array) | Multiple checklist IDs in query |

**Current solution**: Internal `_authorize_checklist_access` for each checklist in the array

---

## Voice Config Endpoints (`api/routes/admin/_voice_config.py`)

### Endpoints with voice_config_id (need project lookup)

| Route | Parameter | Issue |
|-------|-----------|-------|
| `GET /voice-configs/{voice_config_id}` | `voice_config_id` | Need voice_config -> project chain |
| `PATCH /voice-configs/{voice_config_id}` | `voice_config_id` | Need voice_config -> project chain |
| `DELETE /voice-configs/{voice_config_id}` | `voice_config_id` | Need voice_config -> project chain |
| `POST /voice-configs` | `project_id` (body) | ID is in request body |

**Current solution**: Internal `_check_project_access` after looking up voice config and project

**Additional issue**: Uses AsyncSession but `check_permission` needs sync Session. Current workaround creates a new sync session.

### Batch update endpoint (admin-only)

| Route | Parameter | Issue |
|-------|-----------|-------|
| `POST /voice-configs/batch` | Multiple project_ids | Admin-only batch operation |

**Current solution**: `authorize_admin(context)` - admin role check only

---

## Knowledge Endpoints (`api/routes/admin/_knowledge.py`)

### Dynamic resource type endpoints

| Route | Parameter | Issue |
|-------|-----------|-------|
| `GET /knowledge/{resource}/{resource_id}/files` | `resource` (path enum) | Resource type is dynamic (projects or agents) |
| `POST /knowledge/{resource}/{resource_id}/files` | `resource` (path enum) | Resource type is dynamic |
| `DELETE /knowledge/{resource}/{resource_id}/files/{filename}` | `resource` (path enum) | Resource type is dynamic |

**Current solution**: `get_and_authorize()` helper that handles both project and agent types with internal `_check_account_access`

**Why decorator won't work**: Would need different decorators based on resource type enum value

### Admin-only knowledge endpoints

| Route | Parameter | Issue |
|-------|-----------|-------|
| `POST /knowledge/update-agent-kb` | N/A | Admin-only operation |
| `DELETE /knowledge/namespace` | N/A | Admin-only operation |
| `POST /knowledge/namespace/query` | N/A | Admin-only operation |

**Current solution**: `authorize_admin(context)` - admin role check only

---

## Feedback Endpoints (`api/routes/admin/_feedback.py`)

### Create feedback (message lookup)

| Route | Parameter | Issue |
|-------|-----------|-------|
| `POST /feedbacks` | `message_id` (body) | Need message -> conversation -> user -> account chain |

**Current solution**: Internal `_check_account_access` after traversing the chain

---

## Recommendations

### Keep Internal Checks For:
1. **Multi-resource lookups**: When you need to traverse 3+ resources
2. **Dynamic resource types**: When the resource type varies by parameter
3. **Admin-only operations**: Use `authorize_admin()` directly
4. **Batch operations**: Multiple resource IDs in one request
5. **Non-path parameters**: Form data, query params, request body

### Create Decorators For:
1. **Simple path-based lookups**: Single resource_id in path with 1-2 level hierarchy
2. **Consistent patterns**: Multiple endpoints using same parameter name

### Potential New Decorators (Future Work):
- `require_checkpoint_run_permission(run_id)` - for run-based endpoints
- `require_voice_config_permission(voice_config_id)` - for voice config endpoints
- `require_message_permission(message_id)` - for message-based endpoints
