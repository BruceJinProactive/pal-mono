# Phase 2: Authorization Backend - Detailed Task Breakdown

**Timeline**: Weeks 3-4

**Goal**: Implement core authorization framework with permission checking, decorators, and API endpoint protection

**Related**: [TDD_RBAC.md](./TDD_RBAC.md), [PHASE_1_TASKS.md](./PHASE_1_TASKS.md)

---

## Prerequisites

Before starting Phase 2, ensure Phase 1 is complete:

- [x] All database tables created and migrated
- [x] SQLAlchemy models implemented
- [x] Repository layer complete with tests
- [x] Cache infrastructure set up (cachetools)
- [x] Seed data populated (permissions, role mappings)
- [x] Unit tests passing for all models and repositories

---

## Design Context

### V1 Scope: Account-Level Only

Phase 2 implements **account-level authorization** only. This means:

- ✅ Users have roles (Owner, Manager, Viewer) on their account
- ✅ Permission checks verify account-level role
- ❌ No project-specific or agent-specific role overrides (V2 feature)

**Benefit**: Simpler implementation, faster delivery, same data model ready for V2

### Permission Resolution Flow

```
1. Extract user_id, account_id from request
2. Get user's role on account (cached, 5 min TTL)
3. Get permissions for role (cached, 15 min TTL)
4. Check if required permission exists in set
5. Allow or Deny (403 Forbidden)
```

### Migration Strategy: Dual-Mode Authorization

Phase 2 implements **dual-mode authorization** to enable gradual migration from legacy to RBAC:

```
┌─────────────────────────────────────────────────────────┐
│                   PermissionChecker                     │
│                                                         │
│   feature_flag.is_rbac_enabled(account_id)?            │
│                                                         │
│         ┌─────────────────┬─────────────────┐          │
│         │      YES        │       NO        │          │
│         ▼                 ▼                 │          │
│   _check_rbac()      _check_legacy()       │          │
│         │                 │                 │          │
│         └────────┬────────┘                 │          │
│                  ▼                          │          │
│            Allow / Deny                     │          │
└─────────────────────────────────────────────────────────┘
```

**Key Benefits**:
- ✅ Endpoints remain unchanged during migration
- ✅ Feature flag controls rollout (OFF → INTERNAL → BETA → 10% → 25% → 50% → ON)
- ✅ Instant rollback via flag (no code deployment)
- ✅ Both systems coexist safely
- ✅ Clean cutover: After 3 months at 100%, remove legacy code (Phase 5, Task 5.20)

**Migration Timeline**:
1. **Phase 2 Complete**: Dual-mode ready, flag=OFF (100% legacy)
2. **Phase 5 Start**: flag=INTERNAL (Palona accounts use RBAC)
3. **Phase 5 Rollout**: Gradual 10% → 25% → 50% → 100% over 2 weeks
4. **+3 Months Stable**: Remove legacy code, simplify to single path

---

## Task Categories

