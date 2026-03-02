# ADR-007: Agno to Pal-Agents Migration

> **Status:** Accepted
> **Date:** 2026-02-01
> **Decision makers:** Kelvin

## Context

Agno was the initial agent framework choice, but the team built a custom in-house framework (pal-agents) with PalAgent, Spec, and RuntimeContext designed specifically for LiveKit integration. This provides more control and customization than the third-party Agno solution.

## Decision

The platform is migrating from Agno to the pal-agents framework. Both frameworks coexist during the migration period.

## Alternatives Considered

- **LangChain / LangGraph** — Heavier framework with more abstractions than needed; vendor lock-in concerns
- **Build from scratch (no framework)** — pal-agents IS the from-scratch approach, purpose-built for this platform's needs

## Consequences

- **Easier:** Custom framework tailored to platform needs, better LiveKit integration
- **Harder:** Two agent frameworks to maintain during migration; ongoing maintenance of custom framework
