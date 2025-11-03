# Technical Design Document: Role-Based Access Control (RBAC)

**Document Owner**: Engineering Lead
**Last Updated**: 2025-10-31
**Status**: Draft
**Version**: 1.0
**Related PRD**: [PRD_RBAC.md](./PRD_RBAC.md)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Architecture](#system-architecture)
3. [Core Design Principle](#core-design-principle)
4. [Data Models](#data-models)
5. [Authorization Framework](#authorization-framework)
6. [API Design](#api-design)
7. [Caching Strategy](#caching-strategy)
8. [Frontend Architecture](#frontend-architecture)
9. [Security Considerations](#security-considerations)
10. [Performance Requirements](#performance-requirements)
11. [Implementation Plan](#implementation-plan)
12. [Testing Strategy](#testing-strategy)
13. [Migration Strategy](#migration-strategy)
14. [Monitoring & Observability](#monitoring--observability)

---

## Executive Summary

This document describes the technical architecture for implementing Role-Based Access Control (RBAC) in the Palona platform. The system is designed with a permission-based architecture under the hood while presenting a simple role-based interface to users.

### Key Architectural Decision

**Users interact with roles (Owner, Manager, Viewer), but APIs check permissions (`project.create`, `plan.approve`, etc.).**

This design provides:
- ✅ **v1 Simplicity**: Simple 3-role UI, easy for users to understand
- ✅ **v2+ Extensibility**: Add fine-grained permissions without changing authorization code
- ✅ **Performance**: Efficient caching (cache 3 role permissions, not thousands of user permissions)
- ✅ **Maintainability**: Add new actions by inserting database rows, not changing code

---

## System Architecture

### High-Level Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Streamlit)                           │
│  ┌────────────────┐  ┌─────────────────┐  ┌──────────────────────┐   │
│  │  Team Mgmt UI  │  │  Account Switch │  │  Role-Based UI       │   │
│  │  - Invite      │  │  - Multi-tenancy │  │  - PermissionGate    │   │
│  │  - Edit ROLES  │  │  - Switch context│  │  - Conditional render│   │
│  │  - Remove      │  └─────────────────┘  │  (permissions hidden)│   │
│  └────────────────┘                        └──────────────────────┘   │
└───────────────────────────────────────────────────────────────────────┘
                                   │ HTTP
                                   ▼
┌───────────────────────────────────────────────────────────────────────┐
│                         API LAYER (FastAPI)                            │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  Authentication Middleware                                        │ │
│  │  - Validate JWT from Cognito                                     │ │
│  │  - Extract user_id, email                                        │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                   │                                    │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  Authorization Layer (Permission-Based!)                         │ │
│  │  1. Get user's role (account or project level)                  │ │
│  │  2. Get permissions for role from cache                         │ │
│  │  3. Check if specific permission exists (e.g., "project.create")│ │
│  │  4. Allow/Deny request                                          │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                   │                                    │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  Endpoints (decorated with @require_permission)                  │ │
│  │  POST   /v1/admin/projects          @require_permission(         │ │
│  │                                        "project.create")          │ │
│  │  PATCH  /v1/admin/projects/{id}     @require_permission(         │ │
│  │                                        "project.write")           │ │
│  │  DELETE /v1/admin/projects/{id}     @require_permission(         │ │
│  │                                        "project.delete")          │ │
│  │  POST   /v1/admin/plans/{id}/approve @require_permission(        │ │
│  │                                        "plan.approve")            │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌───────────────────────────────────────────────────────────────────────┐
│                     DATA LAYER (PostgreSQL)                            │
│  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ permissions  │  │role_        │  │account_users │  │resource_   │ │
│  │- name        │  │permissions  │  │- account_id  │  │role_       │ │
│  │- resource    │  │- role       │  │- user_id     │  │assignments │ │
│  │- action      │  │- permission │  │- status      │  │- user_id   │ │
│  │              │  │  _id        │  │- added_by    │  │- resource_ │ │
│  │              │  │             │  │              │  │  type/id   │ │
│  │              │  │             │  │              │  │- role      │ │
│  └──────────────┘  └─────────────┘  └──────────────┘  └────────────┘ │
│         △                 △               ▲                  ▲         │
│         └─────────────────┘               │                  │         │
│         Defines which permissions         │                  │         │
│         each role has                     │                  │         │
│                                           │                  │         │
│        Membership only (no role) ─────────┘                  │         │
│        Roles assigned per resource ──────────────────────────┘         │
└───────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌───────────────────────────────────────────────────────────────────────┐
│                  CACHING LAYER (cachetools - In-Memory)                │
│  @cached(cache=TTLCache, ttl=900)  - Role permissions (15 min)        │
│  @cached(cache=TTLCache, ttl=300)  - User roles (5 min)               │
│  Note: MVP uses in-memory cache; scale to Redis/Memcached later       │
└───────────────────────────────────────────────────────────────────────┘
```

---

## Core Design Principle

### Unified Resource-Role Model

**Key Design Decision**: All resources (account, project, agent, etc.) use the same role assignment model. No inheritance, no overrides - just "What role does this user have on THIS resource?"

```
┌──────────────────────────────────────────────────────────────┐
│ USER INTERFACE LAYER                                         │
│ "What users see and interact with"                           │
│                                                              │
│ Concepts: Roles (Owner, Manager, Viewer)                    │
│ Operations: Assign role, Change role, Remove user           │
└──────────────────────────────────────────────────────────────┘
                            ↕
┌──────────────────────────────────────────────────────────────┐
│ AUTHORIZATION LAYER                                          │
│ "How the system makes access control decisions"             │
│                                                              │
│ Concepts: Permissions (project.create, plan.approve)        │
│ Operations: Check permission, Get role on resource          │
└──────────────────────────────────────────────────────────────┘
                            ↕
┌──────────────────────────────────────────────────────────────┐
│ DATA LAYER                                                   │
│ "How permissions are stored and mapped"                     │
│                                                              │
│ Tables: permissions, role_permissions, account_users,       │
│         resource_role_assignments (unified for all resources)│
│ Relationships: role → permissions (many-to-many)            │
└──────────────────────────────────────────────────────────────┘
```

**Core Principles:**
1. **Account membership ≠ permissions** - Being added to an account grants access, not permissions
2. **All resources are equal** - Account, project, agent all use same role assignment table
3. **Role per resource** - Users have roles on specific resources (including account itself)
4. **No inheritance or overrides** - Simple lookup: "What's your role on this resource?"

**Why This Matters:**
- Extremely simple and consistent model
- No complex permission resolution logic
- Easy to understand: "What's my role on this thing?"
- Flexible: Can assign different roles to different resources
- Performant: Single table lookup
- Adding new permissions doesn't require code deployment

---

## Data Models

### Entity Relationship Diagram

```
┌──────────────────┐
│   permissions    │
│──────────────────│
│ id (PK)          │◄──────┐
│ name (UNIQUE)    │       │
│ resource_type    │       │
│ action           │       │
│ display_name     │       │
│ description      │       │
└──────────────────┘       │
                           │
┌──────────────────┐       │
│ role_permissions │       │
│──────────────────│       │
│ id (PK)          │       │
│ role (ENUM)      │       │
│ permission_id    ├───────┘
│ (FK)             │
└──────────────────┘
         │
         │ Maps role to permissions
         │
         ▼
┌─────────────────────────┐       ┌──────────────────────────────┐
│    account_users        │       │ resource_role_assignments    │
│─────────────────────────│       │──────────────────────────────│
│ id (PK)                 │       │ id (PK)                      │
│ account_id (FK)         │       │ user_id (FK)                 │
│ user_id (FK)            │       │ account_id (FK)              │
│ added_by                │       │ resource_type (account,      │
│ added_at                │       │   project, agent, etc.)      │
│ status                  │       │ resource_id (UUID)           │
└─────────────────────────┘       │ role (ENUM)                  │
         ▲                         │ assigned_by                  │
         │                         │ assigned_at                  │
         │                         └──────────────────────────────┘
         │
    Membership only                Unified table for ALL resources
    (no role column)               (account, project, agent, etc.)
```

### Database Schema

#### 1. `permissions` Table

```sql
CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,  -- e.g., "project.create"
    resource_type VARCHAR(50) NOT NULL,  -- e.g., "project"
    action VARCHAR(50) NOT NULL,         -- e.g., "create"
    display_name VARCHAR(100) NOT NULL,  -- e.g., "Create Projects"
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT permissions_name_format CHECK (name ~ '^[a-z_]+\.[a-z_]+$')
);

CREATE UNIQUE INDEX idx_permissions_name ON permissions(name);
CREATE INDEX idx_permissions_resource_action ON permissions(resource_type, action);
```

**Naming Convention**: `{resource}.{action}`
- Examples: `account.read`, `project.create`, `agent.delete`, `plan.approve`, `data.export`
- Special case: `*` represents all permissions (for Owner role)

#### 2. `role_permissions` Table

```sql
CREATE TYPE user_role AS ENUM ('owner', 'manager', 'viewer');

CREATE TABLE role_permissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    role user_role NOT NULL,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_role_permission UNIQUE(role, permission_id)
);

CREATE INDEX idx_role_permissions_role ON role_permissions(role);
CREATE INDEX idx_role_permissions_permission ON role_permissions(permission_id);
```

#### 3. `account_users` Table

Stores user memberships in accounts. **Membership alone grants NO permissions** - users must be assigned roles on resources via `resource_role_assignments`.

```sql
CREATE TYPE account_user_status AS ENUM ('pending', 'active', 'deactivated');

CREATE TABLE account_users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Audit trail (nullable for self-onboarding)
    added_by UUID REFERENCES users(id),
    added_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Status tracking
    status account_user_status NOT NULL DEFAULT 'active',

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_account_user UNIQUE(account_id, user_id)
);

CREATE INDEX idx_account_users_user ON account_users(user_id);
CREATE INDEX idx_account_users_account ON account_users(account_id);
CREATE INDEX idx_account_users_status ON account_users(status);
CREATE INDEX idx_account_users_lookup ON account_users(user_id, account_id, status);
```

**Key Changes from Old Design:**
- ❌ Removed `account_role` column - roles are now in `resource_role_assignments`
- ✅ Changed `invited_by` to `added_by` (more generic - nullable for self-onboarding)
- ✅ Removed `invited_at` and `accepted_at` (moved to `user_invitations` table)
- ✅ Status defaults to 'active' instead of 'pending'

#### 4. `resource_role_assignments` Table

**NEW**: Unified table for ALL role assignments on ANY resource (account, project, agent, etc.).

```sql
CREATE TABLE resource_role_assignments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    resource_type VARCHAR(50) NOT NULL,  -- 'account', 'project', 'agent', etc.
    resource_id UUID NOT NULL,           -- ID of the specific resource
    role user_role NOT NULL,             -- 'owner', 'manager', 'viewer'

    -- Audit trail
    assigned_by UUID REFERENCES users(id),
    assigned_at TIMESTAMP NOT NULL DEFAULT NOW(),
    reason TEXT,                         -- Optional explanation

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_resource_role
        UNIQUE(user_id, account_id, resource_type, resource_id)
);

CREATE INDEX idx_resource_roles_user ON resource_role_assignments(user_id);
CREATE INDEX idx_resource_roles_resource ON resource_role_assignments(resource_type, resource_id);
CREATE INDEX idx_resource_roles_lookup ON resource_role_assignments(user_id, account_id, resource_type, resource_id);
CREATE INDEX idx_resource_roles_account ON resource_role_assignments(account_id);
```

**Design Notes:**
- **Unified for all resources** - No separate tables for `project_users`, `agent_users`, etc.
- **Account is a resource** - Use `resource_type='account', resource_id=account_id` for account-level roles
- **Project roles** - Use `resource_type='project', resource_id=project_id`
- **Agent roles** - Use `resource_type='agent', resource_id=agent_id`

**Examples:**

```sql
-- Alice has owner role on Account
INSERT INTO resource_role_assignments
(user_id, account_id, resource_type, resource_id, role, assigned_by)
VALUES
('alice-uuid', 'account-uuid', 'account', 'account-uuid', 'owner', NULL);

-- Bob has manager role on Project X
INSERT INTO resource_role_assignments
(user_id, account_id, resource_type, resource_id, role, assigned_by)
VALUES
('bob-uuid', 'account-uuid', 'project', 'project-x-uuid', 'manager', 'alice-uuid');

-- Carol has viewer role on Agent Z
INSERT INTO resource_role_assignments
(user_id, account_id, resource_type, resource_id, role, assigned_by)
VALUES
('carol-uuid', 'account-uuid', 'agent', 'agent-z-uuid', 'viewer', 'alice-uuid');
```

#### 5. `user_invitations` Table

Tracks team member invitations. The `account_role` field specifies the role to assign when the invitation is accepted.

```sql
CREATE TYPE invitation_status AS ENUM ('pending', 'accepted', 'expired', 'revoked');

CREATE TABLE user_invitations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    account_role user_role NOT NULL,  -- Role to assign on acceptance
    invited_by UUID NOT NULL REFERENCES users(id),
    invitation_token VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    accepted_at TIMESTAMP,
    status invitation_status NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_expiry CHECK (expires_at > created_at)
);

CREATE UNIQUE INDEX idx_invitations_token ON user_invitations(invitation_token);
CREATE INDEX idx_invitations_email ON user_invitations(email);
CREATE INDEX idx_invitations_account ON user_invitations(account_id);
CREATE INDEX idx_invitations_status ON user_invitations(status);
```

**Invitation Acceptance Flow:**

When an invitation is accepted, two records are created:
1. **Account membership** - Insert into `account_users` (grants access to account)
2. **Role assignment** - Insert into `resource_role_assignments` with `resource_type='account'` and `resource_id=account_id` (grants permissions via role)

### SQLAlchemy Models

```python
from sqlalchemy import Column, String, ForeignKey, Enum, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import relationship
import enum

class UserRole(str, enum.Enum):
    OWNER = "owner"
    MANAGER = "manager"
    VIEWER = "viewer"

class Permission(Base):
    __tablename__ = "permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    name = Column(String(100), nullable=False, unique=True)
    resource_type = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False)
    display_name = Column(String(100), nullable=False)
    description = Column(String)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))

    __table_args__ = (
        CheckConstraint("name ~ '^[a-z_]+\\.[a-z_]+$'", name="permissions_name_format"),
    )

class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    role = Column(Enum(UserRole), nullable=False)
    permission_id = Column(UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))

    permission = relationship("Permission", backref="role_mappings")

    __table_args__ = (
        UniqueConstraint("role", "permission_id", name="unique_role_permission"),
    )

class AccountUser(Base):
    """
    User membership in an account.

    Membership alone grants NO permissions - users must be assigned
    roles on resources via ResourceRoleAssignment.
    """
    __tablename__ = "account_users"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Audit trail (nullable for self-onboarding)
    added_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    added_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))

    # Status tracking
    status = Column(Enum(AccountUserStatus), nullable=False, server_default="active")

    # Timestamps
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))
    updated_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"), onupdate=text("NOW()"))

    account = relationship("Account", backref="members")
    user = relationship("User", foreign_keys=[user_id], backref="account_memberships")
    adder = relationship("User", foreign_keys=[added_by])

    __table_args__ = (
        UniqueConstraint("account_id", "user_id", name="unique_account_user"),
    )


