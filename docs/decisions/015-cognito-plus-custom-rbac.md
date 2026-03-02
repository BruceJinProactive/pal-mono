# ADR-015: Cognito + Custom RBAC

> **Status:** Accepted
> **Date:** 2025-11-01
> **Decision makers:** Jacob

## Context

The platform is multi-tenant with fine-grained authorization needs. AWS Cognito handles authentication (identity management) but is too limited for resource-level permissions within a multi-tenant environment.

## Decision

The platform uses Cognito for authentication (who you are) and custom RBAC for authorization (what you can do). Custom tables handle permissions: permission, role_permission, resource_role_assignment.

## Alternatives Considered

- **Cognito only** — Insufficient for multi-tenant resource-level permissions (account/project/agent hierarchy)
- **Auth0** — More powerful RBAC but higher cost and another vendor dependency
- **Custom auth from scratch** — Security risk; Cognito handles identity/tokens safely, custom RBAC handles authorization

## Consequences

- **Easier:** Fine-grained multi-tenant authorization; Cognito handles the complexity of identity management
- **Harder:** More complex auth stack; custom RBAC code must be maintained

## Evidence

- `docs/state/architecture.md` line 83 describes authentication
- `auth_service` handles authentication integration
- Database tables: permission, role_permission, resource_role_assignment
