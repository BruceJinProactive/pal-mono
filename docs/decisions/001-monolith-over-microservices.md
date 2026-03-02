# ADR-001: Monolith over Microservices

> **Status:** Accepted
> **Date:** 2024-01-01
> **Decision makers:** Kelvin

## Context

The platform is a restaurant/food service conversational AI solution that needs to iterate quickly with a small team. Building a full microservices architecture would introduce significant operational complexity, deployment overhead, and require more personnel to manage.

## Decision

The system is built as a monolithic application with event-driven components. Synchronous operations happen within the monolith, while asynchronous workflows use AWS EventBridge for decoupling.

## Alternatives Considered

- **Microservices** — Operational complexity too high for team size; deployment overhead unjustified at current scale
- **Modular monolith with strict module boundaries** — Considered but EventBridge already provides sufficient decoupling for async flows
- **Serverless (Lambda-based)** — Cold start latency incompatible with real-time voice/chat streaming requirements

## Consequences

- **Easier:** Simpler deployment (single artifact), easier local development, simpler debugging across the full call stack
- **Harder:** Scaling individual components requires scaling the entire application; no fault isolation between features
