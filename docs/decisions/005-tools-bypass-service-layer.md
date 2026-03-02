# ADR-005: Tools Bypass Service Layer

> **Status:** Accepted
> **Date:** 2024-01-01
> **Decision makers:** _To be filled_

## Context

Tools run inside the agent context. If tools called services, it would create a circular dependency: agent → tools → services → agent. Additionally, tools need direct access to external APIs and repositories for data persistence.

## Decision

Tools bypass the service layer entirely and use repositories directly for data access. This avoids circular dependencies and gives tools the flexibility they need.

## Alternatives Considered

- **Tools call services** — Creates circular dependency: agent → tools → services → message_service → agent
- **Shared service layer for tools and API** — Would require extracting common logic, adding complexity without clear benefit
- **Tools have their own service layer** — Excessive abstraction for tool-specific data access needs

## Consequences

- **Easier:** Breaks the circular dependency, allows tools direct access to data and external APIs
- **Harder:** Tools cannot reuse business logic from services; some code duplication may occur

## Evidence

- `tools/CLAUDE.md` line 12: "Tools must be decoupled from services. It should only rely on repositories for data persistency"
