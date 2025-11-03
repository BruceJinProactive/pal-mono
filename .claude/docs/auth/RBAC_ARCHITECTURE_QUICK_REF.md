# RBAC Architecture Quick Reference

**TL;DR**: Users assign **roles**, APIs check **permissions**. This gives v1 simplicity with v2+ extensibility.

---

## The Key Design Decision

```
┌─────────────────────────────────────────────────────────────┐
│                    What Users See (v1)                      │
│                                                             │
│   "Make Alice a Manager"    ← Simple!                      │
│                                                             │
│   Roles: Owner | Manager | Viewer                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                 What APIs Check (v1)                        │
│                                                             │
│   @require_permission("project.create")                     │
│   @require_permission("plan.approve")                       │
│                                                             │
│   Permissions: project.create, agent.write, plan.approve   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              What the Database Stores                       │
│                                                             │
│   account_users: user_id → role: "manager"                 │
│   role_permissions: "manager" → [permissions]              │
│   permissions: "project.create", "agent.write", etc.       │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Schema Summary

### Core Tables

```sql
-- Permission definitions
permissions (
  id UUID PRIMARY KEY,
  name VARCHAR UNIQUE,              -- "project.create"
  resource_type VARCHAR,            -- "project"
  action VARCHAR,                   -- "create"
  display_name VARCHAR,             -- "Create Projects"
  description TEXT
)

-- Which permissions each role has
role_permissions (
  role ENUM('owner', 'manager', 'viewer'),
  permission_id UUID → permissions.id,
  UNIQUE(role, permission_id)
)

-- User role assignments (unchanged from simple RBAC)
account_users (
  user_id UUID,
  account_id UUID,
  account_role ENUM('owner', 'manager', 'viewer')  -- Still just roles!
)
```

---

## Permission Checking Flow

### Code Example

```python
# Step 1: Get user's role (from account_users or project_users)
role = get_effective_role(user_id, account_id, project_id)
# Returns: "manager"

# Step 2: Get permissions for role (CACHED in Redis for 15 min)
permissions = get_role_permissions(role)
# Returns: {"project.create", "project.read", "project.write", ...}

# Step 3: Check if required permission exists
if "project.create" in permissions:
    allow()
else:
    deny()
```

### Decorator Usage

```python
@require_permission("project.create")
async def create_project(user: UserContext, account_id: UUID):
    # User must have "project.create" permission
    # Which means their role (owner/manager/viewer) must include it
    pass

@require_permission("plan.approve")
async def approve_plan(user: UserContext, plan_id: UUID):
    # Only roles with "plan.approve" permission can call this
    pass

@require_permission("account.billing.read")
async def view_billing(user: UserContext, account_id: UUID):
    # Only Owner has this permission in v1
    pass
```

---

## Default Permission Mappings

### Owner Role

```
Permissions: * (all permissions)

Includes:
- account.read, account.write, account.billing.*
- account.team_manage
- project.create, project.read, project.write, project.delete
- agent.create, agent.read, agent.write, agent.delete
- plan.approve
- data.export
- ... (all future permissions too)
```

### Manager Role

```
Permissions:
- account.read
- project.create, project.read, project.write, project.delete
- agent.create, agent.read, agent.write, agent.delete
- plan.approve
- data.export

Cannot:
- account.write, account.billing.*
- account.team_manage
```

### Viewer Role

```
Permissions:
- account.read
- project.read
- agent.read
- data.export

Cannot:
- Any write/create/delete operations
- Team management
- Billing access
- Plan approval
```

---

## Caching Strategy

### Two-Tier Cache (Redis)

```python
# Cache 1: Role permissions (long-lived, rarely changes)
Cache Key: "permissions:manager"
Value: ["project.create", "project.read", "agent.write", ...]
TTL: 15 minutes
Invalidate: When role_permissions table changes (admin operation)

