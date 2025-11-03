# Phase 1: RBAC Foundation - Detailed Task Breakdown

**Timeline**: Weeks 1-2

**Goal**: Set up database schema, models, and core infrastructure for RBAC system

**Related**: [TDD_RBAC.md](./TDD_RBAC.md)

---

## Design Principles

### Unified Resource-Role Model

**Key Design Decisions:**

1. **Account membership ≠ permissions** - Being added to an account means you can access it, not that you have any permissions
2. **All resources are equal** - Account, project, agent, etc. all use the same role assignment table
3. **Role per resource** - Users have roles on specific resources (including the account itself)
4. **No inheritance or overrides** - Simple lookup: "What role does this user have on THIS resource?"

**Example:**

```
Alice is a member of "Acme Corp" account

Alice's role assignments:
- account:acme-corp-id → viewer     (can view account settings)
- project:project-x-id → owner      (full control of Project X)
- project:project-y-id → manager    (can edit Project Y, can't delete)
- agent:agent-z-id → viewer         (read-only for Agent Z)

Permission checks:
✅ Alice edits Project X → check project:project-x-id → owner → has project.write
❌ Alice deletes Project Y → check project:project-y-id → manager → no project.delete
❌ Alice changes billing → check account:acme-corp-id → viewer → no account.billing.write
```

**Benefits:**

- Extremely simple and consistent model
- No complex permission resolution logic
- Easy to understand: "What's my role on this thing?"
- Flexible: Can assign different roles to different resources
- Performant: Single table lookup

**Permission Resolution:**

```
1. Verify user is member of account (account_users)
2. Get user's role on specific resource (resource_role_assignments)
3. Get permissions for that role (role_permissions)
4. Check if permission exists
```

---

## Task Categories

