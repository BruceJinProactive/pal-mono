# Services

Business logic layer that orchestrates operations across repositories, enforces business rules, and provides clean interfaces for API endpoints.

## Core Principles

**Service Responsibilities:**

- Coordinate operations across multiple repositories
- Enforce business rules and validation
- Provide transaction boundaries

## Service Structure

**Simple Services:**

```tree
service_name/
├── __init__.py          # Service facade with __all__ exports
├── _implementation.py   # Private implementation (prefix with _)
└── schema.py            # Pydantic models
```

## Database Patterns

**No direct DB interaction:**

- **NEVER** execute raw SQL or ORM queries directly - always use repositories

**Session Management:**

- Never use global session state, always pass sessions explicitly to services
- Session-per-operation ensures proper transaction isolation

## Service Composition

**Avoiding Circular Dependencies:**

- Strictly follow API -> service -> DB
- Avoid having circular dependencies cross-importing service, alert when shared service is absolutely required

## Advanced Patterns

**Async only:**

- All services should be async, and exported in `__all__`

**Distributed Tracing:**

- use `traced("Agent Service Create Agent")` for Datadog tracing