class ResourceRoleAssignment(Base):
    """
    Role assignment for a user on a specific resource.

    Unified table for ALL resource types (account, project, agent, etc.).
    """
    __tablename__ = "resource_role_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    resource_type = Column(String(50), nullable=False)  # 'account', 'project', 'agent', etc.
    resource_id = Column(UUID(as_uuid=True), nullable=False)  # ID of the specific resource
    role = Column(Enum(UserRole), nullable=False)  # 'owner', 'manager', 'viewer'

    # Audit trail
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    assigned_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))
    reason = Column(Text)  # Optional explanation

    # Timestamps
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"))
    updated_at = Column(TIMESTAMP, nullable=False, server_default=text("NOW()"), onupdate=text("NOW()"))

    user = relationship("User", foreign_keys=[user_id], backref="role_assignments")
    account = relationship("Account", backref="role_assignments")
    assigner = relationship("User", foreign_keys=[assigned_by])

    __table_args__ = (
        UniqueConstraint("user_id", "account_id", "resource_type", "resource_id", name="unique_resource_role"),
    )
```

---

## Authorization Framework

### Permission Resolution Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. AUTHENTICATE                                              │
│    Extract user_id, account_id from JWT token               │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. GET USER'S ROLE ON RESOURCE                               │
│    Query resource_role_assignments:                          │
│      WHERE user_id = {user_id}                               │
│        AND account_id = {account_id}                         │
│        AND resource_type = {resource_type}                   │
│        AND resource_id = {resource_id}                       │
│    Returns: role (owner, manager, viewer) or None            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. GET ROLE PERMISSIONS (CACHED)                            │
│    Cache key: permissions:{role}                             │
│    Query: SELECT p.name FROM permissions p                   │
│           JOIN role_permissions rp ON p.id = rp.permission_id│
│           WHERE rp.role = {role}                             │
│    Returns: Set of permission names                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. CHECK PERMISSION                                          │
│    if required_permission in permissions:                    │
│        ALLOW                                                 │
│    else:                                                     │
│        DENY (403 Forbidden)                                  │
└─────────────────────────────────────────────────────────────┘
```

### Core Functions

#### `get_user_role_on_resource()`

```python
from cachetools import cached, TTLCache
from cachetools.keys import hashkey
import threading

# Cache for user resource roles: max 10,000 entries, 5 minute TTL
user_resource_role_cache = TTLCache(maxsize=10000, ttl=300)
user_resource_role_lock = threading.RLock()

@cached(cache=user_resource_role_cache,
        key=lambda user_id, account_id, resource_type, resource_id:
            hashkey(user_id, account_id, resource_type, resource_id),
        lock=user_resource_role_lock)
def get_user_role_on_resource(
    user_id: UUID,
    account_id: UUID,
    resource_type: str,
    resource_id: UUID
) -> Optional[UserRole]:
    """
    Get user's role on a specific resource.

    Args:
        user_id: User's ID
        account_id: Account context
        resource_type: Type of resource ('account', 'project', 'agent', etc.)
        resource_id: ID of the specific resource

    Returns:
        UserRole if user has a role on this resource, None otherwise

    Note: Uses in-memory cache with 5-minute TTL for MVP.
    """
    # First verify user is a member of the account
    account_user = db.query(AccountUser).filter_by(
        user_id=user_id,
        account_id=account_id,
        status=AccountUserStatus.ACTIVE
    ).first()

    if not account_user:
        raise HTTPException(403, "User does not have access to this account")

    # Get user's role on the specific resource
    role_assignment = db.query(ResourceRoleAssignment).filter_by(
        user_id=user_id,
        account_id=account_id,
        resource_type=resource_type,
        resource_id=resource_id
    ).first()

    if not role_assignment:
        return None  # User has no role on this resource

    return role_assignment.role
```

