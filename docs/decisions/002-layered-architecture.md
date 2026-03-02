# ADR-002: Layered Architecture

> **Status:** Accepted
> **Date:** 2024-01-01
> **Decision makers:** Kelvin

## Context

The codebase needs clear separation of concerns to remain maintainable as it grows. FastAPI endpoints, business logic services, and database operations must have well-defined boundaries with unidirectional dependencies.

## Decision

The system follows a strict layered architecture: API → Services → Database. Dependencies flow in one direction only. This is enforced at CI using import-linter.

## Alternatives Considered

- **Hexagonal architecture (ports & adapters)** — More flexible but more boilerplate; team familiarity with layered approach was higher
- **Clean architecture** — Similar tradeoffs to hexagonal; layered is simpler to enforce with import-linter
- **No enforced boundaries** — Leads to spaghetti dependencies; rejected due to prior experience

## Consequences

- **Easier:** Predictable dependency flow, easier to reason about where code belongs, enforced by automated checks
- **Harder:** Rigid structure — some features require workarounds. For example, tools had to bypass this layer ([ADR-005](005-tools-bypass-service-layer.md)) because they run inside the agent context
