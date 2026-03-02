# ADR-008: Multi-Provider LLM Support

> **Status:** Accepted
> **Date:** 2025-07-01
> **Decision makers:** Kelvin

## Context

Different tasks require different models — some need speed, others need reasoning quality, and cost optimization is important at scale. Relying on a single provider creates vendor risk and limits optimization opportunities.

## Decision

The platform supports multiple LLM providers: OpenAI, Anthropic, Google (Gemini), and Groq. A provider abstraction layer allows routing requests to different providers based on use case.

## Alternatives Considered

- **Single provider (OpenAI only)** — Vendor lock-in, no cost optimization, no redundancy
- **Two providers (OpenAI + one backup)** — Insufficient for optimizing cost/quality across different task types
- **Abstract behind a gateway (e.g. LiteLLM)** — Adds another dependency; custom abstraction in agent/model/ is simpler

## Consequences

- **Easier:** Flexibility to choose the best model per task; cost optimization; provider redundancy
- **Harder:** Must maintain provider abstraction layer; inconsistent behavior across providers must be handled