#### `get_role_permissions()`

```python
# Cache for role permissions: max 10 entries (3 roles), 15 minute TTL
role_permissions_cache = TTLCache(maxsize=10, ttl=900)
role_permissions_lock = threading.RLock()

@cached(cache=role_permissions_cache,
        key=lambda role: hashkey(role.value),
        lock=role_permissions_lock)
def get_role_permissions(role: UserRole) -> Set[str]:
    """
    Get all permissions for a given role.
    Returns a set of permission names (e.g., {"project.create", "agent.read"}).

    Note: Uses in-memory cache with 15-minute TTL for MVP.
    """
    # Special case: Owner has all permissions
    if role == UserRole.OWNER:
        return {"*"}  # Wildcard = all permissions

    # Query database
    permissions = db.query(Permission.name).join(RolePermission).filter(
        RolePermission.role == role
    ).all()

    perm_set = {p.name for p in permissions}

    return perm_set
```

#### `check_permission()`

```python
def check_permission(
    user_id: UUID,
    account_id: UUID,
    permission_name: str,
    project_id: Optional[UUID] = None
) -> bool:
    """
    Check if user has a specific permission.
    """
    # Get effective role
    role = get_effective_role(user_id, account_id, project_id)

    # Get permissions for role
    permissions = get_role_permissions(role)

    # Check permission (wildcard * means all permissions)
    return "*" in permissions or permission_name in permissions
```

### Authorization Decorator

```python
from functools import wraps
from typing import Optional
from fastapi import HTTPException, Depends

def require_permission(permission_name: str):
    """
    Decorator to require a specific permission for an endpoint.

    Usage:
        @require_permission("project.create")
        async def create_project(user: UserContext, account_id: UUID):
            # User must have "project.create" permission
            pass
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract user context and IDs from function arguments
            user: UserContext = kwargs.get("user") or args[0]
            account_id: UUID = kwargs.get("account_id")
            project_id: Optional[UUID] = kwargs.get("project_id")

            # Check permission
            has_permission = check_permission(
                user.id,
                account_id,
                permission_name,
                project_id
            )

            if not has_permission:
                raise HTTPException(
                    status_code=403,
                    detail=f"Missing permission: {permission_name}"
                )

            return await func(*args, **kwargs)

        return wrapper
    return decorator
```

### FastAPI Dependency

```python
from fastapi import Depends, HTTPException
from typing import Annotated

class PermissionChecker:
    """
    FastAPI dependency for checking permissions.
    """
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    async def __call__(
        self,
        user: Annotated[UserContext, Depends(authenticate_user)],
        account_id: UUID,
        project_id: Optional[UUID] = None
    ):
        has_permission = check_permission(
            user.id,
            account_id,
            self.required_permission,
            project_id
        )

        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail=f"Missing permission: {self.required_permission}"
            )

        return user

# Usage in endpoints
@app.post("/v1/admin/projects")
async def create_project(
    user: Annotated[UserContext, Depends(PermissionChecker("project.create"))],
    account_id: UUID,
    data: ProjectCreate
):
    # User is guaranteed to have "project.create" permission
    pass
```

---

## API Design

### Team Management Endpoints

#### Invite Team Member

```python
POST /v1/admin/accounts/{account_id}/team/invite
Authorization: Bearer {jwt_token}
Permissions: account.team_manage

Request:
{
    "email": "alice@example.com",
    "account_role": "manager"  // Role to assign when invitation is accepted
}

Response: 200 OK
{
    "invitation_id": "uuid",
    "email": "alice@example.com",
    "account_role": "manager",  // Role to assign on acceptance
    "invitation_token": "secure-random-token",
    "expires_at": "2025-11-07T12:00:00Z",
    "status": "pending"
}
```

**Note**: When the invitation is accepted:
1. User is added to `account_users` (membership)
2. Role is assigned via `resource_role_assignments` with `resource_type='account'` and `resource_id=account_id`

#### List Team Members

```python
GET /v1/admin/accounts/{account_id}/team
Authorization: Bearer {jwt_token}
Permissions: account.read

Query Parameters:
- role: Filter by account-level role (owner, manager, viewer)
- status: Filter by membership status (active, deactivated)
- search: Search by name or email

Response: 200 OK
{
    "members": [
        {
            "user_id": "uuid",
            "email": "bob@example.com",
            "name": "Bob Smith",
            "account_role": "manager",  // From resource_role_assignments where resource_type='account'
            "status": "active",  // From account_users.status
            "added_at": "2025-01-15T10:00:00Z",
            "last_active": "2025-10-31T14:22:00Z",
            "resource_roles": [  // Additional roles on specific resources
                {
                    "resource_type": "project",
                    "resource_id": "uuid",
                    "resource_name": "Production",
                    "role": "viewer"
                }
            ]
        }
    ],
    "total": 42
}
```

**Implementation Note**: Query joins `account_users` (for membership status) with `resource_role_assignments` (for roles). The `account_role` is fetched from `resource_role_assignments` where `resource_type='account'` and `resource_id=account_id`.

#### Update Team Member Role

```python
PATCH /v1/admin/accounts/{account_id}/team/{user_id}
Authorization: Bearer {jwt_token}
Permissions: account.team_manage

Request:
{
    "account_role": "viewer"  // Change account-level role
}

Response: 200 OK
{
    "user_id": "uuid",
    "account_role": "viewer",
    "updated_at": "2025-10-31T14:30:00Z"
}
```

**Implementation Note**: Updates the user's role in `resource_role_assignments` where `resource_type='account'` and `resource_id=account_id`.

#### Remove Team Member

```python
DELETE /v1/admin/accounts/{account_id}/team/{user_id}
Authorization: Bearer {jwt_token}
Permissions: account.team_manage

Response: 204 No Content
```

**Implementation Note**: Removes user from account by:
1. Setting `account_users.status` to 'deactivated' (soft delete membership)
2. Deleting all role assignments from `resource_role_assignments` where `user_id` and `account_id` match

#### Assign Role on Project

```python
POST /v1/admin/projects/{project_id}/team/{user_id}/role
Authorization: Bearer {jwt_token}
Permissions: project.write

Request:
{
    "role": "viewer"  // Role to assign on this project
}

Response: 200 OK
{
    "project_id": "uuid",
    "user_id": "uuid",
    "role": "viewer",
    "resource_type": "project"
}
```

**Implementation Note**: Creates entry in `resource_role_assignments` with `resource_type='project'` and `resource_id=project_id`. User must already be a member of the account (exist in `account_users`).

### Invitation Endpoints

#### Accept Invitation

```python
POST /v1/invitations/accept
Authorization: Bearer {jwt_token}

Request:
{
    "invitation_token": "secure-random-token"
}

Response: 200 OK
{
    "account_id": "uuid",
    "account_name": "Acme Corp",
    "account_role": "manager",
    "message": "You've been added to Acme Corp as a Manager"
}
```

#### Get Invitation Details

```python
GET /v1/invitations/{token}

Response: 200 OK
{
    "account_name": "Acme Corp",
    "invited_by": "John Doe",
    "role": "manager",
    "expires_at": "2025-11-07T12:00:00Z",
    "status": "pending"
}
```

### User Context Endpoints

#### List User's Accounts

```python
GET /v1/users/me/accounts
Authorization: Bearer {jwt_token}

Response: 200 OK
{
    "accounts": [
        {
            "account_id": "uuid",
            "account_name": "Acme Corp",
            "role": "owner",
            "last_accessed": "2025-10-31T14:00:00Z"
        },
        {
            "account_id": "uuid",
            "account_name": "Client Inc",
            "role": "manager",
            "last_accessed": "2025-10-30T09:15:00Z"
        }
    ]
}
```

#### Switch Active Account

```python
POST /v1/users/me/switch-account
Authorization: Bearer {jwt_token}

Request:
{
    "account_id": "uuid"
}

Response: 200 OK
{
    "account_id": "uuid",
    "account_name": "Client Inc",
    "role": "manager"
}
```

---

## Caching Strategy

### Two-Tier In-Memory Caching Architecture (MVP)

**Note**: For MVP, we use `cachetools` for in-memory caching. This is simpler and requires no external dependencies.

**Limitations of In-Memory Caching**:
- ❌ Not shared across multiple application instances (each process has its own cache)
- ❌ Cache is lost on application restart
- ❌ Higher memory usage per instance compared to shared cache

