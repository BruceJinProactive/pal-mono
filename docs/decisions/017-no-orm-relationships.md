# ADR-017: No ORM Relationships

> **Status:** Accepted
> **Date:** 2024-01-01
> **Decision makers:** _To be filled_

## Context

Following the decision to avoid foreign key constraints ([ADR-004](004-no-foreign-key-constraints.md)), using SQLAlchemy's relationship() would introduce ORM-level complexity with lazy loading, eager loading, and potential N+1 query issues. Explicit data fetching is more predictable.

## Decision

Tables use indexed columns but do not define SQLAlchemy relationship() objects. All joins are written explicitly in repository queries.

## Alternatives Considered

- **Full SQLAlchemy relationships with lazy loading** — N+1 query risk, implicit queries, harder to reason about performance
- **Eager loading relationships** — Memory overhead loading related objects that may not be needed
- **Relationships with explicit loading only** — Half-measure that still introduces SQLAlchemy relationship complexity

## Consequences

- **Easier:** No lazy loading bugs; explicit queries are clear and debuggable; predictable performance
- **Harder:** More manual join code in repositories; must explicitly fetch related data