1. [Core Authorization Functions](#core-authorization-functions) (Tasks 2.1-2.4)
2. [Feature Flag Infrastructure](#task-245-feature-flag-infrastructure-for-gradual-migration) (Task 2.4.5)
3. [Permission Decorators](#permission-decorators) (Tasks 2.5-2.6)
4. [FastAPI Dependencies](#fastapi-dependencies) (Task 2.7)
5. [Endpoint Migration](#endpoint-migration) (Tasks 2.8-2.12)
6. [Testing](#testing) (Tasks 2.13-2.16)

---

## Core Authorization Functions

### Task 2.1: Implement get_user_role_on_account()

**Priority**: High

**Estimated Time**: 2 hours

**Dependencies**: Phase 1 repositories complete

**File Location**: `src/auth/rbac/authorization.py`

**Description**: Implement cached function to get user's role on account (V1: account-level only).

**Requirements**:

**Function: get_user_role_on_account(user_id, account_id, db_session) → Optional[UserRole]**
- Purpose: Get user's role on account (V1 - account-level only)
- Cache: TTLCache with 5-minute TTL, use hashkey(user_id, account_id)
- Returns: UserRole if user has active membership and role, None otherwise
- Algorithm:
  1. Verify user is active member (AccountUserRepository.is_member)
  2. If not member → return None
  3. Get role from resource_role_assignments (resource_type='account', resource_id=account_id)
  4. Return role or None
- Error Handling: Returns None instead of raising exceptions (fail closed)
- Logging: Debug messages for membership failures and missing roles

**Validation Steps**:

1. Test with user who has account membership and role → returns role
2. Test with user who has membership but no role → returns None
3. Test with user who is not a member → returns None
4. Test with deactivated user → returns None
5. Verify caching works (check cache hit on second call)

---

### Task 2.2: Implement get_role_permissions()

**Priority**: High

**Estimated Time**: 1.5 hours

**Dependencies**: Phase 1 repositories complete

**File Location**: `src/auth/rbac/authorization.py` (add to existing)

**Description**: Implement cached function to get all permissions for a role.

**Requirements**:

**Function: get_role_permissions(role, db_session) → Set[str]**
- Purpose: Get all permissions for a role (cached)
- Cache: TTLCache with 15-minute TTL, use hashkey(role.value)
- Returns: Set of permission names (e.g., {"project.create", "agent.read"})
- Algorithm:
  1. If role == OWNER → return {"*"} (wildcard for all permissions)
  2. Query RolePermissionRepository.get_permission_names_for_role(role)
  3. Return set of permission names
- Logging: Debug messages showing role, permission count, and permission names

**Validation Steps**:

1. Test Owner role → returns `{"*"}`
2. Test Manager role → returns correct permission set (no billing, no team_manage)
3. Test Viewer role → returns read-only permissions
4. Verify caching works (second call doesn't hit database)
5. Test cache invalidation after role_permissions change

---

### Task 2.3: Implement check_permission()

**Priority**: High

**Estimated Time**: 1.5 hours

**Dependencies**: Tasks 2.1, 2.2

**File Location**: `src/auth/rbac/authorization.py` (add to existing)

**Description**: Implement main permission checking function combining role lookup and permission verification.

**Requirements**:

**Function: check_permission(user_id, account_id, permission_name, db_session) → bool**
- Purpose: Check if user has permission on account (V1 - account-level only)
- Returns: True if user has permission, False otherwise
- Algorithm:
  1. Get user's role on account via get_user_role_on_account() (cached)
  2. If no role → log denial, return False
  3. Get permissions for role via get_role_permissions() (cached)
  4. Check if permission_name in permissions OR "*" in permissions (wildcard)
  5. Log result (granted/denied with role info)
  6. Return boolean result
- Error Handling: Wrap in try/except, return False on any exception (fail closed)
- Logging: Debug messages for permission granted/denied, error messages for exceptions
- Performance: Leverages cached lookups, target <50ms p99, <10ms with cache hits

**Validation Steps**:

1. Test with Owner → all permissions granted
2. Test with Manager → appropriate permissions granted/denied
3. Test with Viewer → only read permissions granted
4. Test with non-member → all permissions denied
5. Test with invalid IDs → returns False (fail closed)
6. Test performance: <50ms p99 (should be <10ms with cache hits)

---

### Task 2.4: Create Authorization Module Package

**Priority**: Medium

**Estimated Time**: 30 minutes

**Dependencies**: Tasks 2.1-2.3

**File Location**: `src/auth/rbac/__init__.py`

**Description**: Create package initialization for RBAC authorization module.

**Requirements**:

- Import and re-export: get_user_role_on_account, get_role_permissions, check_permission
- Define __all__ list with all exported functions
- Docstring: "RBAC authorization package."

**Validation**: Import from package works (e.g., `from src.auth.rbac import check_permission`)

---

### Task 2.4.5: Feature Flag Infrastructure for Gradual Migration

**Priority**: High

**Estimated Time**: 3 hours

**Dependencies**: Tasks 2.1-2.4

**File Location**: `src/auth/rbac/feature_flags.py`

**Description**: Set up feature flag infrastructure to support gradual migration from legacy authorization to RBAC. This enables dual-mode operation where both legacy and RBAC systems coexist during rollout.

**Requirements**:

**Enum: RBACFeatureFlag (str, Enum)**
- Values: OFF, INTERNAL, BETA, ROLLOUT_10, ROLLOUT_25, ROLLOUT_50, ON
- Purpose: Define possible feature flag states for gradual rollout

**Class: FeatureFlagService**
- Purpose: Service for checking RBAC feature flags
- Constructor __init__():
  - Load RBAC_FEATURE_FLAG from environment (default: OFF)
  - Load beta account IDs from RBAC_BETA_ACCOUNTS (comma-separated)
  - Calculate rollout_percentage based on flag value
  - Log initialization
- Method _load_beta_accounts() → Set[str]:
  - Parse RBAC_BETA_ACCOUNTS environment variable
  - Return set of account IDs
- Method _get_rollout_percentage() → int:
  - Extract percentage from ROLLOUT_10/25/50 flags
  - Return 0 for OFF, 100 for ON/INTERNAL/BETA
- Method is_rbac_enabled(account_id, is_internal) → bool:
  - Purpose: Check if RBAC is enabled for specific account
  - Algorithm:
    1. If flag=OFF → return False
    2. If flag=ON → return True
    3. If flag=INTERNAL → return is_internal
    4. If flag=BETA → return is_internal OR account_id in beta_accounts
    5. If percentage-based → use consistent hash (account_id % 100 < percentage)
  - Consistent hashing ensures same account always gets same result
  - Log debug info for percentage-based decisions

**Global Singleton**: feature_flags = FeatureFlagService()

**Environment Variables**:
- RBAC_FEATURE_FLAG: off (default), internal, beta, 10, 25, 50, on
- RBAC_BETA_ACCOUNTS: Comma-separated list of beta test account IDs

**Migration Timeline**:
```
Phase 1 Complete → flag=OFF (legacy only)
Phase 2 Complete → flag=OFF (dual-mode ready, not activated)
Phase 5 Start → flag=INTERNAL (Palona internal accounts)
         Day 3 → flag=BETA (beta customers)
         Day 6 → flag=10 (10% rollout)
         Day 9 → flag=25 (25% rollout)
        Day 12 → flag=50 (50% rollout)
        Day 15 → flag=ON (100% rollout)
   +3 months → Remove legacy code (see Phase 5, Task 5.20)
```

**Validation Steps**:

1. Test with flag=OFF → all accounts use legacy
2. Test with flag=INTERNAL → only internal accounts use RBAC
3. Test with flag=BETA → internal + beta accounts use RBAC
4. Test with flag=10 → ~10% of accounts use RBAC (consistent hash)
5. Test with flag=ON → all accounts use RBAC
6. Verify same account always gets same result (consistent hashing)

---

## Permission Decorators

### Task 2.5: Create PermissionChecker Dependency (Dual-Mode)

**Priority**: High

**Estimated Time**: 3 hours

**Dependencies**: Task 2.3, Task 2.4.5 (Feature Flags)

**File Location**: `src/auth/rbac/dependencies.py`

**Description**: Create FastAPI dependency for permission checking with **dual-mode support**. Internally checks feature flag to use either RBAC or legacy authorization, keeping endpoint code clean.

**Requirements**:

**Class: PermissionChecker**
- Purpose: FastAPI dependency for dual-mode permission checking (RBAC or legacy)
- Constructor __init__(required_permission: str):
  - Store required_permission for RBAC mode
- Method __call__(account_id, current_user, db) → User:
  - Purpose: Check permission using RBAC or legacy based on feature flag
  - Algorithm:
    1. Check if RBAC enabled via feature_flags.is_rbac_enabled(account_id, is_internal)
    2. Log which mode is being used (RBAC or legacy)
    3. If RBAC enabled → call _check_rbac_permission()
    4. Else → call _check_legacy_permission()
    5. If denied → raise HTTPException 403 with permission details
    6. If granted → log success, return current_user
  - Returns: User object if permission granted
  - Raises: HTTPException 403 with error details {error, message, required_permission}
- Method _check_rbac_permission(user, account_id, db_session) → bool:
  - Call check_permission(user.id, account_id, self.required_permission, db_session)
  - Return boolean result
- Method _check_legacy_permission(user, account_id, db_session) → bool:
  - Purpose: Legacy authorization logic
  - Algorithm:
    1. If user.role == "Admin" → return True (admin bypass)
    2. If user.role == "AccountManager" → query UserAccount to check membership
    3. Else → return False (regular users have no admin access)
  - Note: These imports/logic will be removed in Phase 5 Task 5.20
  - Returns: Boolean indicating access

**Function: require_permission(user_id, account_id, permission, db_session) → None**
- Purpose: Programmatic permission check (not as dependency)
- Algorithm:
  1. Call check_permission(user_id, account_id, permission, db_session)
  2. If False → raise HTTPException 403 with permission details
- Raises: HTTPException 403 if permission denied

**Usage Example**:
```
@router.post("/projects")
async def create_project(
    account_id: UUID,
    current_user: Annotated[User, Depends(PermissionChecker("project.create"))],
    db: Session = Depends(get_db)
):
    # Permission already checked (RBAC or legacy depending on flag)
    pass
```

**Validation Steps**:

#### RBAC Mode Testing (flag=ON):
1. Test with Owner role → all permissions granted
2. Test with Manager role → appropriate permissions granted/denied
3. Test with Viewer role → only read permissions granted
4. Test with non-member → 403 denied
5. Verify RBAC check_permission() is called (not legacy)

#### Legacy Mode Testing (flag=OFF):
1. Test with Admin user → all permissions granted (admin bypass)
2. Test with AccountManager (member) → granted
3. Test with AccountManager (non-member) → 403 denied
4. Test with regular User → 403 denied
5. Verify legacy check is used (not RBAC)

#### Dual-Mode Testing:
1. Test flag=INTERNAL with internal account → uses RBAC
2. Test flag=INTERNAL with non-internal account → uses legacy
3. Test flag=BETA with beta account → uses RBAC
4. Test flag=10 with 10% rollout → consistent per account
5. Test mode transition: same account should always get same result

#### General:
1. Test logging shows correct mode (RBAC or legacy)
2. Test error messages include required permission
3. Test with multiple concurrent requests (thread safety)
4. Verify performance: <50ms p99 for permission checks

---

### Task 2.6: Create Admin-Only Checker

**Priority**: Medium

**Estimated Time**: 1 hour

**Dependencies**: Task 2.5

**File Location**: `src/auth/rbac/dependencies.py` (add to existing)

**Description**: Create dependency for admin-only endpoints (Palona internal staff).

**Requirements**:

**Class: AdminOnlyChecker**
- Purpose: FastAPI dependency requiring Palona admin role
- Method __call__(current_user) → User:
  - Check if current_user.is_admin is True
  - If not admin → raise HTTPException 403 with {error: "admin_required", message}
  - If admin → return current_user
- Note: Preserves existing admin functionality for Palona internal staff (no RBAC, bypass all checks)

**Usage Example**:
```
@router.get("/admin/debug")
async def debug_endpoint(
    current_user: Annotated[User, Depends(AdminOnlyChecker())]
):
    # Only Palona admins can access
    pass
```

**Validation Steps**:

1. Test with Admin user → success
2. Test with AccountManager user → 403
3. Test endpoint access control

---

## FastAPI Dependencies

### Task 2.7: Create Account Context Dependency

**Priority**: High

**Estimated Time**: 1.5 hours

**Dependencies**: Task 2.5

**File Location**: `src/auth/rbac/dependencies.py` (add to existing)

**Description**: Create dependency that validates account access and provides account context.

**Requirements**:

**Class: AccountContext**
- Purpose: Context object containing account and user's role
- Constructor __init__(account, user, role):
  - Store account (Account object), user (User object), role (UserRole)
- Property account_id → UUID:
  - Return self.account.id
- Property user_id → UUID:
  - Return self.user.id

**Function: get_account_context(account_id, current_user, db) → AccountContext**
- Purpose: Get account context with user's role, verify access
- Algorithm:
  1. Query AccountRepository.get_by_id(account_id)
  2. If not found → raise HTTPException 404
  3. Get user's role via get_user_role_on_account(current_user.id, account_id, db)
  4. If no role → raise HTTPException 403
  5. Return AccountContext(account, current_user, role)
- Returns: AccountContext with account, user, and role
- Raises: HTTPException 404 if account not found, 403 if no access

**Validation Steps**:

1. Test with valid account and access → returns context
2. Test with non-existent account → 404
3. Test with no access → 403
4. Test context attributes (account_id, user_id, role)

---

## Endpoint Migration

### Task 2.8: Create Permission Mapping for Existing Endpoints

**Priority**: High

**Estimated Time**: 3 hours

**Dependencies**: None (can be done in parallel)

**File Location**: `docs/ENDPOINT_PERMISSION_MAPPING.md`

**Description**: Document which permissions each endpoint requires.

**Implementation**: Create spreadsheet/document mapping:

| Endpoint | Method | Permission Required | Role Access |
|----------|--------|---------------------|-------------|
| `/v1/admin/accounts/{id}` | GET | `account.read` | Owner, Manager, Viewer |
| `/v1/admin/accounts/{id}` | PATCH | `account.write` | Owner |
| `/v1/admin/accounts/{id}/billing` | GET | `account.billing.read` | Owner |
| `/v1/admin/accounts/{id}/billing` | PATCH | `account.billing.write` | Owner |
| `/v1/admin/accounts/{id}/team` | GET | `account.read` | Owner, Manager, Viewer |
| `/v1/admin/accounts/{id}/team/invite` | POST | `account.team_manage` | Owner |
| `/v1/admin/projects` | GET | `project.read` | Owner, Manager, Viewer |
| `/v1/admin/projects` | POST | `project.create` | Owner, Manager |
| `/v1/admin/projects/{id}` | GET | `project.read` | Owner, Manager, Viewer |
| `/v1/admin/projects/{id}` | PATCH | `project.write` | Owner, Manager |
| `/v1/admin/projects/{id}` | DELETE | `project.delete` | Owner, Manager |
| `/v1/admin/agents` | POST | `agent.create` | Owner, Manager |
| `/v1/admin/agents/{id}` | GET | `agent.read` | Owner, Manager, Viewer |
| `/v1/admin/agents/{id}` | PATCH | `agent.write` | Owner, Manager |
| `/v1/admin/agents/{id}` | DELETE | `agent.delete` | Owner, Manager |
| `/v1/admin/plans/{id}/approve` | POST | `plan.approve` | Owner, Manager |
| `/v1/admin/data/export` | POST | `data.export` | Owner, Manager, Viewer |

**Validation**: Review with product team to confirm permission requirements.

---

### Task 2.9: Migrate Projects Endpoints

**Priority**: High

**Estimated Time**: 2 hours

**Dependencies**: Tasks 2.5, 2.8

**File Location**: `src/api/v1/admin/projects.py`

**Description**: Add permission checks to all project endpoints.

**Requirements**:

**Endpoint Transformations:**

**POST /projects** - Create project
- Before: Depends(get_current_user)
- After: Depends(PermissionChecker("project.create"))
- Parameters: Add account_id (UUID) if not present
- Docstring: "Requires: project.create permission (Owner, Manager)"
- Role Access: Owner, Manager

**GET /projects/{project_id}** - Get project
- Before: Depends(get_current_user)
- After: Depends(PermissionChecker("project.read"))
- Parameters: Add account_id (UUID) if not present
- Docstring: "Requires: project.read permission (Owner, Manager, Viewer)"
- Role Access: Owner, Manager, Viewer

**PATCH /projects/{project_id}** - Update project
- Before: Depends(get_current_user)
- After: Depends(PermissionChecker("project.write"))
- Parameters: Add account_id (UUID) if not present
- Docstring: "Requires: project.write permission (Owner, Manager)"
- Role Access: Owner, Manager

**DELETE /projects/{project_id}** - Delete project
- Before: Depends(get_current_user)
- After: Depends(PermissionChecker("project.delete"))
- Parameters: Add account_id (UUID) if not present
- Docstring: "Requires: project.delete permission (Owner, Manager)"
- Role Access: Owner, Manager

**Implementation Steps**:
1. Add account_id as query parameter if not already present
2. Replace get_current_user with PermissionChecker(permission)
3. Add docstring documenting required permission
4. Test each endpoint with different roles

**Validation Steps**:

1. Test Owner can perform all operations
2. Test Manager can create/read/update/delete
3. Test Viewer can only read
4. Test non-member gets 403
5. Verify error messages include permission name

---

### Task 2.10: Migrate Agents Endpoints

**Priority**: High

**Estimated Time**: 2 hours

**Dependencies**: Tasks 2.5, 2.8

**File Location**: `src/api/v1/admin/agents.py`

**Description**: Add permission checks to all agent endpoints (similar to Task 2.9).

**Permissions Required**:
- `agent.create` - Create agents (Owner, Manager)
- `agent.read` - View agents (Owner, Manager, Viewer)
- `agent.write` - Edit agents (Owner, Manager)
- `agent.delete` - Delete agents (Owner, Manager)

**Validation Steps**: Same as Task 2.9

---

### Task 2.11: Migrate Account Settings Endpoints

**Priority**: High

**Estimated Time**: 2 hours

**Dependencies**: Tasks 2.5, 2.8

**File Location**: `src/api/v1/admin/accounts.py`

**Description**: Add permission checks to account settings endpoints.

**Requirements**:

**Endpoint Transformations:**

**GET /accounts/{account_id}** - Get account details
- Before: Depends(get_current_user)
- After: Depends(PermissionChecker("account.read"))
- Docstring: "Requires: account.read permission (Owner, Manager, Viewer)"
- Role Access: Owner, Manager, Viewer

**PATCH /accounts/{account_id}** - Update account settings
- Before: Depends(get_current_user)
- After: Depends(PermissionChecker("account.write"))
- Docstring: "Requires: account.write permission (Owner only)"
- Role Access: Owner only

**GET /accounts/{account_id}/billing** - Get billing information
- Before: Depends(get_current_user)
- After: Depends(PermissionChecker("account.billing.read"))
- Docstring: "Requires: account.billing.read permission (Owner only)"
- Role Access: Owner only

**PATCH /accounts/{account_id}/billing** - Update billing
- Before: Depends(get_current_user)
- After: Depends(PermissionChecker("account.billing.write"))
- Docstring: "Requires: account.billing.write permission (Owner only)"
- Role Access: Owner only

**POST /accounts/{account_id}/team/invite** - Invite team member
- Before: Depends(get_current_user)
- After: Depends(PermissionChecker("account.team_manage"))
- Docstring: "Requires: account.team_manage permission (Owner only)"
- Role Access: Owner only

**Validation Steps**:

1. Test Owner can access/modify all account settings
2. Test Manager can view but not modify
3. Test Viewer can view but not modify
4. Test only Owner can access billing endpoints

---

### Task 2.12: Migrate Remaining Endpoints

**Priority**: Medium

**Estimated Time**: 3 hours

**Dependencies**: Tasks 2.5, 2.8

**File Locations**: Various (`plans.py`, `data.py`, etc.)

**Description**: Add permission checks to remaining admin endpoints.

**Endpoints**:
- Plans: `plan.approve`
- Data export: `data.export`
- Other administrative endpoints

**Validation**: Full endpoint audit to ensure no unprotected endpoints remain.

---

## Testing

### Task 2.13: Unit Tests for Authorization Functions

**Priority**: High

**Estimated Time**: 3 hours

**Dependencies**: Tasks 2.1-2.3

**File Location**: `tests/unit/auth/test_authorization.py`

**Requirements**:

**Test Class: TestGetUserRoleOnAccount**
- test_returns_role_for_active_member_with_role
  - Setup: Active member with owner role assignment
  - Verify: Returns UserRole.OWNER
- test_returns_none_for_member_without_role
  - Setup: Account member without role assignment
  - Verify: Returns None
- test_returns_none_for_non_member
  - Setup: User not in account
  - Verify: Returns None
- test_returns_none_for_deactivated_member
  - Setup: Deactivated account member
  - Verify: Returns None
- test_caching_works
  - Setup: Clear cache, call twice
  - Verify: Second call hits cache (cache size unchanged), both return same result

**Test Class: TestGetRolePermissions**
- test_owner_has_wildcard_permission
  - Verify: get_role_permissions(OWNER) returns {"*"}
- test_manager_has_project_and_agent_permissions
  - Verify: Manager has project.create, project.write, agent.write, plan.approve
- test_manager_lacks_billing_and_team_permissions
  - Verify: Manager lacks account.billing.*, account.team_manage
- test_viewer_has_only_read_permissions
  - Verify: Viewer has project.read, agent.read, account.read
  - Verify: Viewer lacks project.create, project.write, agent.write
- test_caching_works
  - Setup: Clear cache, call twice
  - Verify: Second call hits cache (cache size unchanged), both return same result

**Test Class: TestCheckPermission**
- test_owner_has_all_permissions
  - Verify: Owner passes check for project.create, account.billing.write, random permissions (wildcard)
- test_manager_permissions
  - Verify: Manager has project.create
  - Verify: Manager lacks account.billing.write, account.team_manage
- test_viewer_permissions
  - Verify: Viewer has project.read
  - Verify: Viewer lacks project.create, project.write
- test_non_member_has_no_permissions
  - Verify: Non-member denied for all permissions
- test_fails_closed_on_error
  - Setup: Invalid UUID causing error
  - Verify: Returns False (fail closed)

**Run Command**: `pytest tests/unit/auth/test_authorization.py -v`

---

### Task 2.14: Integration Tests for Permission Decorators

**Priority**: High

**Estimated Time**: 3 hours

**Dependencies**: Tasks 2.5-2.6

**File Location**: `tests/integration/auth/test_permission_decorators.py`

**Requirements**:

**Test Setup**:
- Create test FastAPI app with test endpoints
- Endpoints: /test/project-read (GET), /test/project-create (POST), /test/admin-only (GET)
- Use PermissionChecker and AdminOnlyChecker dependencies

**Test Class: TestPermissionChecker**
- test_owner_can_access_all_endpoints
  - Verify: Owner can GET /test/project-read (200)
  - Verify: Owner can POST /test/project-create (200)
- test_manager_permissions
  - Verify: Manager can GET /test/project-read (200)
  - Verify: Manager can POST /test/project-create (200)
- test_viewer_cannot_create
  - Verify: Viewer can GET /test/project-read (200)
  - Verify: Viewer cannot POST /test/project-create (403)
  - Verify: Error details include "permission_denied" and "project.create"
- test_non_member_denied
  - Verify: Non-member gets 403 for all endpoints

**Test Class: TestAdminOnlyChecker**
- test_admin_can_access
  - Verify: Admin can GET /test/admin-only (200)
- test_regular_user_denied
  - Verify: Regular user (even Owner) gets 403
  - Verify: Error contains "admin_required"

---

### Task 2.15: API Endpoint Integration Tests

**Priority**: High

**Estimated Time**: 4 hours

**Dependencies**: Tasks 2.9-2.12

**File Location**: `tests/integration/api/test_rbac_endpoints.py`

**Requirements**:

**Test Class: TestProjectEndpoints**
- test_create_project_as_owner
  - Verify: POST /v1/admin/projects returns 200 for Owner
- test_create_project_as_manager
  - Verify: POST /v1/admin/projects returns 200 for Manager
- test_create_project_as_viewer
  - Verify: POST /v1/admin/projects returns 403 for Viewer
  - Verify: Error contains "project.create"
- test_delete_project_as_viewer
  - Verify: DELETE /v1/admin/projects/{id} returns 403 for Viewer

**Test Class: TestAccountEndpoints**
- test_view_account_settings_all_roles
  - Verify: GET /v1/admin/accounts/{id} returns 200 for Owner, Manager, Viewer
- test_modify_account_owner_only
  - Verify: PATCH /v1/admin/accounts/{id} returns 200 for Owner
  - Verify: PATCH returns 403 for Manager and Viewer
- test_billing_owner_only
  - Verify: GET /v1/admin/accounts/{id}/billing returns 200 for Owner
  - Verify: GET returns 403 for Manager

**Test Class: TestAgentEndpoints**
- test_create_agent_permissions
  - Verify: POST /v1/admin/agents returns 200 for Owner and Manager
  - Verify: POST returns 403 for Viewer

---

### Task 2.16: Performance Tests

**Priority**: Medium

**Estimated Time**: 2 hours

**Dependencies**: Tasks 2.1-2.3

**File Location**: `tests/performance/test_authorization_performance.py`

**Requirements**:

**Test Class: TestAuthorizationPerformance**
- test_permission_check_latency
  - Purpose: Verify permission checks complete in <50ms p99
  - Algorithm:
    1. Run check_permission() 1000 times
    2. Measure latency for each call
    3. Calculate p50, p95, p99 percentiles using statistics.quantiles()
    4. Print results
    5. Assert p99 < 50ms, p95 < 20ms
  - Verify: All calls return correct result (True for Owner)

- test_cache_hit_performance
  - Purpose: Verify cache hits are <10ms p99
  - Algorithm:
    1. Warm up cache with one call
    2. Run check_permission() 100 times
    3. Measure latency for each call (should be cache hits)
    4. Calculate p99 percentile
    5. Print result
    6. Assert p99 < 10ms

- test_concurrent_permission_checks
  - Purpose: Verify thread safety
  - Algorithm:
    1. Create function calling check_permission()
    2. Use ThreadPoolExecutor with 10 workers
    3. Submit 100 concurrent permission checks
    4. Collect all results
    5. Verify all 100 succeed (return True)

**Run Command**: `pytest tests/performance/test_authorization_performance.py -v -s`

**Expected Results**:
- p99 latency < 50ms
- p95 latency < 20ms
- Cache hit latency p99 < 10ms
- 100% success rate for concurrent checks

---

## Validation Checklist

Before marking Phase 2 complete, ensure:

- [ ] All core authorization functions implemented and tested
- [ ] Permission decorators work correctly
- [ ] FastAPI dependencies inject properly
- [ ] All project endpoints migrated to RBAC
- [ ] All agent endpoints migrated to RBAC
- [ ] All account endpoints migrated to RBAC
- [ ] Unit tests passing (>80% coverage)
- [ ] Integration tests passing
- [ ] Performance tests meet targets (<50ms p99)
- [ ] Cache warming works on startup
- [ ] Error messages are clear and actionable
- [ ] Logging is comprehensive (debug, info, warning levels)
- [ ] Thread safety verified (concurrent requests)
- [ ] Admin endpoints preserve existing functionality

---

## Estimated Timeline

| Category | Tasks | Estimated Time |
|----------|-------|----------------|
| Core Authorization Functions | 2.1 - 2.4 | 6 hours |
| Feature Flag Infrastructure | 2.4.5 | 3 hours |
| Permission Decorators (Dual-Mode) | 2.5 - 2.6 | 4 hours |
| FastAPI Dependencies | 2.7 | 1.5 hours |
| Endpoint Migration | 2.8 - 2.12 | 12 hours |
| Testing (incl. dual-mode tests) | 2.13 - 2.16 | 12 hours |
| **Total** | | **38.5 hours** |

*Note: Estimates are for development time only. Add 20-30% buffer for code review, bug fixes, and iteration. The dual-mode approach adds ~4 hours but enables zero-downtime migration.*

---

## Dependencies Summary

**Critical Path**:

1. Core functions (2.1-2.3) → Decorator (2.5) → Endpoint migration (2.9-2.12)
2. Permission mapping (2.8) informs endpoint migration
3. Tests (2.13-2.16) depend on implementation

**Parallelizable Work**:

- Permission mapping (2.8) can be done early
- Different endpoint migrations (2.9-2.12) can be done in parallel
- Unit tests (2.13) and integration tests (2.14) can be written in parallel

---

## Next Steps After Phase 2

Once Phase 2 is complete, proceed to:

- **Phase 3**: Team Management API (invite, role assignment, user management)
- See [PHASE_3_TASKS.md](./PHASE_3_TASKS.md) for detailed plan

Key Phase 3 tasks will include:

- Team invitation flow (email, tokens, acceptance)
- Role management endpoints (assign, update, remove)
- User invitation acceptance
- Multi-account support (account switcher)
- Notification emails
