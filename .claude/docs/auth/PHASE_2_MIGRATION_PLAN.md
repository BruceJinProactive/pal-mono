# Phase 2 Migration Plan: Feature Flag + Endpoint Migration to RBAC

## Overview

Implement feature flag infrastructure and migrate routes to use RBAC `Depends()` pattern.

**Scope**: Core CRUD endpoints only (42 endpoints: Accounts, Projects, Agents, Team)
**Approach**: Simple environment switch (`USE_RBAC=true/false`)
**API Compatibility**: Adapt RBAC dependencies to existing path parameter names (no breaking changes)

---

## Current State

| Component | Status |
|-----------|--------|
| RBAC Models & Repositories | ✅ Done (Phase 1) |
| Authorization functions (`check_permission()`) | ✅ Done |
| Permission config (`ROLE_PERMISSIONS`) | ✅ Done |
| RBAC Dependencies (`require_*_permission()`) | ✅ Done |
| Feature Flag Infrastructure | ❌ Missing |
| Endpoint Migration | ❌ Not started |

---

## Files to Modify

| File | Changes |
|------|---------|
| `services/auth_service/feature_flags.py` | **NEW** - Feature flag service |
| `services/auth_service/dependencies.py` | Rename param `account_identifier` → `account_name` + add dual-mode |
| `services/auth_service/__init__.py` | Export feature flag |
| `api/routes/admin/__init__.py` | Use RBAC `Depends()` in route decorators |
| `api/routes/admin/_account.py` | Remove `authorize_user_account()` calls |
| `api/routes/admin/_projects.py` | Remove `authorize_user_account()` calls |
| `api/routes/admin/_agent.py` | Remove `authorize_user_account()` calls |
| `api/routes/admin/_team.py` | Remove `authorize_user_account()` calls |

---

## Implementation Steps

### Step 1: Create Feature Flag Service

**File**: `services/auth_service/feature_flags.py`

```python
import os
from utils.log import logger

def is_rbac_enabled() -> bool:
    """Check if RBAC is enabled via environment variable."""
    return os.environ.get("USE_RBAC", "false").lower() == "true"
```

### Step 2: Rename Parameter in RBAC Dependencies (FastAPI wiring)

**File**: `services/auth_service/dependencies.py`

Rename `account_identifier` → `account_name` so FastAPI can match the route's path parameter.

> **Note**: The parameter already accepts both account names AND UUIDs internally - this is just a rename for FastAPI parameter matching, not a functionality change.

```python
# BEFORE (line 193-196)
async def dependency(
    account_identifier: str,  # FastAPI can't match to route's {account_name}
    ...

# AFTER
async def dependency(
    account_name: str,  # Now matches route's {account_name} path parameter
    ...
```

Also update variable references:
- Line 210: `f"accounts/{account_identifier}"` → `f"accounts/{account_name}"`
- Update docstring example (line 180): `{account_identifier}` → `{account_name}`

### Step 3: Add Dual-Mode Fallback to Dependencies

**File**: `services/auth_service/dependencies.py`

Modify `require_account_permission()` to support both legacy and RBAC modes:

```python
from services.auth_service.feature_flags import is_rbac_enabled
from services.auth_types import UserRole

async def dependency(
    account_name: str,
    current_user: UserContext = Depends(auth_dependency),
    session: Session = Depends(db.get_db),
) -> UserContext:
    # Extract user_id from UserContext
    try:
        user_id = UUID(current_user.username)
    except (ValueError, AttributeError) as err:
        raise HTTPException(status_code=403, detail="Invalid user credentials") from err

    # Legacy mode: fall back to account membership check
    if not is_rbac_enabled():
        if account_name not in current_user.account_names:
            if current_user.role != UserRole.Admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User does not have permission for the requested account",
                )
        return current_user

    # RBAC mode: check permission via RBAC system
    has_permission = check_permission(
        user_id=user_id,
        resource_id=f"accounts/{account_name}",
        permission_name=permission,
        session=session,
    )

    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {permission}",
        )

    return current_user
```

Apply same pattern to:

- `require_project_permission()`
- `require_agent_permission()`

### Step 4: Update Routes to Use RBAC Depends()

**File**: `api/routes/admin/__init__.py`

```python
# Add imports
from services.auth_service import require_account_permission

# BEFORE
@admin_router.get("/accounts/{account_name}")
def get_account(
    account_name: str,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Account:
    return _account.get_account(account_name, context, session)

# AFTER
@admin_router.get("/accounts/{account_name}")
def get_account(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> Account:
    return _account.get_account(account_name, context, session)
```

