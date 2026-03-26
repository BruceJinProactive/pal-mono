# Add "Store Owner" Role for Store-Level Access Control

---

# Part 1: PRD

## Problem

**Current situation:**

- Multi-tenant restaurant platform with Account → Project (store) hierarchy
- 3 store owners each own specific stores but have no role that fits their needs

**What's broken:**

- No `store_owner` role exists - store owners are either:
  - Given "owner" role → can see ALL stores (security issue)
  - Given "staff" role → too limited (can't configure their store)
- Store owners need full control of THEIR store(s) but no access to other stores

**Who's affected:**

- **Store Owners** - Need to manage their stores independently

## Goal

Add a `store_owner` role (displayed as "Store Owner" in UI) that grants **full management of assigned project(s)** while **isolating access** from other projects.

**Outcome:**

- Each store owner (`store_owner`) sees and manages ONLY their store(s)
- Account owner maintains full access to all stores
- Clear, auditable role-based access control
- FDEs can invite store owners and assign them to specific projects

## Requirements

**Must have:**

- FDE/Account Owner can invite users with "Store Owner" role
- Invitation flow allows selecting one or multiple projects for the user
- Define `store_owner` role in RBAC system with project-level permissions
- Store Owner can view/modify their assigned project(s) settings
- Store Owner can manage agents for their project(s)
- Store Owner can view conversation history for their project(s)
- Store Owner can invite staff members to their project(s)
- Store Owner CANNOT see other store owners' projects
- Store Owner CANNOT modify account settings or billing
- Account owner (owner role) maintains full access to all projects

## User Flow

### FDE Invites Store Owner

1. **FDE (or Account Owner) logs in** to admin console with appropriate permissions
2. **Navigates to Team Management** section
3. **Clicks "Invite User"** button
4. **Fills in invitation form:**
  - Email address of the store owner
  - Name (first/last)
  - Role: "Store Owner" (backend: `store_owner`)
  - **Project Assignment:** Multi-select dropdown of available projects
    - FDE sees all projects in the account
    - Can assign one or multiple stores
    - Example: Select "Downtown Store" for Store Owner 1
5. **Submits invitation**
6. **System creates invitation record** and sends email to store owner
7. **Store Owner receives email** with:
  - Welcome message
  - Link to set password and accept invitation
  - List of stores they'll have access to
8. **Store Owner accepts invitation:**
  - Clicks link in email
  - Sets password in Cognito
  - Account is activated
9. **System creates role assignments:**
  - Insert into `resource_role_assignments` for each selected project
  - Role: `store_owner`
  - User can now log in and access their assigned store(s)

### Store Owner Login & Access

1. **Store Owner logs in** to admin console
2. **System checks role assignments** via `resource_role_assignments` table
3. **Store Owner sees only their store(s)** in project selector (or auto-selected if single)
4. **Store Owner navigates to:**
  - Project settings → Can view/edit store hours, menu, contact info
  - Agents → Can view/configure agents for their store
  - Conversations → Can view call logs for their store only
  - Team → Can invite staff members for their store
5. **Store Owner tries to access another store:**
  - API returns 404 Not Found
  - UI shows "Not Found" or simply doesn't show unauthorized stores

### Account Owner Access

1. **Account owner logs in** with owner role
2. **System recognizes wildcard permissions** (`owner` role = `*`)
3. **Account owner sees ALL stores** in aggregated dashboard
4. **Account owner can:**
  - Switch between stores to view details
  - See account-wide analytics across all stores
  - Manage account billing and settings
  - Create new projects (stores)
  - Assign store owners to stores

### Staff Member Access (existing)

1. **Staff logs in** with staff role on specific project
2. **Sees only operational views** (routines, submissions)
3. **Cannot** access project settings or conversation history

## Out of Scope

- **Multi-account support** - Store Owner role is per-account only
- **Granular sub-permissions** - Either full project access or none (no "can edit hours but not menu")
- **Time-based access** - No temporary or scheduled access grants
- **Delegation** - Store Owners cannot assign other store owners
- **Account-level store_owner** - Role must be assigned per project, not account-wide

## Success Metrics

- **Security:** Zero unauthorized cross-project access incidents after rollout
- **Adoption:** All 3 store owners successfully using the system within 1 week
- **Efficiency:** Store owners can complete typical management tasks (update hours, review conversations, manage staff) without requesting admin help

---

# Part 2: Technical Design

## Overview

Add a new `store_owner` role to the existing RBAC permission system. The infrastructure (tables, permission checking, hierarchy, invitation API) already exists. We only need to:

1. Add `STORE_OWNER` enum value to schemas
2. Define role permissions in auth config
3. Add Store Owner as an option in the admin console team member assignment modal

**Note on naming:**

- **Backend role name:** `store_owner` (in code, database, permissions)
- **UI display name:** "Store Owner" (user-facing)

## Changes Required

### 1. Backend: Add Enum Values to Schemas

**File:** `api/schemas/admin/team.py`

These are Python enums for API validation. The database `role` columns are already VARCHAR and can accept "store_owner" as a string.

**Change 1:** Add to `UserRole` enum (line 19-25):

```python
class UserRole(str, Enum):
    """User roles for account and project-level permissions."""
    OWNER = "owner"
    MANAGER = "manager"
    VIEWER = "viewer"
    STAFF = "staff"
    STORE_OWNER = "store_owner"  # ✅ ADD THIS
```

**Change 2:** Add to `ProjectRole` enum (line 259-264):

```python
class ProjectRole(str, Enum):
    """User roles for project-level permissions."""
    STAFF = "staff"
    MANAGER = "manager"
    VIEWER = "viewer"
    STORE_OWNER = "store_owner"  # ✅ ADD THIS
```

### 2. Backend: Define Role Permissions

**File:** `services/auth_service/config.py`

Add to `ROLE_PERMISSIONS` dict:

```python
"store_owner": {
    "project.read",
    "project.write",
    "agent.create",
    "agent.read",
    "agent.write",
    "agent.delete",
    "history.read",
    "project.team_manage",
    "account.read",
    "account.status.read",
},
```

**Permissions explained:**

- `project.read`, `project.write` - View and modify their store settings
- `agent.create`, `agent.read`, `agent.write`, `agent.delete` - Full agent lifecycle management for their store
- `history.read` - View conversation logs for their store
- `project.team_manage` - Invite staff members to their store
- `account.read`, `account.status.read` - Read-only account visibility (no modification)

### 3. Backend: Assign Users via Invitation Flow

Role assignments will be created through the existing invitation API:

1. FDE/Account Owner sends invitation via admin console
2. Selects "Store Owner" role and assigns project(s)
3. User accepts invitation
4. System automatically creates `resource_role_assignments` records

**No SQL migration needed** - assignments happen through the UI/API workflow.

### 4. Frontend: Admin Console Changes

**File:** `components/(console)/team/actions.ts`

**Change 1:** Add to `UserRole` type (line 5):

```typescript
export type UserRole = 'Owner' | 'Manager' | 'Viewer' | 'Staff' | 'Store Owner';
```

**Change 2:** Add to `roleToBackend` function (lines 16-17):

```typescript
case 'Store Owner':
  return 'store_owner';
```

**Change 3:** Add to `roleFromBackend` function (lines 30-31):

```typescript
case 'store_owner':
  return 'Store Owner';
```

**Change 4:** Add to `getRoleLevel` function (lines 220-221):

```typescript
case 'Store Owner':
  return 2; // Same level as Viewer
```

---

**File:** `lib/constants/route-permissions.ts`

**Change 1:** Add to `NON_STAFF_ROLES` array (line 3):

```typescript
export const NON_STAFF_ROLES: UserRole[] = ['Owner', 'Manager', 'Viewer', 'Store Owner'];
```

**Change 2:** Update `isRouteAllowed` function to handle Store Owner (if needed based on final routing decisions)

---

**File:** `components/(console)/team/Team.tsx`

**Change 1:** Add color for Store Owner badge (line 316):

```typescript
'Store Owner': 'bg-ds-surface-info text-ds-text-info',
```

**Change 2:** Add to `allRoles` array (line 373):

```typescript
const allRoles: UserRole[] = ['Owner', 'Manager', 'Viewer', 'Staff', 'Store Owner'];
```

**Change 3:** Add role description in invite dialog (lines 485-486):

```typescript
{newUserRole === 'Store Owner' &&
  'Can manage their own store locations and operations'}
```

**Change 4:** Add role description in edit modal (lines 877-878):

```typescript
{newRole === 'Store Owner' &&
  'Can manage their own store locations and operations'}
```

**Change 5:** Enable store-specific access for Store Owner (line 329):

```typescript
if (user.role !== 'Staff' && user.role !== 'Store Owner') {
  return <span className="text-muted-foreground">-</span>;
}
```

**Change 6:** Show store selector for Store Owner in invite dialog (line 491):

```typescript
{(newUserRole === 'Staff' || newUserRole === 'Store Owner') && (
```

**Change 7:** Update validation to require store selection for Store Owner (lines 655-657):

```typescript
disabled={
  isSubmitting ||
  ((newUserRole === 'Staff' || newUserRole === 'Store Owner') &&
    newUserProjectIds !== null &&
    newUserProjectIds.length === 0)
}
```

**Change 8:** Include project_ids for Store Owner in API call (line 144 in actions.ts):

```typescript
if ((user.role === 'Staff' || user.role === 'Store Owner') && user.project_ids !== undefined) {
  requestBody.project_ids = user.project_ids;
}
```

---

**File:** `components/(console)/layout/Sidebar.tsx`

Update `allowedRoles` arrays in navigation sections to include `'Store Owner'` where appropriate:

- Dashboard (line 76)
- Hosting (line 91)
- Catering (line 98)
- Integrations (line 105)
- Settings (line 153)
- Docs (line 166)

Example:

```typescript
allowedRoles: ['Owner', 'Manager', 'Viewer', 'Store Owner'],
```

## Testing

### Unit Tests

Test file: `tests/services/auth_service/test_store_owner_role.py`

**Test cases:**

- Store owner can access assigned project
- Store owner cannot access other projects (returns 404, not 403)
- Account owner can still access all projects
- Store owner role has correct permission set (no `account.write`, no billing)

### Integration Tests

Test file: `tests/integration/test_store_owner_rbac.py`

**Test cases:**

- API endpoints return 200 for owned projects, 404 for others
- Cross-project access denied between store owners (404 response)
- Invitation API accepts `store_owner` role with project_ids

### STG Validation

**Manual testing:**

1. Login as each store owner → verify can only see/access their project(s)
2. Login as account owner → verify can access all projects
3. Test negative cases: direct API calls to unauthorized projects return 404
4. Create invitation with `store_owner` role → verify role assignments created on acceptance

## Rollout

### Deploy Order

1. Deploy code to `lat` → `stg` → `prd`
2. Complete manual STG validation before production
3. Send invitations via admin console to assign users to projects

### Monitoring

Watch for:

- 404 error rate spike (may indicate permission issues)
- Permission check latency (should remain <10ms)
- Datadog logs: filter for `permission_denied` events

### Rollback

If needed:

```sql
-- Remove store_owner role assignments
DELETE FROM resource_role_assignments WHERE role = 'store_owner';
```

Then revert code deployment.