**When to Migrate to Redis**:
- ✅ When running multiple application instances (horizontal scaling)
- ✅ When cache invalidation needs to be synchronized across instances
- ✅ When memory constraints become an issue
- ✅ When you need cache persistence across restarts

**Migration Path**: The caching code is designed to be easily swappable. When ready, replace `cachetools` decorators with Redis-based caching (e.g., `aiocache` or `redis-py`) without changing the authorization logic.

**Thread Safety**:
- ⚠️ `cachetools` caches are NOT thread-safe by default
- ✅ Use `threading.RLock()` with the `@cached` decorator's `lock` parameter
- ✅ Required for FastAPI/asyncio environments (multiple concurrent requests)

#### Tier 1: Role Permissions (Long-Lived)

**Purpose**: Cache the set of permissions for each role
**Implementation**: `TTLCache(maxsize=10, ttl=900)`
**TTL**: 15 minutes (900 seconds)
**Size**: Small cache (10 entries max, only 3 roles exist)
**Cache Key**: Role enum value

```python
from cachetools import TTLCache, cached
from cachetools.keys import hashkey
import threading

# Small cache for role permissions (only 3 roles)
# Note: Use threading.RLock() for thread-safety in async environments
role_permissions_cache = TTLCache(maxsize=10, ttl=900)
role_permissions_lock = threading.RLock()

@cached(cache=role_permissions_cache,
        key=lambda role: hashkey(role.value),
        lock=role_permissions_lock)
def get_role_permissions(role: UserRole) -> Set[str]:
    # ... implementation ...
    pass
```

**Invalidation Strategy**:
- Automatic TTL-based expiration (15 minutes)
- Manual invalidation when role_permissions table changes:
  ```python
  role_permissions_cache.clear()  # Clear entire cache
  # Or clear specific role:
  key = hashkey(UserRole.MANAGER.value)
  if key in role_permissions_cache:
      del role_permissions_cache[key]
  ```

#### Tier 2: User Roles (Medium-Lived)

**Purpose**: Cache the effective role for a user in a context
**Implementation**: `TTLCache(maxsize=10000, ttl=300)`
**TTL**: 5 minutes (300 seconds)
**Size**: 10,000 entries (handles up to 10k concurrent user-context combinations)
**Cache Key**: Tuple of (user_id, account_id, project_id)

```python
# Larger cache for user roles
user_role_cache = TTLCache(maxsize=10000, ttl=300)
user_role_lock = threading.RLock()

@cached(cache=user_role_cache,
        key=lambda user_id, account_id, project_id=None:
            hashkey(user_id, account_id, project_id or ''),
        lock=user_role_lock)
def get_effective_role(user_id, account_id, project_id=None):
    # ... implementation ...
    pass
```

**Invalidation Strategy**:
- Automatic TTL-based expiration (5 minutes)
- Manual invalidation when user's role changes:
  ```python
  # Simple approach for MVP: clear entire cache
  user_role_cache.clear()

  # More granular approach (if needed):
  # Note: This requires iterating over cache keys
  keys_to_delete = [k for k in user_role_cache.keys()
                    if k[0] == user_id]  # Find keys for specific user
  for key in keys_to_delete:
      del user_role_cache[key]
  ```

**Important for Multi-Instance Deployments**:
- ⚠️ Cache invalidation only affects the current process
- ⚠️ Other application instances will retain stale data until TTL expires
- ✅ For MVP with single instance: not an issue
- ✅ For production: migrate to Redis for distributed cache invalidation

### Cache Hit Rate Optimization