### Step 5: Remove Authorization Calls from Implementation Files

**File**: `api/routes/admin/_account.py`

```python
# BEFORE
def get_account(account_name: str, context: UserContext, session: Session):
    authorize_user_account(context, account_name)  # Remove this line
    account = account_service.get_account(session, account_name)
    ...

# AFTER (authorization already done in Depends())
def get_account(account_name: str, context: UserContext, session: Session):
    account = account_service.get_account(session, account_name)
    ...
```

---

## Endpoint Permission Mapping

### Accounts (18 endpoints)

| Endpoint | Method | Permission |
|----------|--------|------------|
| `/accounts` | GET | `account.read` |
| `/accounts/{account_name}` | GET | `account.read` |
| `/accounts/{account_name}` | PATCH | `account.write` |
| `/accounts/{account_name}` | DELETE | `account.write` |
| `/accounts/{account_name}/close` | POST | `account.write` |
| `/accounts/{account_name}/agents` | GET | `account.read` |
| `/accounts/{account_name}/projects` | GET | `account.read` |
| `/accounts/{account_name}/stat` | GET | `account.read` |
| `/accounts/{account_name}/status` | GET | `account.read` |
| `/accounts/{account_name}/terms_status` | GET | `account.read` |
| `/accounts/{account_name}/initiate_terms_signing` | POST | `account.write` |
| `/accounts/{account_name}/complete_terms_signing` | POST | `account.write` |
| `/accounts/{account_name}/accept_terms` | PUT | `account.write` |

### Projects (15 endpoints)

| Endpoint | Method | Permission |
|----------|--------|------------|
| `/projects` | PUT | `project.create` |
| `/projects/{project_id}` | GET | `project.read` |
| `/projects/{project_id}` | PATCH | `project.write` |
| `/projects/{project_id}` | DELETE | `project.delete` |
| `/projects/{project_id}/integrations` | GET | `project.read` |
| `/projects/{project_id}/integrations` | PUT | `project.write` |
| `/projects/{project_id}/integrations/{id}` | GET | `project.read` |
| `/projects/{project_id}/integrations/{id}` | PATCH | `project.write` |
| `/projects/{project_id}/integrations/{id}` | DELETE | `project.write` |
| `/projects/{project_id}/voice_configs` | GET | `project.read` |

### Agents (9 endpoints)

| Endpoint | Method | Permission |
|----------|--------|------------|
| `/agents` | PUT | `agent.create` |
| `/agents/{agent_id}` | GET | `agent.read` |
| `/agents/{agent_id}` | PATCH | `agent.write` |
| `/agents/{agent_id}` | DELETE | `agent.delete` |
| `/agents/{agent_id}/projects` | GET | `agent.read` |
| `/agents/{agent_id}/agent_config` | GET | `agent.read` |

### Team (9 endpoints)

| Endpoint | Method | Permission |
|----------|--------|------------|
| `/accounts/{account_name}/team` | GET | `account.read` |
| `/accounts/{account_name}/team/invite` | POST | `account.team_manage` |
| `/accounts/{account_name}/team/{user_email}` | PATCH | `account.team_manage` |
| `/accounts/{account_name}/team/{user_email}` | DELETE | `account.team_manage` |
| `/accounts/{account_name}/team/invitations/{id}/resend` | POST | `account.team_manage` |

---

## Testing Strategy

1. **Unit tests**: Test dual-mode functions with flag on/off
2. **Integration tests**: Verify endpoints work with both modes
3. **Manual testing**:
   - `USE_RBAC=false` - Legacy behavior (default)
   - `USE_RBAC=true` - RBAC behavior

---

## Rollout Plan

1. Deploy with `USE_RBAC=false` (default)
2. Test in staging with `USE_RBAC=true`
3. Enable in production when ready
4. Monitor for issues
5. Future: Remove legacy code path after stable period

---

## Estimated Effort

| Task | Time |
|------|------|
| Feature flag service | 15 min |
| Rename dependency parameter | 15 min |
| Add dual-mode fallback to dependencies | 30 min |
| Update routes (accounts) | 1 hour |
| Update routes (projects) | 45 min |
| Update routes (agents) | 30 min |
| Update routes (team) | 30 min |
| Remove authorize_user_account() calls | 30 min |
| Testing | 2 hours |
| **Total** | ~6 hours |