# Cache 2: User roles (medium-lived)
Cache Key: "user_role:{user_id}:{account_id}:{project_id}"
Value: "manager"
TTL: 5 minutes
Invalidate: When user's role changes
```

### Why This Is Efficient

- ✅ Only **3 cache keys** for role permissions (owner, manager, viewer)
- ✅ vs. thousands of cache keys if we cached per-user permissions
- ✅ Adding new permission = just update database + clear 3 cache keys
- ✅ Most requests hit cache, not database

---

## Adding a New Permission (No Code Changes!)

```sql
-- 1. Add permission to database
INSERT INTO permissions (id, resource_type, action, name, display_name, description)
VALUES (
  uuid_generate_v4(),
  'report',
  'generate',
  'report.generate',
  'Generate Reports',
  'Allows user to generate custom reports'
);

-- 2. Assign to roles that should have it
INSERT INTO role_permissions (role, permission_id)
SELECT 'manager', id FROM permissions WHERE name = 'report.generate';

INSERT INTO role_permissions (role, permission_id)
SELECT 'owner', id FROM permissions WHERE name = 'report.generate';

-- 3. Clear cache
REDIS: DEL permissions:manager
REDIS: DEL permissions:owner
```

```python
# 4. Use in code
@require_permission("report.generate")
async def generate_report(user: UserContext, account_id: UUID):
    # Now only Owner and Manager can generate reports
    # Viewer role doesn't have this permission
    pass
```

**That's it!** No changes to authorization framework, no deployment needed (just cache clear).

---

## Evolution Path

### v1: Role-Based UI, Permission-Based APIs ✅
- **User Experience**: Assign roles (Owner, Manager, Viewer)
- **APIs**: Check permissions (`@require_permission("project.create")`)
- **Database**: Has both `permissions` and `role_permissions` tables
- **UI Complexity**: Low (3 roles, simple dropdown)
- **Extensibility**: High (easy to add permissions)

### v2: Expose Permission Management UI
- **User Experience**: See and edit which permissions each role has
- **New UI**: Permission matrix (rows=roles, columns=permissions)
- **API Changes**: None! Just query existing tables
- **Database Changes**: None! Already supports this
- **Example**: "Manager role should also have `report.generate` permission"

### v3: Custom Roles
- **User Experience**: Create custom roles with chosen permissions
- **New Tables**: `custom_roles`, `custom_role_permissions`
- **API Changes**: Minimal (handle custom role IDs)
- **Database**: Extend `account_users.account_role` to support custom role IDs
- **Example**: Create "Support Agent" role with specific permission set

### v4: Per-User Permission Overrides
- **User Experience**: Grant/revoke specific permissions for individual users
- **New Table**: `user_permissions` (overrides role permissions)
- **API Changes**: Update permission resolution to merge user + role permissions
- **Database**: Add user-specific overrides
- **Example**: "Alice is a Viewer, but give her `project.write` for Project X"

---

## Benefits of This Architecture

### For v1 MVP
- ✅ **Simple UI**: Users only see 3 roles
- ✅ **Fast to Build**: Standard role assignment interface
- ✅ **Easy to Understand**: "Manager can do X, Y, Z"
- ✅ **Performant**: Cached permissions, minimal DB queries

### For v2+ Evolution
- ✅ **No API Changes**: Endpoints already check permissions
- ✅ **No Authorization Refactor**: Framework supports fine-grained permissions
- ✅ **Database Ready**: Tables already support permission mappings
- ✅ **Just Add UI**: Only need permission management interface

### For Engineering
- ✅ **Declarative**: `@require_permission("action")` is self-documenting
- ✅ **Testable**: Easy to test permission checks in isolation
- ✅ **Maintainable**: Add permission = SQL insert, not code change
- ✅ **Future-Proof**: Supports any permission granularity

---

## Common Operations

### Check if User Can Perform Action

```python
# In endpoint
@require_permission("project.delete")
async def delete_project(user: UserContext, project_id: UUID):
    # Permission check happens automatically
    pass