**Expected Hit Rates**:
- Role permissions: >99% (3 entries, rarely evicted due to small size and long TTL)
- User roles: >90% (users don't change accounts frequently; TTL-based eviction)

**Cache Warming**:

```python
async def warm_permission_cache():
    """Warm up the permission cache on application startup."""
    logger.info("Warming RBAC permission cache...")
    for role in UserRole:
        permissions = get_role_permissions(role)  # This will populate the cache
        logger.info(f"Cached permissions for {role.value}: {len(permissions)} permissions")
    logger.info("RBAC cache warming complete")

# Call this in your FastAPI startup event
@app.on_event("startup")
async def startup_event():
    await warm_permission_cache()
```

**Cache Size Monitoring**:

```python
def get_cache_stats():
    """Get current cache statistics for monitoring."""
    return {
        "role_permissions": {
            "size": len(role_permissions_cache),
            "maxsize": role_permissions_cache.maxsize,
            "ttl": role_permissions_cache.ttl
        },
        "user_roles": {
            "size": len(user_role_cache),
            "maxsize": user_role_cache.maxsize,
            "ttl": user_role_cache.ttl
        }
    }
```

### Cache Monitoring

**Note**: With cachetools, cache hits/misses are handled by the decorator. We can track cache sizes and provide statistics endpoints.

```python
from prometheus_client import Counter, Histogram, Gauge

# Metrics
permission_check_duration = Histogram('rbac_permission_check_seconds', 'Permission check duration')
cache_size = Gauge('rbac_cache_size', 'Current cache size', ['cache_type'])

@permission_check_duration.time()
def check_permission_with_metrics(user_id, account_id, permission, project_id=None):
    result = check_permission(user_id, account_id, permission, project_id)
    # Update cache size metrics
    cache_size.labels(cache_type='role_permissions').set(len(role_permissions_cache))
    cache_size.labels(cache_type='user_roles').set(len(user_role_cache))
    return result

# Optional: Add cache info endpoint for debugging
@app.get("/v1/admin/rbac/cache/stats")
async def get_rbac_cache_stats(user: UserContext):
    """Get RBAC cache statistics (admin only)."""
    return {
        "role_permissions_cache": {
            "current_size": len(role_permissions_cache),
            "max_size": role_permissions_cache.maxsize,
            "ttl_seconds": role_permissions_cache.ttl
        },
        "user_roles_cache": {
            "current_size": len(user_role_cache),
            "max_size": user_role_cache.maxsize,
            "ttl_seconds": user_role_cache.ttl
        }
    }
```

---

## Frontend Architecture

### React Hooks

#### `usePermissions()` Hook

```typescript
import { useMemo } from 'react';
import { useAuth } from './useAuth';

interface UsePermissionsReturn {
    hasPermission: (permission: string) => boolean;
    role: 'owner' | 'manager' | 'viewer';
    permissions: Set<string>;
}

export function usePermissions(
    accountId: string,
    projectId?: string
): UsePermissionsReturn {
    const { user } = useAuth();

    // Fetch user's role and permissions
    const { data } = useSWR(
        projectId
            ? `/v1/users/${user.id}/permissions?account_id=${accountId}&project_id=${projectId}`
            : `/v1/users/${user.id}/permissions?account_id=${accountId}`,
        fetcher
    );

    const hasPermission = useMemo(() => {
        return (permission: string) => {
            if (!data) return false;
            return data.permissions.includes('*') || data.permissions.includes(permission);
        };
    }, [data]);

    return {
        hasPermission,
        role: data?.role || 'viewer',
        permissions: new Set(data?.permissions || [])
    };
}
```

### UI Components

#### `<PermissionGate>` Component

```typescript
interface PermissionGateProps {
    permission: string;
    accountId: string;
    projectId?: string;
    fallback?: React.ReactNode;
    children: React.ReactNode;
}

export function PermissionGate({
    permission,
    accountId,
    projectId,
    fallback = null,
    children
}: PermissionGateProps) {
    const { hasPermission } = usePermissions(accountId, projectId);

    if (!hasPermission(permission)) {
        return <>{fallback}</>;
    }

    return <>{children}</>;
}

// Usage
<PermissionGate permission="project.create" accountId={accountId}>
    <Button onClick={createProject}>Create Project</Button>
</PermissionGate>
```

#### `<RoleSelector>` Component

```typescript
interface RoleSelectorProps {
    value: 'owner' | 'manager' | 'viewer';
    onChange: (role: string) => void;
    disabled?: boolean;
}

const ROLE_DESCRIPTIONS = {
    owner: 'Full access including team management and billing',
    manager: 'Can create and manage projects, agents, and approve plans',
    viewer: 'Read-only access to all data and configurations'
};

export function RoleSelector({ value, onChange, disabled }: RoleSelectorProps) {
    return (
        <Select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
            <option value="owner">
                Owner - {ROLE_DESCRIPTIONS.owner}
            </option>
            <option value="manager">
                Manager - {ROLE_DESCRIPTIONS.manager}
            </option>
            <option value="viewer">
                Viewer - {ROLE_DESCRIPTIONS.viewer}
            </option>
        </Select>
    );
}
```

---

## Security Considerations

### 1. Invitation Token Security

**Requirements**:
- Cryptographically secure random tokens (32+ bytes)
- Single-use tokens
- Time-limited (7 days expiration)
- Rate limiting (max 10 invitations per account per hour)

**Implementation**:

```python
import secrets

def generate_invitation_token() -> str:
    """Generate a secure random token for invitations."""
    return secrets.token_urlsafe(32)  # 256 bits of entropy
```

### 2. Permission Check Bypass Prevention

**Vulnerabilities to Prevent**:
- Direct parameter manipulation (changing user_id in request)
- Session fixation
- Role escalation

**Mitigations**:
- Always extract user_id from JWT, never from request parameters
- Validate account_id and project_id belong to user's accessible accounts
- Log all permission checks (audit trail)

```python
def authorize_request(user: UserContext, account_id: UUID):
    """Ensure user has access to the account before checking permissions."""
    # First, verify user has ANY role in the account
    account_user = db.query(AccountUser).filter_by(
        user_id=user.id,
        account_id=account_id,
        status=AccountUserStatus.ACTIVE
    ).first()

    if not account_user:
        raise HTTPException(403, "Access denied")

    # Then check specific permissions
    ...
```

### 3. Owner Role Protection

**Requirement**: At least one Owner must exist per account

**Implementation**:

```python
def remove_team_member(account_id: UUID, user_id: UUID, requesting_user: UserContext):
    """Remove a team member with safeguards."""
    # Get user's account membership
    account_user = db.query(AccountUser).filter_by(
        account_id=account_id,
        user_id=user_id
    ).first()

    if not account_user:
        raise HTTPException(404, "User is not a member of this account")

    # Check if user has owner role on account
    owner_role = db.query(ResourceRoleAssignment).filter_by(
        user_id=user_id,
        account_id=account_id,
        resource_type='account',
        resource_id=account_id,
        role=UserRole.OWNER
    ).first()

    if owner_role:
        # Count remaining owners on the account
        owner_count = db.query(ResourceRoleAssignment).filter_by(
            account_id=account_id,
            resource_type='account',
            resource_id=account_id,
            role=UserRole.OWNER
        ).join(AccountUser).filter(
            AccountUser.status == AccountUserStatus.ACTIVE
        ).count()

        if owner_count <= 1:
            raise HTTPException(
                400,
                "Cannot remove the last owner from the account"
            )

    # Proceed with removal
    # 1. Deactivate membership
    account_user.status = AccountUserStatus.DEACTIVATED

    # 2. Remove all role assignments for this user in this account
    db.query(ResourceRoleAssignment).filter_by(
        user_id=user_id,
        account_id=account_id
    ).delete()

    db.commit()

    # Invalidate user's resource role cache
    # Note: With cachetools, we clear all entries for simplicity (MVP approach)
    # For production, consider more granular invalidation or migrate to Redis
    from src.auth.rbac.cache import clear_user_resource_role_cache
    clear_user_resource_role_cache(user_id=str(user_id))
```

### 4. Audit Logging

**Events to Log**:
- Role changes (who, when, what changed)
- Team member additions/removals
- Permission checks (failures only, for security monitoring)
- Invitation sends and acceptances

```python
from models import AuditLog

def log_role_change(
    account_id: UUID,
    target_user_id: UUID,
    changed_by: UUID,
    old_role: UserRole,
    new_role: UserRole
):
    """Log role change for audit trail."""
    audit_log = AuditLog(
        account_id=account_id,
        event_type="role_changed",
        actor_id=changed_by,
        target_user_id=target_user_id,
        details={
            "old_role": old_role.value,
            "new_role": new_role.value
        }
    )
    db.add(audit_log)
    db.commit()
```

---

## Performance Requirements

### Latency Targets

| Operation | Target | Measurement |
|-----------|--------|-------------|
| Permission check (cache hit) | <10ms | p99 |
| Permission check (cache miss) | <50ms | p99 |
| Get role permissions | <5ms | p99 (cached) |
| List team members (100 users) | <500ms | p95 |
| Invite team member | <200ms | p95 |

### Database Query Optimization

#### Index Strategy

```sql
-- Essential indexes for permission checks
CREATE INDEX idx_account_users_lookup ON account_users(user_id, account_id, status);
CREATE INDEX idx_resource_roles_lookup ON resource_role_assignments(user_id, account_id, resource_type, resource_id);
CREATE INDEX idx_role_permissions_lookup ON role_permissions(role, permission_id);

-- Indexes for team management queries
CREATE INDEX idx_account_users_account ON account_users(account_id, status);
CREATE INDEX idx_resource_roles_account ON resource_role_assignments(account_id, resource_type);
CREATE INDEX idx_invitations_account_status ON user_invitations(account_id, status);
```

**Note**: Removed `account_role` from account_users indexes since that column no longer exists. Role information is now in `resource_role_assignments`.

#### Query Patterns

**Anti-Pattern** (N+1 query):

```python
# BAD: Separate query for each user's role
for user in users:
    role = db.query(ResourceRoleAssignment).filter_by(
        user_id=user.id,
        resource_type='account',
        resource_id=account_id
    ).first()
```

**Optimized** (single query with joins):

```python
# GOOD: Fetch all users with account-level roles in one query
users_with_roles = db.query(
    User,
    AccountUser.status,
    ResourceRoleAssignment.role
).join(
    AccountUser, User.id == AccountUser.user_id
).outerjoin(
    ResourceRoleAssignment,
    and_(
        User.id == ResourceRoleAssignment.user_id,
        ResourceRoleAssignment.resource_type == 'account',
        ResourceRoleAssignment.resource_id == account_id
    )
).filter(
    AccountUser.account_id == account_id,
    AccountUser.status == AccountUserStatus.ACTIVE
).all()
```

**Note**: Use `outerjoin` for `resource_role_assignments` to include users who are members but don't have a role assigned yet.

### Load Testing Targets

```bash
# Target: 1000 requests/second for permission checks
hey -n 10000 -c 100 -m POST \
    -H "Authorization: Bearer $TOKEN" \
    http://localhost:8000/v1/admin/projects

# Success criteria:
# - p99 latency < 50ms
# - Error rate < 0.1%
# - No cache stampede
```

---

## Implementation Plan

### Phase 1: Foundation (Weeks 1-2)

**Database Setup**:
- [ ] Create migration scripts for all new tables
- [ ] Add seed data for default permissions
- [ ] Create indexes for performance
- [ ] Write migration to populate `account_users` from existing data

**Permissions Seed Data**:

```sql
-- Seed default permissions
INSERT INTO permissions (name, resource_type, action, display_name, description) VALUES
-- Account permissions
('account.read', 'account', 'read', 'View Account', 'View account settings and information'),
('account.write', 'account', 'write', 'Modify Account', 'Modify account settings'),
('account.billing.read', 'account', 'billing_read', 'View Billing', 'View billing information'),
('account.billing.write', 'account', 'billing_write', 'Modify Billing', 'Modify billing settings'),
('account.team_manage', 'account', 'team_manage', 'Manage Team', 'Invite and remove team members'),

-- Project permissions
('project.create', 'project', 'create', 'Create Projects', 'Create new projects'),
('project.read', 'project', 'read', 'View Projects', 'View project configurations'),
('project.write', 'project', 'write', 'Modify Projects', 'Modify project settings'),
('project.delete', 'project', 'delete', 'Delete Projects', 'Delete projects'),

-- Agent permissions
('agent.create', 'agent', 'create', 'Create Agents', 'Create new agents'),
('agent.read', 'agent', 'read', 'View Agents', 'View agent configurations'),
('agent.write', 'agent', 'write', 'Modify Agents', 'Modify agent settings'),
('agent.delete', 'agent', 'delete', 'Delete Agents', 'Delete agents'),

-- Plan permissions
('plan.approve', 'plan', 'approve', 'Approve Plans', 'Approve automated plans'),

-- Data permissions
('data.export', 'data', 'export', 'Export Data', 'Export data and reports');

-- Map permissions to roles
-- Owner: All permissions (represented by wildcard in code)
INSERT INTO role_permissions (role, permission_id)
SELECT 'owner', id FROM permissions;

-- Manager: All except billing and team management
INSERT INTO role_permissions (role, permission_id)
SELECT 'manager', id FROM permissions WHERE name IN (
    'account.read',
    'project.create', 'project.read', 'project.write', 'project.delete',
    'agent.create', 'agent.read', 'agent.write', 'agent.delete',
    'plan.approve',
    'data.export'
);

-- Viewer: Read-only permissions
INSERT INTO role_permissions (role, permission_id)
SELECT 'viewer', id FROM permissions WHERE name IN (
    'account.read',
    'project.read',
    'agent.read',
    'data.export'
);
```

**Code Infrastructure**:
- [ ] Add `cachetools` dependency (`pip install cachetools`)
- [ ] Create SQLAlchemy models
- [ ] Write repository layer for data access
- [ ] Set up cache instances (TTLCache for roles and permissions)
- [ ] Implement cache warming on startup
- [ ] Unit tests for all models and repositories

### Phase 2: Authorization Backend (Weeks 3-4)

**Core Functions**:
- [ ] Implement `get_effective_role()` with cachetools
- [ ] Implement `get_role_permissions()` with cachetools
- [ ] Implement `check_permission()`
- [ ] Set up TTL caches with appropriate sizes (MVP: in-memory only)

**Decorators & Dependencies**:
- [ ] Create `@require_permission()` decorator
- [ ] Create `PermissionChecker` FastAPI dependency
- [ ] Update existing endpoints to use new decorators

**Endpoint Updates**:

```python
# Before
@app.post("/v1/admin/projects")
async def create_project(user: UserContext):
    pass

# After
@app.post("/v1/admin/projects")
async def create_project(
    user: Annotated[UserContext, Depends(PermissionChecker("project.create"))]
):
    pass
```

**Testing**:
- [ ] Unit tests for permission resolution
- [ ] Integration tests for each permission
- [ ] Performance tests (target: <50ms p99)
- [ ] Security tests (bypass attempts)

### Phase 3: Team Management API (Weeks 5-6)

**Endpoints**:
- [ ] POST `/v1/admin/accounts/{id}/team/invite`
- [ ] GET `/v1/admin/accounts/{id}/team`
- [ ] GET `/v1/admin/accounts/{id}/team/{user_id}`
- [ ] PATCH `/v1/admin/accounts/{id}/team/{user_id}`
- [ ] DELETE `/v1/admin/accounts/{id}/team/{user_id}`
- [ ] POST `/v1/admin/projects/{id}/team/{user_id}/role`
- [ ] DELETE `/v1/admin/projects/{id}/team/{user_id}/role`

**Invitation Flow**:
- [ ] POST `/v1/invitations/accept`
- [ ] GET `/v1/invitations/{token}`
- [ ] Email service integration

**User Context**:
- [ ] GET `/v1/users/me/accounts`
- [ ] POST `/v1/users/me/switch-account`

### Phase 4: Frontend (Weeks 7-9)

**React Hooks & Components**:
- [ ] `usePermissions()` hook
- [ ] `<PermissionGate>` component
- [ ] `<RoleSelector>` component
- [ ] `<PermissionPreview>` component

**Pages**:
- [ ] Team members list (`/admin/team`)
- [ ] Invite member form (`/admin/team/invite`)
- [ ] Edit member permissions (`/admin/team/{id}/edit`)
- [ ] Account switcher dropdown

### Phase 5: Testing & Launch (Weeks 10-12)

**Testing**:
- [ ] End-to-end tests (Playwright)
- [ ] Load testing (1000 req/s target)
- [ ] Security audit
- [ ] UAT with 2-3 beta customers

**Launch**:
- [ ] Feature flag rollout (beta → 25% → 50% → 100%)
- [ ] Monitor error rates and latency
- [ ] Document rollback procedure

---

## Testing Strategy

### Unit Tests

```python
# test_authorization.py

def test_get_role_permissions_owner():
    """Owner should have wildcard permission."""
    perms = get_role_permissions(UserRole.OWNER)
    assert "*" in perms

def test_get_role_permissions_manager():
    """Manager should have project and agent permissions."""
    perms = get_role_permissions(UserRole.MANAGER)
    assert "project.create" in perms
    assert "agent.write" in perms
    assert "account.billing.read" not in perms

def test_get_role_permissions_viewer():
    """Viewer should only have read permissions."""
    perms = get_role_permissions(UserRole.VIEWER)
    assert "project.read" in perms
    assert "project.create" not in perms

def test_get_effective_role_account_level():
    """Should return account-level role when no project override."""
    role = get_effective_role(user_id, account_id)
    assert role == UserRole.MANAGER

def test_get_effective_role_project_override():
    """Should return project-level role when override exists."""
    # Setup: user is Manager at account level, Viewer for specific project
    role = get_effective_role(user_id, account_id, project_id)
    assert role == UserRole.VIEWER

def test_check_permission_granted():
    """Should allow when user has permission."""
    assert check_permission(user_id, account_id, "project.create") == True

def test_check_permission_denied():
    """Should deny when user lacks permission."""
    assert check_permission(user_id, account_id, "account.billing.read") == False
```

### Integration Tests

```python
# test_api_authorization.py

@pytest.mark.asyncio
async def test_create_project_as_manager():
    """Manager should be able to create projects."""
    response = await client.post(
        "/v1/admin/projects",
        json={"name": "Test Project"},
        headers=auth_headers(role="manager")
    )
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_create_project_as_viewer():
    """Viewer should NOT be able to create projects."""
    response = await client.post(
        "/v1/admin/projects",
        json={"name": "Test Project"},
        headers=auth_headers(role="viewer")
    )
    assert response.status_code == 403
    assert "project.create" in response.json()["detail"]

@pytest.mark.asyncio
async def test_invite_team_member_as_owner():
    """Owner should be able to invite team members."""
    response = await client.post(
        f"/v1/admin/accounts/{account_id}/team/invite",
        json={"email": "alice@example.com", "account_role": "manager"},
        headers=auth_headers(role="owner")
    )
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_invite_team_member_as_manager():
    """Manager should NOT be able to invite team members."""
    response = await client.post(
        f"/v1/admin/accounts/{account_id}/team/invite",
        json={"email": "alice@example.com", "account_role": "manager"},
        headers=auth_headers(role="manager")
    )
    assert response.status_code == 403
```

### Performance Tests

```python
# test_performance.py

def test_permission_check_latency():
    """Permission checks should complete in <50ms (p99)."""
    latencies = []

    for _ in range(1000):
        start = time.time()
        check_permission(user_id, account_id, "project.create")
        latencies.append(time.time() - start)

    p99 = np.percentile(latencies, 99)
    assert p99 < 0.05, f"p99 latency: {p99*1000:.2f}ms (target: <50ms)"

def test_cache_hit_rate():
    """Role permissions should have >95% cache hit rate."""
    # Warm up cache
    for role in UserRole:
        get_role_permissions(role)

    # Measure hits
    hits = 0
    total = 1000

    for _ in range(total):
        # Random role
        role = random.choice(list(UserRole))
        # This should hit cache
        get_role_permissions(role)
        if redis_hit:
            hits += 1

    hit_rate = hits / total
    assert hit_rate > 0.95, f"Cache hit rate: {hit_rate:.2%} (target: >95%)"
```

---

## Migration Strategy

### Backward Compatibility

**Goal**: Zero downtime migration with gradual rollout

**Strategy**:
1. Deploy new tables without changing existing endpoints
2. Backfill `account_users` from existing user-account relationships
3. Deploy new authorization code behind feature flag
4. Test with internal users
5. Gradually roll out to customers (beta → 25% → 50% → 100%)
6. Remove old authorization code after full rollout

### Migration Script

```python
# migrations/001_add_rbac_tables.py

def upgrade():
    # Create new tables
    create_permissions_table()
    create_role_permissions_table()
    create_account_users_table()
    create_resource_role_assignments_table()
    create_user_invitations_table()

    # Seed default permissions
    seed_permissions()
    seed_role_permissions()

    # Backfill account_users and resource_role_assignments from existing data
    backfill_account_data()

def backfill_account_data():
    """
    Populate account_users and resource_role_assignments tables from existing relationships.

    Step 1: Create account memberships (account_users)
    Step 2: Assign owner role on account resource (resource_role_assignments)

    Assumptions:
    - Existing users with role "Admin" → Skip (Palona internal)
    - Existing users with role "AccountManager" → Owner role on account
    """
    # Get all existing user-account relationships
    existing_relationships = db.execute("""
        SELECT DISTINCT u.id as user_id, a.id as account_id, u.created_at
        FROM users u
        JOIN user_accounts ua ON u.id = ua.user_id
        JOIN accounts a ON ua.account_id = a.id
        WHERE u.role = 'AccountManager'
    """).fetchall()

    # Step 1: Insert into account_users (membership only)
    for rel in existing_relationships:
        account_user = AccountUser(
            account_id=rel.account_id,
            user_id=rel.user_id,
            added_by=None,  # Self-onboarded
            added_at=rel.created_at or datetime.utcnow(),
            status=AccountUserStatus.ACTIVE
        )
        db.add(account_user)

    db.commit()
    logger.info(f"Backfilled {len(existing_relationships)} account memberships")

    # Step 2: Insert into resource_role_assignments (assign owner role on account)
    for rel in existing_relationships:
        role_assignment = ResourceRoleAssignment(
            user_id=rel.user_id,
            account_id=rel.account_id,
            resource_type='account',
            resource_id=rel.account_id,  # Account itself is the resource
            role=UserRole.OWNER,
            assigned_by=None,  # Self-assigned
            assigned_at=rel.created_at or datetime.utcnow()
        )
        db.add(role_assignment)

    db.commit()
    logger.info(f"Backfilled {len(existing_relationships)} account role assignments")

def downgrade():
    # Drop tables in reverse order (respecting foreign keys)
    drop_table("user_invitations")
    drop_table("resource_role_assignments")
    drop_table("account_users")
    drop_table("role_permissions")
    drop_table("permissions")
```

### Feature Flag

```python
from featureflags import is_enabled

def check_permission_v2(user_id, account_id, permission, project_id=None):
    """New permission-based authorization."""
    # ... new implementation ...

def check_permission_v1(user_id, account_id, role_required):
    """Old role-based authorization."""
    # ... old implementation ...

def authorize_request(user_id, account_id, permission):
    """Wrapper that uses feature flag to choose implementation."""
    if is_enabled("rbac_v2", account_id):
        return check_permission_v2(user_id, account_id, permission)
    else:
        # Map permission to old role check (temporary)
        role_required = permission_to_role_map.get(permission, "owner")
        return check_permission_v1(user_id, account_id, role_required)
```

---

## Monitoring & Observability

### Metrics to Track

```python
from prometheus_client import Counter, Histogram, Gauge

# Permission checks
permission_check_total = Counter(
    'rbac_permission_check_total',
    'Total permission checks',
    ['permission', 'granted']
)

permission_check_duration = Histogram(
    'rbac_permission_check_seconds',
    'Permission check duration',
    ['cache_hit']
)

# Cache metrics
cache_hits = Counter('rbac_cache_hits_total', 'Cache hits', ['cache_type'])
cache_misses = Counter('rbac_cache_misses_total', 'Cache misses', ['cache_type'])

# Team management
team_invitations_sent = Counter('rbac_invitations_sent_total', 'Invitations sent', ['account_id'])
team_invitations_accepted = Counter('rbac_invitations_accepted_total', 'Invitations accepted')
role_changes = Counter('rbac_role_changes_total', 'Role changes', ['from_role', 'to_role'])

# Active users per role
users_per_role = Gauge('rbac_users_per_role', 'Number of users per role', ['account_id', 'role'])
```

### Dashboards

**1. Authorization Performance**
- p50, p95, p99 latency for permission checks
- Cache hit rate (role permissions, user roles)
- Error rate (403 Forbidden responses)

**2. Team Management**
- Invitations sent per day
- Invitation acceptance rate
- Time to accept invitation (avg, median)
- Role distribution (% of users per role)

**3. System Health**
- Database query latency (account_users, role_permissions)
- Memory usage (cache size, Python process memory)
- Cache efficiency (cache size vs maxsize ratio)

### Alerts

```yaml
alerts:
  - name: HighPermissionCheckLatency
    condition: rbac_permission_check_seconds.p99 > 0.05
    for: 5m
    severity: warning
    description: "Permission check p99 latency is above 50ms"

  - name: CacheNearCapacity
    condition: rbac_cache_size{cache_type="user_roles"} / 10000 > 0.9
    for: 10m
    severity: warning
    description: "User roles cache is above 90% capacity (consider increasing maxsize or migrating to Redis)"

  - name: HighAuthorizationErrorRate
    condition: rate(http_requests_total{status="403"}[5m]) > 10
    for: 5m
    severity: critical
    description: "High rate of 403 Forbidden responses"
```

---

## Appendix

### Permission Naming Conventions

**Format**: `{resource}.{action}`

**Resources**:
- `account`: Account-level settings and configuration
- `project`: Project management
- `agent`: Agent configuration
- `plan`: Plan approval and execution
- `data`: Data export and reporting

**Actions**:
- `read`: View/read access
- `write`: Modify/update access
- `create`: Create new resources
- `delete`: Delete resources
- `approve`: Approve actions (e.g., plans)
- `export`: Export data
- Custom actions as needed (e.g., `billing_read`, `team_manage`)

**Examples**:
- `account.read`: View account settings
- `project.create`: Create new projects
- `agent.delete`: Delete agents
- `plan.approve`: Approve plans
- `account.team_manage`: Manage team members (invite, remove, change roles)

### Future Extensibility Examples

#### Adding a New Permission

```sql
-- 1. Add permission
INSERT INTO permissions (name, resource_type, action, display_name, description)
VALUES ('report.generate', 'report', 'generate', 'Generate Reports', 'Generate custom reports');

-- 2. Assign to roles
INSERT INTO role_permissions (role, permission_id)
SELECT 'manager', id FROM permissions WHERE name = 'report.generate';

INSERT INTO role_permissions (role, permission_id)
SELECT 'owner', id FROM permissions WHERE name = 'report.generate';

-- 3. Clear cache
REDIS: DEL permissions:manager permissions:owner
```

```python
# 4. Use in code
@app.post("/v1/admin/reports/generate")
async def generate_report(
    user: Annotated[UserContext, Depends(PermissionChecker("report.generate"))]
):
    # Implementation
    pass
```

**No code deployment needed!** Just database change and cache invalidation.

#### Migration from cachetools to Redis (Future)

When you need to scale to multiple instances, here's the migration path:

```python
# Before (cachetools - MVP)
from cachetools import TTLCache, cached
from cachetools.keys import hashkey

role_permissions_cache = TTLCache(maxsize=10, ttl=900)

@cached(cache=role_permissions_cache, key=lambda role: hashkey(role.value))
def get_role_permissions(role: UserRole) -> Set[str]:
    # ... implementation ...
    pass

# After (Redis - Production)
import redis
from functools import wraps
import json

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

def redis_cached(prefix: str, ttl: int):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key from function arguments
            cache_key = f"{prefix}:{':'.join(str(arg) for arg in args)}"

            # Check cache
            cached_value = redis_client.get(cache_key)
            if cached_value:
                return json.loads(cached_value)

            # Compute value
            result = func(*args, **kwargs)

            # Store in cache
            redis_client.setex(cache_key, ttl, json.dumps(result))

            return result
        return wrapper
    return decorator

@redis_cached(prefix="permissions", ttl=900)
def get_role_permissions(role: UserRole) -> Set[str]:
    # ... same implementation ...
    pass
```

**Migration Checklist**:
- [ ] Set up Redis instance (AWS ElastiCache, Redis Cloud, etc.)
- [ ] Update dependencies (`pip install redis`)
- [ ] Replace cachetools decorators with Redis caching wrapper
- [ ] Update cache invalidation logic to use Redis commands
- [ ] Test with multiple application instances
- [ ] Monitor Redis memory usage and connection pool
- [ ] Update documentation and deployment guides

---

## Document History

| Version | Date       | Author | Changes |
|---------|------------|--------|---------|
| 1.0     | 2025-10-31 | Engineering Lead | Initial technical design document |
| 1.1     | 2025-11-01 | Engineering Lead | Updated to use cachetools instead of Redis for MVP |

---

## V1 Implementation Simplification (Account-Level Only)

### Overview

For the initial v1 release, we simplify the implementation by only supporting **account-level role assignments**. This means:

- ✅ Users can have roles (Owner, Manager, Viewer) on their account
- ✅ All permission checks are at the account level
- ❌ No project-specific or agent-specific role overrides (yet)
- ✅ The data model remains unchanged - ready for future expansion

**Benefits:**
- Simpler v1 implementation and testing
- Faster time to market
- No schema changes needed for v2 - just code logic changes
- Clean migration path to granular permissions

### V1 Data Model Usage

The `resource_role_assignments` table stays exactly as designed. For v1, we only populate it with account-level assignments:

```sql
-- V1: Only account-level roles
INSERT INTO resource_role_assignments
(user_id, account_id, resource_type, resource_id, role, assigned_by)
VALUES
('alice-uuid', 'account-uuid', 'account', 'account-uuid', 'owner', NULL);

-- No project or agent level assignments in v1:
-- (resource_type='project' or 'agent' entries not created yet)
```

### V1 Authorization Implementation

#### Core Authorization Module

**File: `src/auth/rbac/authorization.py`**

```python
"""RBAC authorization functions (V1 - Account Level)."""

from typing import Set, Optional
from uuid import UUID
from cachetools import cached
from cachetools.keys import hashkey

from src.models.rbac.enums import UserRole
from src.repositories.rbac import (
    ResourceRoleAssignmentRepository,
    RolePermissionRepository,
)
from src.auth.rbac.cache import (
    role_permissions_cache,
    role_permissions_lock,
    user_resource_role_cache,
    user_resource_role_lock,
)


@cached(
    cache=user_resource_role_cache,
    key=lambda user_id, account_id: hashkey(str(user_id), str(account_id)),
    lock=user_resource_role_lock
)
def get_user_role_on_account(
    user_id: UUID,
    account_id: UUID,
    db_session
) -> Optional[UserRole]:
    """
    Get user's role on account (V1 - account-level only).

    Returns None if user has no role on account.
    """
    repo = ResourceRoleAssignmentRepository(db_session)

    # V1: Only check account-level role
    role = repo.get_role_for_resource(
        user_id=user_id,
        account_id=account_id,
        resource_type="account",
        resource_id=account_id
    )

    return role


@cached(
    cache=role_permissions_cache,
    key=lambda role: hashkey(role.value),
    lock=role_permissions_lock
)
def get_role_permissions(role: UserRole, db_session) -> Set[str]:
    """
    Get all permissions for a role (cached).

    Returns set of permission names (e.g., {"project.create", "agent.read"}).
    """
    # Special case: Owner has all permissions
    if role == UserRole.OWNER:
        return {"*"}

    repo = RolePermissionRepository(db_session)
    return repo.get_permission_names_for_role(role)


def check_permission(
    user_id: UUID,
    account_id: UUID,
    permission_name: str,
    db_session
) -> bool:
    """
    Check if user has permission on account (V1 - account-level only).

    Args:
        user_id: User ID
        account_id: Account ID
        permission_name: Permission to check (e.g., "project.create")
        db_session: Database session

    Returns:
        True if user has permission, False otherwise
    """
    # Get user's role on account
    role = get_user_role_on_account(user_id, account_id, db_session)

    if not role:
        return False

    # Get permissions for role
    permissions = get_role_permissions(role, db_session)

    # Check permission (wildcard * means all permissions)
    return "*" in permissions or permission_name in permissions
```

#### Permission Decorator

**File: `src/auth/rbac/decorators.py`**

```python
"""RBAC authorization decorators."""

from functools import wraps
from typing import Callable
from uuid import UUID

from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session

from src.auth.rbac.authorization import check_permission
from src.database import get_db
from src.auth.dependencies import get_current_user


class PermissionChecker:
    """
    FastAPI dependency for permission checking (V1 - account-level).

    Usage:
        @router.post("/projects")
        async def create_project(
            account_id: UUID,
            current_user = Depends(PermissionChecker("project.create")),
            db: Session = Depends(get_db)
        ):
            # Permission already checked
            pass
    """

    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    async def __call__(
        self,
        account_id: UUID,
        current_user = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Check if current user has required permission on account.

        Raises:
            HTTPException: 403 if permission denied
        """
        has_permission = check_permission(
            user_id=current_user.id,
            account_id=account_id,
            permission_name=self.required_permission,
            db_session=db
        )

        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail=f"Missing permission: {self.required_permission}"
            )

        return current_user
```

### V1 API Endpoint Examples

**File: `src/api/v1/admin/projects.py`**

```python
"""Project management endpoints with RBAC (V1 - account-level permissions)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from src.auth.rbac.decorators import PermissionChecker
from src.auth.dependencies import get_current_user
from src.database import get_db
from src.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse

router = APIRouter(prefix="/admin/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse)
async def create_project(
    account_id: UUID,
    project_data: ProjectCreate,
    current_user = Depends(PermissionChecker("project.create")),
    db: Session = Depends(get_db)
):
    """
    Create a new project.

    Requires: project.create permission on account
    V1: Checks account-level role only
    """
    # Permission already checked by PermissionChecker
    # Create project logic here
    ...


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    account_id: UUID,
    project_id: UUID,
    current_user = Depends(PermissionChecker("project.read")),
    db: Session = Depends(get_db)
):
    """
    Get project details.

    Requires: project.read permission on account
    V1: All users with project.read on account can view all projects
    """
    # Permission already checked
    ...


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    account_id: UUID,
    project_id: UUID,
    project_data: ProjectUpdate,
    current_user = Depends(PermissionChecker("project.write")),
    db: Session = Depends(get_db)
):
    """
    Update project settings.

    Requires: project.write permission on account
    V1: All users with project.write on account can edit all projects
    """
    # Permission already checked
    ...


@router.delete("/{project_id}")
async def delete_project(
    account_id: UUID,
    project_id: UUID,
    current_user = Depends(PermissionChecker("project.delete")),
    db: Session = Depends(get_db)
):
    """
    Delete a project.

    Requires: project.delete permission on account
    V1: All users with project.delete on account can delete all projects
    """
    # Permission already checked
    ...
```

### V1 Limitations

In v1, the following scenarios are **NOT** supported:

1. ❌ **Project-specific roles**: Cannot give someone "Manager" role on only Project X
2. ❌ **Agent-specific roles**: Cannot give someone "Viewer" role on only Agent Z
3. ❌ **Mixed permissions**: Cannot say "Alice is a Manager for projects but Viewer for agents"

**All permissions are account-wide:**
- If Alice has `project.write` permission → she can edit **all** projects in the account
- If Bob has `agent.delete` permission → he can delete **all** agents in the account

### V2 Migration Path

When ready to add project-level and agent-level permissions, the migration is straightforward:

#### 1. Update Authorization Function

**File: `src/auth/rbac/authorization.py`**

```python
def check_permission(
    user_id: UUID,
    account_id: UUID,
    permission_name: str,
    db_session,
    resource_type: Optional[str] = None,  # NEW in V2
    resource_id: Optional[UUID] = None    # NEW in V2
) -> bool:
    """
    Check if user has permission on resource.

    V2: Supports resource-specific roles with fallback to account-level.
    """
    # Default to account-level
    if not resource_type or not resource_id:
        resource_type = "account"
        resource_id = account_id

    repo = ResourceRoleAssignmentRepository(db_session)

    # Try resource-specific role first
    role = repo.get_role_for_resource(
        user_id=user_id,
        account_id=account_id,
        resource_type=resource_type,
        resource_id=resource_id
    )

    # Fallback to account-level role if no resource-specific role exists
    if not role and (resource_type != "account"):
        role = repo.get_role_for_resource(
            user_id=user_id,
            account_id=account_id,
            resource_type="account",
            resource_id=account_id
        )

    if not role:
        return False

    permissions = get_role_permissions(role, db_session)
    return "*" in permissions or permission_name in permissions
```

#### 2. Update Decorator

**File: `src/auth/rbac/decorators.py`**

```python
class PermissionChecker:
    """V2: Supports optional resource-specific checks."""

    def __init__(
        self,
        required_permission: str,
        resource_type: Optional[str] = None  # NEW in V2
    ):
        self.required_permission = required_permission
        self.resource_type = resource_type  # e.g., "project", "agent"

    async def __call__(
        self,
        account_id: UUID,
        resource_id: Optional[UUID] = None,  # NEW - project_id, agent_id, etc.
        current_user = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        has_permission = check_permission(
            user_id=current_user.id,
            account_id=account_id,
            permission_name=self.required_permission,
            resource_type=self.resource_type,  # NEW in V2
            resource_id=resource_id,  # NEW in V2
            db_session=db
        )

        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail=f"Missing permission: {self.required_permission}"
            )

        return current_user
```

#### 3. Update Endpoints (V2)

```python
@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    account_id: UUID,
    project_id: UUID,  # Will be passed to PermissionChecker
    project_data: ProjectUpdate,
    current_user = Depends(
        PermissionChecker("project.write", resource_type="project")  # NEW
    ),
    db: Session = Depends(get_db)
):
    """
    Update project settings.

    V2: Checks project-specific role, falls back to account-level role
    """
    # Permission already checked for THIS specific project
    ...
```

### V1 → V2 Migration Checklist

When implementing v2:

- [ ] Update `check_permission()` to accept optional `resource_type` and `resource_id`
- [ ] Add resource-specific role lookup with account-level fallback
- [ ] Update `PermissionChecker` to accept optional `resource_type`
- [ ] Update cache key generation to include resource_type and resource_id
- [ ] Update API endpoints to pass project_id/agent_id to PermissionChecker
- [ ] Create UI for assigning project-level and agent-level roles
- [ ] Add migration script to backfill existing account roles as needed
- [ ] Update tests to cover resource-specific permission scenarios
- [ ] Update documentation with v2 behavior

**No database schema changes required** - the `resource_role_assignments` table already supports v2!

### V1 Testing Strategy

#### Unit Tests

```python
def test_v1_account_level_permission_check():
    """Test account-level permission checking (V1)."""
    # Setup: Alice is Manager on account
    assign_account_role(alice.id, account.id, UserRole.MANAGER)

    # Managers have project.write
    assert check_permission(
        alice.id, account.id, "project.write", db_session
    ) == True

    # Managers don't have account.billing.write
    assert check_permission(
        alice.id, account.id, "account.billing.write", db_session
    ) == False


def test_v1_no_project_specific_roles():
    """Test that project-specific roles are not checked in V1."""
    # Setup: Alice is Manager on account
    assign_account_role(alice.id, account.id, UserRole.MANAGER)

    # Even if we manually create a project-specific role (shouldn't happen in V1)
    # the check_permission function doesn't look at it
    assign_project_role(alice.id, account.id, project_x.id, UserRole.VIEWER)

    # V1 only checks account-level role (Manager)
    assert check_permission(
        alice.id, account.id, "project.write", db_session
    ) == True  # Uses account-level Manager role, ignores project-level Viewer
```

#### Integration Tests

```python
@pytest.mark.asyncio
async def test_v1_api_permission_enforcement():
    """Test API permission enforcement (V1)."""
    # Setup: Bob is Viewer on account
    assign_account_role(bob.id, account.id, UserRole.VIEWER)

    # Bob can read projects
    response = await client.get(
        f"/v1/admin/projects/{project_id}",
        params={"account_id": account.id},
        headers=auth_headers(bob)
    )
    assert response.status_code == 200

    # Bob cannot create projects
    response = await client.post(
        "/v1/admin/projects",
        params={"account_id": account.id},
        json={"name": "New Project"},
        headers=auth_headers(bob)
    )
    assert response.status_code == 403
    assert "project.create" in response.json()["detail"]
```

### V1 Summary

**What V1 Includes:**
- ✅ Account-level role assignments (Owner, Manager, Viewer)
- ✅ Permission-based authorization (project.create, agent.write, etc.)
- ✅ Cached permission checks (<50ms p99)
- ✅ FastAPI dependency injection for permission checks
- ✅ Team management (invite, remove, change roles)
- ✅ Multi-account support (users can belong to multiple accounts)

**What V1 Excludes:**
- ❌ Project-specific role overrides
- ❌ Agent-specific role overrides
- ❌ Resource-level permission granularity

**What V1 Enables for V2:**
- ✅ Unified data model ready for expansion
- ✅ Clean API pattern that extends naturally
- ✅ No breaking changes needed for v2 migration
- ✅ Cache infrastructure supports resource-specific keys

---

## References

- [PRD: Role-Based Access Control](./PRD_RBAC.md)
- [Quick Reference: RBAC Architecture](./RBAC_ARCHITECTURE_QUICK_REF.md)
- [Current Authentication Analysis](./AUTHENTICATION_AUTHORIZATION_ANALYSIS.md)
