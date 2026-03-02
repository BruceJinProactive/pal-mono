# ADR-004: No Foreign Key Constraints

> **Status:** Accepted
> **Date:** 2024-01-01
> **Decision makers:** Kelvin

## Context

The multi-tenant system requires flexibility in schema migrations and data management. Foreign key constraints would add complexity to migrations and potentially block schema changes during the rapid development phase.

## Decision

Tables use indexed columns for relationships but without foreign key constraints. Referential integrity is enforced in application code rather than at the database level.

## Alternatives Considered

- **Full FK constraints with cascades** — Slower migrations, cascade complexity with multi-tenant data, harder to reorder migration chains
- **FK constraints without cascades** — Still constrains migration ordering and makes schema changes harder across tenants
- **Partial FKs (only critical relationships)** — Inconsistent; either enforce everywhere or nowhere

## Consequences

- **Easier:** Faster migrations, more flexible schema changes, no cascade-related issues
- **Harder:** Orphaned data is possible if application code has bugs; referential integrity must be carefully managed in code
