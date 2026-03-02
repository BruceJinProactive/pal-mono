# ADR-009: Mem0ai for Conversational Memory

> **Status:** Accepted
> **Date:** 2024-01-01
> **Decision makers:** Kelvin

## Context

The platform needs personalized memory across conversations — remembering user preferences, past interactions, and conversation context. Building a custom memory system from scratch would be time-consuming and error-prone.

## Decision

The platform uses mem0ai for conversational memory management. This is a managed service that provides memory persistence and retrieval optimized for AI applications.

## Alternatives Considered

- **Custom memory system (PostgreSQL-based)** — Significant engineering effort for memory extraction, relevance scoring, and retrieval
- **LangChain memory modules** — Tightly coupled to LangChain ecosystem; less flexible
- **No persistent memory** — Degrades user experience; restaurant customers expect personalization

## Consequences

- **Easier:** Managed solution with battle-tested memory management; faster time to market
- **Harder:** External dependency for a core platform feature; ongoing cost and vendor relationship