# Programmatically
has_permission = check_user_permission(
    user_id=user.id,
    account_id=account_id,
    project_id=project_id,  # Optional, for project-level overrides
    permission="project.delete"
)
```

### Add New Action to Existing Resource

```sql
-- Example: Add "archive" action for projects
INSERT INTO permissions (name, resource_type, action, display_name, description)
VALUES (
  'project.archive',
  'project',
  'archive',
  'Archive Projects',
  'Allows archiving projects without deleting them'
);

-- Assign to roles
INSERT INTO role_permissions (role, permission_id)
SELECT 'owner', id FROM permissions WHERE name = 'project.archive';

INSERT INTO role_permissions (role, permission_id)
SELECT 'manager', id FROM permissions WHERE name = 'project.archive';
```

```python
# Use in code
@require_permission("project.archive")
async def archive_project(user: UserContext, project_id: UUID):
    # Implementation
    pass
```

### Change Which Roles Have a Permission

```sql
-- Example: Remove "project.delete" from Manager role
DELETE FROM role_permissions
WHERE role = 'manager'
  AND permission_id = (SELECT id FROM permissions WHERE name = 'project.delete');

-- Clear cache
REDIS: DEL permissions:manager
```

Now Managers can no longer delete projects (but can still create/edit).

---

## Testing Strategy

### Unit Tests (Permission Resolution)

```python
def test_manager_has_project_create_permission():
    permissions = get_role_permissions("manager")
    assert "project.create" in permissions

def test_viewer_lacks_project_create_permission():
    permissions = get_role_permissions("viewer")
    assert "project.create" not in permissions

def test_owner_has_all_permissions():
    permissions = get_role_permissions("owner")
    assert "project.create" in permissions
    assert "account.billing.read" in permissions
    assert "plan.approve" in permissions
```

### Integration Tests (Endpoint Authorization)

```python
async def test_manager_can_create_project():
    response = await client.post(
        "/v1/admin/projects",
        json={"name": "Test Project"},
        headers=auth_headers(role="manager")
    )
    assert response.status_code == 200

async def test_viewer_cannot_create_project():
    response = await client.post(
        "/v1/admin/projects",
        json={"name": "Test Project"},
        headers=auth_headers(role="viewer")
    )
    assert response.status_code == 403
    assert "project.create" in response.json()["detail"]
```

### Performance Tests

```python
def test_permission_check_performance():
    # Should complete in <50ms
    with Timer() as t:
        for _ in range(100):
            has_permission = check_user_permission(
                user_id=test_user_id,
                account_id=test_account_id,
                permission="project.create"
            )

    avg_time = t.elapsed / 100
    assert avg_time < 0.05  # 50ms
```

---

## FAQ

### Q: Why not just check roles in APIs?

**A**: Checking roles is inflexible. If you want to add a new action (e.g., `plan.reject`), you'd need to update every API endpoint that needs to check for it. With permissions, you just:
1. Add permission to database
2. Assign to roles
3. Use `@require_permission("plan.reject")`

### Q: Won't this be slower than role checking?

**A**: No, because permissions are cached. Checking `if "project.create" in cached_permissions` is O(1) and happens in memory. The cache hit rate is high because role permissions rarely change.

### Q: What if I want to add a permission that only some Managers should have?

**A**: In v1, you can't (all Managers have the same permissions). But in v2, you can either:
- Create a custom role (e.g., "Senior Manager") with extra permissions
- Add per-user permission overrides

The architecture supports both, you just need to build the UI.

### Q: How do I know what permissions exist?

**A**: Query the `permissions` table:

```sql
SELECT name, display_name, description FROM permissions ORDER BY resource_type, action;
```

Or in code:

```python
permissions = db.query(Permission).order_by(Permission.resource_type, Permission.action).all()
```

---

## Key Takeaway

> **"Roles are just UI-friendly labels for permission bundles."**

Users think in terms of roles ("Make Alice a Manager"), but the system thinks in terms of permissions ("Does Alice have `project.create`?"). This separation allows v1 simplicity with v2+ power.

---

**For More Details**: See full PRD at [PRD](./PRD_RBAC.md)