1. [Database Schema](#database-schema)
2. [SQLAlchemy Models](#sqlalchemy-models)
3. [Repository Layer](#repository-layer)
4. [Cache Infrastructure](#cache-infrastructure)
5. [Testing](#testing)

---

## Database Schema

### Task 1.1: Define RBAC Database Schema

**Priority**: High

**Estimated Time**: 4 hours

**Dependencies**: None

**Description**: Define the complete database schema for RBAC tables. Your migration scripts will generate the actual migrations from these schema definitions.

#### 1.1.1: Enum Types

Define PostgreSQL ENUM types:
- `user_role`: owner, manager, viewer
- `account_user_status`: pending, active, deactivated
- `invitation_status`: pending, accepted, expired, revoked

#### 1.1.2: Permissions Table

**Purpose**: Store all available permissions in the system

**Key Fields**:
- id (UUID, PK)
- name (string, unique) - format: "resource.action" (e.g., "project.create")
- resource_type, action (for categorization)
- display_name, description (human-readable)
- created_at timestamp

**Constraints**:
- Unique index on name
- Check constraint on name format (lowercase, dot notation)

#### 1.1.3: Role Permissions Table

**Purpose**: Map roles to permissions (what each role can do)

**Key Fields**:
- id (UUID, PK)
- role (enum: user_role)
- permission_id (UUID, FK to permissions)
- created_at

**Constraints**:
- Unique constraint on (role, permission_id)
- Indexes on role and permission_id

#### 1.1.4: Account Users Table

**Purpose**: Track user memberships in accounts (membership ≠ permissions)

**Key Fields**:
- id, account_id, user_id
- added_by (nullable for self-onboarding)
- added_at, status (active/deactivated)
- created_at, updated_at

**Constraints**:
- Unique on (account_id, user_id)
- Indexes on user_id, account_id, status
- Updated_at trigger

**Design Notes**:
- No role column (roles in resource_role_assignments)
- Membership grants access, not permissions

#### 1.1.5: Resource Role Assignments Table

**Purpose**: Unified table for ALL role assignments on ANY resource (including account)

**Key Fields**:
- id, user_id, account_id
- resource_type (string: 'account', 'project', 'agent', etc.)
- resource_id (UUID of the specific resource)
- role (enum: owner/manager/viewer)
- assigned_by, assigned_at, reason (audit trail)
- created_at, updated_at

**Constraints**:
- Unique on (user_id, account_id, resource_type, resource_id)
- Indexes on user_id, (resource_type, resource_id), account_id
- Updated_at trigger

**Design Notes**:
- Account-level role: resource_type='account', resource_id=account_id
- Project-level role: resource_type='project', resource_id=project_id
- Agent-level role: resource_type='agent', resource_id=agent_id

#### 1.1.6: User Invitations Table

**Purpose**: Track team member invitations

**Key Fields**:
- id, account_id, email
- account_role (role to assign on acceptance)
- invited_by, invitation_token (unique, 64 chars)
- expires_at, accepted_at, status
- created_at

**Constraints**:
- Unique index on invitation_token
- Check constraint: expires_at > created_at
- Indexes on email, account_id, status

**Design Notes**:
- On acceptance: create account_users + resource_role_assignments records
- Token must be cryptographically secure (use secrets.token_urlsafe(48))

**Implementation Notes**:
- Ensure accounts/users tables exist before creating
- Verify update_updated_at_column() trigger function exists
- Use migration scripts to generate actual migrations

**Validation Steps**:

- Run migration generation script
- Apply migrations to dev database
- Verify all tables and indexes exist
- Test constraint enforcement (unique, check, foreign key)
- Verify triggers work (updated_at changes on update)

---

### Task 1.2: Seed Default Permissions

**Priority**: High

**Estimated Time**: 1 hour

**Dependencies**: Task 1.1

**Description**: Create seed data script to populate default permissions and role mappings.

**Permissions to Seed**:

Account permissions:
- account.read, account.write
- account.billing.read, account.billing.write
- account.team_manage

Project permissions:
- project.create, project.read, project.write, project.delete

Agent permissions:
- agent.create, agent.read, agent.write, agent.delete

Other permissions:
- plan.approve
- data.export

**Role-Permission Mappings**:
- **Owner**: All permissions (15 total)
- **Manager**: All except account.billing.*, account.team_manage (10 permissions)
- **Viewer**: Only *.read and data.export (4 permissions)

**Implementation**: Create data migration to insert permissions and role mappings

**Verification**: Query role_permissions grouped by role, verify counts match expected

---

### Task 1.3: Backfill Account Users and Role Assignments

**Priority**: Medium

**Estimated Time**: 2 hours

**Dependencies**: Task 1.1

**Description**: Migrate existing user-account relationships to the new tables.

**Implementation Steps**:

1. Analyze current schema to identify existing user-account relationships
2. Backfill `account_users` (membership only)
3. Backfill `resource_role_assignments` (assign owner role on account for existing users)
4. Test on staging data
5. Run in production

**Backfill Requirements**:

**Step 1 - Account Users Table**:
- Source: Existing user-account relationships
- Target: account_users table
- Fields: account_id, user_id, added_by (NULL for self-onboarded), added_at, status='active'
- Handle conflicts: Skip duplicates

**Step 2 - Resource Role Assignments Table**:
- Source: account_users records from Step 1
- Target: resource_role_assignments table
- Fields: user_id, account_id, resource_type='account', resource_id=account_id, role='owner', assigned_by=NULL, assigned_at
- Handle conflicts: Skip duplicates

**Important Notes**:
- Step 1 creates account membership (no permissions yet)
- Step 2 assigns owner role on the account resource itself
- Set `assigned_by = NULL` for self-onboarded users
- Run in a transaction and verify before committing

**Verification Requirements**:
- Count active memberships in account_users
- Count account-level role assignments in resource_role_assignments
- Verify every account member has at least one role assignment (left join should return 0 orphans)

---

## SQLAlchemy Models

### Task 2.1: Create RBAC Enums

**Priority**: High

**Estimated Time**: 30 minutes

**Dependencies**: Database schema defined

**Description**: Create Python enums matching database types.

**File Location**: `src/models/rbac/enums.py`

**Requirements**:

**Enum: UserRole** (str, enum.Enum)
- Values: OWNER="owner", MANAGER="manager", VIEWER="viewer"
- Implements __str__() returning value

**Enum: AccountUserStatus** (str, enum.Enum)
- Values: PENDING="pending", ACTIVE="active", DEACTIVATED="deactivated"
- Implements __str__() returning value

**Enum: InvitationStatus** (str, enum.Enum)
- Values: PENDING="pending", ACCEPTED="accepted", EXPIRED="expired", REVOKED="revoked"
- Implements __str__() returning value

---

### Task 2.2: Create Permission Model

**Priority**: High

**Estimated Time**: 45 minutes

**Dependencies**: Task 2.1

**File Location**: `src/models/rbac/permission.py`

**Requirements**:

**Class: Permission(Base)**
- Table: permissions
- Columns:
  - id: UUID, PK, auto-generated
  - name: String(100), unique, indexed (format: "resource.action")
  - resource_type: String(50)
  - action: String(50)
  - display_name: String(100)
  - description: Text, nullable
  - created_at: TIMESTAMP, default NOW()
- Relationships:
  - role_mappings → RolePermission (cascade delete)
- Constraints:
  - Check constraint on name format (regex: lowercase, dot notation)
- Methods:
  - __repr__() showing name, resource_type, action

---

### Task 2.3: Create RolePermission Model

**Priority**: High

**Estimated Time**: 45 minutes

**Dependencies**: Task 2.1, Task 2.2

**File Location**: `src/models/rbac/role_permission.py`

**Requirements**:

**Class: RolePermission(Base)**
- Table: role_permissions
- Purpose: Junction table mapping roles to permissions
- Columns:
  - id: UUID, PK, auto-generated
  - role: Enum(UserRole), indexed
  - permission_id: UUID, FK to permissions.id (cascade delete), indexed
  - created_at: TIMESTAMP, default NOW()
- Relationships:
  - permission → Permission (back_populates role_mappings)
- Constraints:
  - Unique constraint on (role, permission_id)
- Methods:
  - __repr__() showing role, permission_id

---

### Task 2.4: Create AccountUser Model

**Priority**: High

**Estimated Time**: 45 minutes

**Dependencies**: Task 2.1

**File Location**: `src/models/rbac/account_user.py`

**Requirements**:

**Class: AccountUser(Base)**
- Table: account_users
- Purpose: User membership in account (membership ≠ permissions)
- Columns:
  - id: UUID, PK, auto-generated
  - account_id: UUID, FK to accounts.id (cascade delete), indexed
  - user_id: UUID, FK to users.id (cascade delete), indexed
  - added_by: UUID, FK to users.id, nullable (for self-onboarding)
  - added_at: TIMESTAMP, default NOW()
  - status: Enum(AccountUserStatus), default "active", indexed
  - created_at: TIMESTAMP, default NOW()
  - updated_at: TIMESTAMP, default NOW(), auto-update on change
- Relationships:
  - Optionally link to Account, User models (adjust based on existing models)
- Constraints:
  - Unique constraint on (account_id, user_id)
- Methods:
  - __repr__() showing user_id, account_id, status
- Design Note: NO role column - roles assigned via ResourceRoleAssignment

---

### Task 2.5: Create ResourceRoleAssignment Model

**Priority**: High

**Estimated Time**: 1 hour

**Dependencies**: Task 2.1

**File Location**: `src/models/rbac/resource_role_assignment.py`

**Requirements**:

**Class: ResourceRoleAssignment(Base)**
- Table: resource_role_assignments
- Purpose: Unified table for ALL role assignments on ANY resource (account, project, agent, etc.)
- Columns:
  - id: UUID, PK, auto-generated
  - user_id: UUID, FK to users.id (cascade delete), indexed
  - account_id: UUID, FK to accounts.id (cascade delete), indexed
  - resource_type: String(50), indexed (e.g., 'account', 'project', 'agent')
  - resource_id: UUID, indexed (the specific resource)
  - role: Enum(UserRole)
  - assigned_by: UUID, FK to users.id, nullable
  - assigned_at: TIMESTAMP, default NOW()
  - reason: Text, nullable (optional explanation)
  - created_at: TIMESTAMP, default NOW()
  - updated_at: TIMESTAMP, default NOW(), auto-update on change
- Relationships:
  - Optionally link to User, Account models (adjust based on existing models)
- Constraints:
  - Unique constraint on (user_id, account_id, resource_type, resource_id)
- Methods:
  - __repr__() showing user_id, resource_type:resource_id, role
- Design Examples:
  - Account-level: resource_type='account', resource_id=account_id
  - Project-level: resource_type='project', resource_id=project_id

---

### Task 2.6: Create UserInvitation Model

**Priority**: High

**Estimated Time**: 45 minutes

**Dependencies**: Task 2.1

**File Location**: `src/models/rbac/user_invitation.py`

**Requirements**:

**Class: UserInvitation(Base)**
- Table: user_invitations
- Purpose: Team member invitations (creates account membership + role on acceptance)
- Columns:
  - id: UUID, PK, auto-generated
  - account_id: UUID, FK to accounts.id (cascade delete), indexed
  - email: String(255), indexed
  - account_role: Enum(UserRole) - role to assign on acceptance
  - invited_by: UUID, FK to users.id
  - invitation_token: String(64), unique, indexed (use secrets.token_urlsafe(48))
  - expires_at: TIMESTAMP
  - accepted_at: TIMESTAMP, nullable
  - status: Enum(InvitationStatus), default "pending", indexed
  - created_at: TIMESTAMP, default NOW()
- Relationships:
  - Optionally link to Account, User models (adjust based on existing models)
- Constraints:
  - Check constraint: expires_at > created_at
- Methods:
  - __repr__() showing email, account_id, account_role, status
- Acceptance Flow:
  1. Create account_users record
  2. Create resource_role_assignments record (resource_type='account')

---

### Task 2.7: Create Models Package

**Priority**: Medium

**Estimated Time**: 15 minutes

**Dependencies**: Tasks 2.1-2.6

**File Location**: `src/models/rbac/__init__.py`

**Requirements**:

- Import and re-export all RBAC models and enums
- Exports: UserRole, AccountUserStatus, InvitationStatus, Permission, RolePermission, AccountUser, ResourceRoleAssignment, UserInvitation
- Define __all__ list for clean imports

---

## Repository Layer

### Task 3.1: Create Permission Repository

**Priority**: High

**Estimated Time**: 1 hour

**Dependencies**: Task 2.2

**File Location**: `src/repositories/rbac/permission_repository.py`

**Requirements**:

**Class: PermissionRepository**
- Constructor: __init__(session: Session)
- Methods:
  - get_by_name(name: str) → Optional[Permission]
    Purpose: Retrieve permission by name
  - get_by_id(permission_id: UUID) → Optional[Permission]
    Purpose: Retrieve permission by ID
  - get_all() → List[Permission]
    Purpose: Retrieve all permissions
  - get_by_resource_type(resource_type: str) → List[Permission]
    Purpose: Retrieve all permissions for a resource type
  - create(name, resource_type, action, display_name, description=None) → Permission
    Purpose: Create a new permission

---

### Task 3.2: Create RolePermission Repository

**Priority**: High

**Estimated Time**: 1.5 hours

**Dependencies**: Task 2.3

**File Location**: `src/repositories/rbac/role_permission_repository.py`

**Requirements**:

**Class: RolePermissionRepository**
- Constructor: __init__(session: Session)
- Methods:
  - get_permissions_for_role(role: UserRole) → List[Permission]
    Purpose: Get all permission objects for a role
  - get_permission_names_for_role(role: UserRole) → Set[str]
    Purpose: Get permission names for caching (returns set of strings)
  - add_permission_to_role(role: UserRole, permission_id: UUID) → RolePermission
    Purpose: Add a permission to a role
  - remove_permission_from_role(role: UserRole, permission_id: UUID) → bool
    Purpose: Remove a permission from a role
  - get_roles_for_permission(permission_id: UUID) → List[UserRole]
    Purpose: Get all roles that have a specific permission
  - bulk_add_permissions_to_role(role: UserRole, permission_ids: List[UUID]) → List[RolePermission]
    Purpose: Batch operation to add multiple permissions to a role

---

### Task 3.3: Create AccountUser Repository

**Priority**: High

**Estimated Time**: 1.5 hours

**Dependencies**: Task 2.4

**File Location**: `src/repositories/rbac/account_user_repository.py`

**Requirements**:

**Class: AccountUserRepository**
- Constructor: __init__(session: Session)
- Methods:
  - get_by_user_and_account(user_id: UUID, account_id: UUID) → Optional[AccountUser]
    Purpose: Retrieve account user by user and account IDs
  - is_member(user_id: UUID, account_id: UUID) → bool
    Purpose: Check if user is an active member of account
  - get_users_for_account(account_id: UUID, status: Optional[AccountUserStatus] = None) → List[AccountUser]
    Purpose: Get all users for an account, optionally filtered by status
  - get_accounts_for_user(user_id: UUID, status: Optional[AccountUserStatus] = None) → List[AccountUser]
    Purpose: Get all accounts for a user, optionally filtered by status
  - create(account_id, user_id, added_by=None, status=ACTIVE) → AccountUser
    Purpose: Create new account membership
  - update_status(account_user_id: UUID, new_status: AccountUserStatus) → AccountUser
    Purpose: Update user's status in account
  - delete(account_user_id: UUID) → bool
    Purpose: Delete account user (set status to deactivated)

---

### Task 3.4: Create ResourceRoleAssignment Repository

**Priority**: High

**Estimated Time**: 2.5 hours

**Dependencies**: Task 2.5

**File Location**: `src/repositories/rbac/resource_role_assignment_repository.py`

**Requirements**:

**Class: ResourceRoleAssignmentRepository**
- Constructor: __init__(session: Session)
- Methods:
  - get_role_for_resource(user_id, account_id, resource_type, resource_id) → Optional[UserRole]
    Purpose: Get user's role on a specific resource
  - get_assignments_for_user(user_id, account_id, resource_type=None) → List[ResourceRoleAssignment]
    Purpose: Get all role assignments for a user, optionally filtered by resource type
  - get_assignments_for_resource(account_id, resource_type, resource_id) → List[ResourceRoleAssignment]
    Purpose: Get all role assignments for a specific resource
  - assign_role(user_id, account_id, resource_type, resource_id, role, assigned_by=None, reason=None) → ResourceRoleAssignment
    Purpose: Assign a role to user for a resource
  - update_role(assignment_id, new_role) → ResourceRoleAssignment
    Purpose: Update an existing role assignment
  - remove_assignment(user_id, account_id, resource_type, resource_id) → bool
    Purpose: Remove a role assignment
  - remove_all_assignments_for_user(user_id, account_id) → int
    Purpose: Remove all role assignments for a user in account (returns count)
  - remove_all_assignments_for_resource(account_id, resource_type, resource_id) → int
    Purpose: Remove all role assignments for a resource (returns count)
  - count_owners_for_account(account_id) → int
    Purpose: Count users with owner role on account resource (prevents removing last owner)

---

### Task 3.5: Create UserInvitation Repository

**Priority**: Medium

**Estimated Time**: 1.5 hours

**Dependencies**: Task 2.6

**File Location**: `src/repositories/rbac/user_invitation_repository.py`

**Requirements**:

**Class: UserInvitationRepository**
- Constructor: __init__(session: Session)
- Methods:
  - create(account_id, email, account_role, invited_by, invitation_token, expires_at) → UserInvitation
    Purpose: Create a new invitation
  - get_by_token(token: str) → Optional[UserInvitation]
    Purpose: Retrieve invitation by token
  - get_by_id(invitation_id: UUID) → Optional[UserInvitation]
    Purpose: Retrieve invitation by ID
  - get_pending_for_account(account_id: UUID) → List[UserInvitation]
    Purpose: Get all pending invitations for an account
  - get_for_email(email: str) → List[UserInvitation]
    Purpose: Get all invitations for an email address
  - mark_as_accepted(invitation_id: UUID) → UserInvitation
    Purpose: Mark invitation as accepted
  - mark_as_expired(invitation_id: UUID) → UserInvitation
    Purpose: Mark invitation as expired
  - revoke(invitation_id: UUID) → UserInvitation
    Purpose: Revoke an invitation
  - cleanup_expired() → int
    Purpose: Mark expired pending invitations as expired (returns count)

---

### Task 3.6: Create Repository Package

**Priority**: Low

**Estimated Time**: 15 minutes

**Dependencies**: Tasks 3.1-3.5

**File Location**: `src/repositories/rbac/__init__.py`

**Requirements**:

- Import and re-export all RBAC repositories
- Exports: PermissionRepository, RolePermissionRepository, AccountUserRepository, ResourceRoleAssignmentRepository, UserInvitationRepository
- Define __all__ list for clean imports

---

## Cache Infrastructure

### Task 4.1: Add cachetools Dependency

**Priority**: High

**Estimated Time**: 15 minutes

**Dependencies**: None

**Requirements**:

- Add cachetools==5.3.2 to requirements.txt
- Install using pip install cachetools
- Verify installation with pip show cachetools

---

### Task 4.2: Create Cache Module

**Priority**: High

**Estimated Time**: 1 hour

**Dependencies**: Task 4.1

**Description**: Create centralized cache management module using cachetools.

**File Location**: `src/auth/rbac/cache.py`

**Requirements**:

**Cache Instances:**
- role_permissions_cache: TTLCache(maxsize=10, ttl=900) - caches role→permissions mappings
- user_resource_role_cache: TTLCache(maxsize=10000, ttl=300) - caches user→resource→role lookups
- Thread locks: RLock for each cache (thread-safe operations)

**Functions:**
- clear_role_permissions_cache(role: Optional[UserRole] = None) → None
  Purpose: Clear role permissions cache (specific role or all)
  Steps: Acquire lock, delete by hashkey if role provided, else clear all

- clear_user_resource_role_cache(user_id=None, account_id=None, resource_type=None, resource_id=None) → None
  Purpose: Clear user resource role cache (filtered or all)
  Steps: Acquire lock, iterate keys, match filters, delete matching entries
  Key structure: (user_id, account_id, resource_type, resource_id)

- get_cache_stats() → dict
  Purpose: Return cache statistics
  Returns: Dict with size, maxsize, ttl for both caches

---

### Task 4.3: Implement Cache Warming

**Priority**: Medium

**Estimated Time**: 45 minutes

**Dependencies**: Task 4.2

**File Location**: `src/auth/rbac/cache.py` (add to existing)

**Requirements**:

**Function: warm_permission_cache(get_role_permissions_func) → None**
- Purpose: Warm up permission cache on application startup
- Parameters: get_role_permissions_func with signature (UserRole) → Set[str]
- Steps:
  1. Iterate through all UserRole enum values
  2. Call get_role_permissions_func for each role
  3. Log success/failure for each role
  4. Log completion

**Integration:**
- Add to FastAPI startup event in main app
- Call warm_permission_cache with get_role_permissions function
- Wire up in @app.on_event("startup") handler

---

### Task 4.4: Add Cache Monitoring Endpoint

**Priority**: Low

**Estimated Time**: 30 minutes

**Dependencies**: Task 4.2

**File Location**: `src/api/v1/admin/rbac.py`

**Requirements**:

**Router: /admin/rbac** (tags: ["admin", "rbac"])

**Endpoints:**

- GET /cache/stats
  Purpose: Get RBAC cache statistics
  Auth: Requires admin (Depends(require_admin))
  Returns: get_cache_stats() output

- POST /cache/clear
  Purpose: Clear all RBAC caches
  Auth: Requires admin (Depends(require_admin))
  Steps: Call clear_role_permissions_cache() and clear_user_resource_role_cache()
  Returns: Success message
  Warning: Causes temporary performance impact

---

## Testing

### Task 5.1: Create Test Fixtures

**Priority**: High

**Estimated Time**: 2 hours

**Dependencies**: All model tasks

**File Location**: `tests/fixtures/rbac.py`

**Requirements**:

**Fixtures to Create:**

- sample_permissions(db_session)
  Purpose: Create 5 sample permissions (account.read, account.write, project.create, project.read, project.write)
  Returns: List of Permission objects

- role_permission_mappings(db_session, sample_permissions)
  Purpose: Create role-permission mappings
  Mappings: Owner gets all 5, Manager gets 3 (create + read/write), Viewer gets 1 (read only)
  Returns: List of RolePermission objects

- account_member_alice(db_session, sample_account)
  Purpose: Create account member (no role yet)
  Creates: AccountUser with status=ACTIVE, added_by=None
  Returns: AccountUser object

- alice_account_owner(db_session, account_member_alice, sample_account)
  Purpose: Assign owner role on account to Alice
  Creates: ResourceRoleAssignment with resource_type='account', role=OWNER
  Returns: ResourceRoleAssignment object

- alice_project_manager(db_session, account_member_alice, sample_account)
  Purpose: Assign manager role on project to Alice
  Creates: ResourceRoleAssignment with resource_type='project', role=MANAGER
  Returns: ResourceRoleAssignment object

- pending_invitation(db_session, sample_account, account_member_alice)
  Purpose: Create a pending invitation
  Creates: UserInvitation with status=PENDING, account_role=VIEWER, expires in 7 days
  Returns: UserInvitation object

---

### Task 5.2: Unit Tests for Models

**Priority**: High

**Estimated Time**: 2 hours

**Dependencies**: Tasks 2.1-2.6, Task 5.1

**File Location**: `tests/unit/models/test_rbac_models.py`

**Test Cases:**

- test_account_user_no_role(db_session, sample_account)
  Purpose: Test account user membership without role
  Verify: AccountUser created with no role column, added_by=None

- test_resource_role_assignment_account(db_session, sample_account, account_member_alice)
  Purpose: Test role assignment on account resource
  Verify: ResourceRoleAssignment created with resource_type='account', role=OWNER

- test_resource_role_assignment_project(db_session, sample_account, account_member_alice)
  Purpose: Test role assignment on project resource
  Verify: ResourceRoleAssignment created with resource_type='project', role=MANAGER

- test_resource_role_unique_constraint(db_session, alice_account_owner)
  Purpose: Test unique constraint on resource role assignment
  Verify: IntegrityError raised when creating duplicate (same user, account, resource_type, resource_id)

- test_user_invitation_with_role(db_session, sample_account, account_member_alice)
  Purpose: Test invitation with role field
  Verify: UserInvitation created with account_role=MANAGER

---

### Task 5.3: Unit Tests for Repositories

**Priority**: High

**Estimated Time**: 3 hours

**Dependencies**: Tasks 3.1-3.5, Task 5.1

**File Location**: `tests/unit/repositories/test_rbac_repositories.py`

**Test Cases:**

**TestAccountUserRepository:**
- test_is_member(db_session, account_member_alice, sample_account)
  Purpose: Test checking account membership
  Verify: is_member() returns True for active member

- test_create_membership(db_session, sample_account)
  Purpose: Test creating account membership
  Verify: create() returns AccountUser with id, added_by=None

**TestResourceRoleAssignmentRepository:**
- test_get_role_for_resource(db_session, alice_account_owner, sample_account)
  Purpose: Test getting user's role on resource
  Verify: get_role_for_resource() returns UserRole.OWNER for account resource

- test_assign_role_on_project(db_session, account_member_alice, sample_account)
  Purpose: Test assigning role on project
  Verify: assign_role() creates assignment with role=MANAGER, resource_type='project'

- test_count_owners_for_account(db_session, alice_account_owner, sample_account)
  Purpose: Test counting account owners
  Verify: count_owners_for_account() returns 1

---

### Task 5.4: Unit Tests for Cache

**Priority**: High

**Estimated Time**: 1.5 hours

**Dependencies**: Task 4.2

**File Location**: `tests/unit/auth/test_rbac_cache.py`

**Test Cases:**

- test_cache_stats()
  Purpose: Test cache stats reporting
  Verify: get_cache_stats() returns dict with role_permissions and user_resource_roles, correct maxsize values

- test_clear_user_resource_role_cache_by_user()
  Purpose: Test clearing cache by user_id
  Setup: Add 3 entries (2 for user-123, 1 for other-user)
  Action: clear_user_resource_role_cache(user_id="user-123")
  Verify: Only user-123's entries cleared, other-user entry remains

---

### Task 5.5: Integration Test

**Priority**: High

**Estimated Time**: 2 hours

**Dependencies**: All previous tasks

**File Location**: `tests/integration/test_rbac_setup.py`

**Test Cases:**

- test_database_schema_exists(db_engine)
  Purpose: Test that all RBAC tables exist
  Required tables: permissions, role_permissions, account_users, resource_role_assignments, user_invitations
  Verify: Use SQLAlchemy inspector to check all tables exist

- test_unified_resource_role_model(db_session, sample_account, sample_permissions, role_permission_mappings)
  Purpose: Test unified resource-role model end-to-end
  Steps:
    1. Create account membership (AccountUser)
    2. Assign owner role on account (resource_type='account')
    3. Assign manager role on project (resource_type='project')
    4. Verify user is member
    5. Verify user has owner role on account
    6. Verify user has manager role on project
    7. Verify owner has account.write permission
    8. Verify manager lacks account.write but has project.write

---

## Validation Checklist

Before marking Phase 1 complete, ensure:

- [ ] All database tables and indexes created successfully
- [ ] No separate project_users, agent_users tables (unified model)
- [ ] account_users has no role column (membership only)
- [ ] resource_role_assignments table handles all resource types
- [ ] Migrations can be applied and rolled back
- [ ] All SQLAlchemy models import without errors
- [ ] Seed data populated (15 permissions, role mappings)
- [ ] All repositories have unit tests with >80% coverage
- [ ] Cache module works correctly (TTL, invalidation)
- [ ] Integration test passes end-to-end
- [ ] Code passes linting (ruff, black, isort)
- [ ] Type checking passes (pyright)
- [ ] No security vulnerabilities in dependencies

---

## Estimated Timeline

| Category | Tasks | Estimated Time |
|----------|-------|----------------|
| Database Schema | 1.1 - 1.3 | 7 hours |
| SQLAlchemy Models | 2.1 - 2.7 | 5.5 hours |
| Repository Layer | 3.1 - 3.6 | 8.5 hours |
| Cache Infrastructure | 4.1 - 4.4 | 3 hours |
| Testing | 5.1 - 5.5 | 10.5 hours |
| **Total** | | **34.5 hours** |

*Note: Estimates are for development time only. Add 20-30% buffer for code review, testing, and iteration.*

---

## Dependencies Summary

**Critical Path**:

1. Database schema (1.1) → Seed data (1.2) → Backfill (1.3)
2. Enums (2.1) → All models (2.2-2.6) → Package (2.7)
3. Models complete → All repositories (3.1-3.6)
4. Cache setup (4.1-4.2) → Warming (4.3) → Monitoring (4.4)
5. Fixtures (5.1) → All tests (5.2-5.5)

**Parallelizable Work**:

- Repositories 3.1-3.5 can be worked on in parallel once models are done
- Unit tests 5.2-5.4 can be written in parallel
- Cache monitoring (4.4) can be done independently after cache module (4.2)

---

## Next Steps After Phase 1

Once Phase 1 is complete, proceed to:

- **Phase 2**: Authorization Backend (core permission checking functions)
- See [TDD_RBAC.md](./TDD_RBAC.md) for full implementation plan

Key Phase 2 tasks will include:

- Implementing `check_permission()` with unified resource-role lookup
- Implementing `get_role_permissions()` with caching
- Creating `@require_permission()` decorator
- Creating `PermissionChecker` FastAPI dependency
- Updating existing endpoints to use permission checks
