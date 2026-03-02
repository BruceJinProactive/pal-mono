# ADR-003: Repository Pattern

> **Status:** Accepted
> **Date:** 2024-01-01
> **Decision makers:** Kelvin

## Context

All database access must go through a consistent abstraction layer for testability, swappable backends, and consistent error handling. Raw SQL or direct ORM queries in services would couple business logic to implementation details.

## Decision

All data access uses the repository pattern. Each domain entity has a corresponding repository class in `db/repositories/` that encapsulates all database operations.

## Alternatives Considered

- **Active Record pattern** — Couples business logic to ORM; harder to test services in isolation
- **Direct ORM queries in services** — Scatters data access logic; no single place to add query optimizations or caching
- **CQRS (Command Query Responsibility Segregation)** — Overkill for current scale; repository pattern sufficient

## Consequences

- **Easier:** Services stay clean and testable; database logic is isolated; easier to mock in tests
- **Harder:** More boilerplate code upfront; repositories must be maintained alongside schema changes
