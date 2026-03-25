# ADR-009: Mem0ai for Conversational Memory

> **Status:** Accepted
> **Date:** 2024-01-01
> **Decision makers:** Kelvin, Jeff C, Shuo

## Context

The platform wanted a simple way to add persistent conversational memory without building a custom memory system from scratch. At the time, managed memory was the fastest path to test personalization across conversations and retain useful user context such as preferences and prior interactions.

This choice optimized for speed and low implementation overhead. Memory was useful, but it was not an area where the team wanted to spend early engineering effort on custom extraction, storage, relevance scoring, and retrieval infrastructure.

## Decision

The platform uses mem0ai as the initial provider for conversational memory.

mem0ai is the managed dependency used to persist and retrieve memory for user-personalization use cases, rather than building a custom memory system inside `pal-mono`.

## Alternatives Considered

- **Custom memory system (PostgreSQL-based)** — Rejected because it required building memory extraction, storage, and retrieval logic before the team knew how much memory would matter to the product.
- **No persistent memory** — Rejected because it removed the ability to explore cross-conversation personalization entirely.

## Consequences

- **Easier:** The team can add managed memory quickly and evaluate personalization without first building custom infrastructure.
- **Harder:** Conversational memory depends on an external service and gives the platform less control over the memory layer.

## Evidence

- `agent/memory/` contains the mem0-backed memory implementation.
- `agent/framework/agno.py` historically integrated that memory into the legacy agent path.
