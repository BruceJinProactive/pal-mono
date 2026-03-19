# ADR-018: Migrate from VAPI to LiveKit

> **Status:** Accepted
> **Date:** 2026-02-18
> **Decision makers:** Jacob Wang

## Context

The platform started with VAPI as the initial managed voice solution. As voice became more central to the product, the team needed a voice runtime with stronger control over transport, agent execution, observability, and failure handling.

This choice is architectural, not just vendor preference. The voice runtime shapes latency, debuggability, deployment options, and how deeply the platform can customize turn-taking and provider routing behavior.

## Decision

The platform standardizes on LiveKit as the long-term voice runtime. New platform voice work should target LiveKit, and VAPI should be treated as a legacy path to remove once migration is complete.

This decision is driven by product and platform fit:
- LiveKit gives the team direct control over the real-time media and agent stack
- LiveKit aligns with the platform's custom agent runtime and observability needs
- LiveKit keeps self-hosted and managed deployment options open

This ADR does not freeze vendor pricing or feature-comparison details as the basis of the decision. Those details may change over time and belong in implementation plans, records, or migration notes.

## Alternatives Considered

- **Stay on VAPI** — Faster to operate in the short term, but less aligned with the level of control and integration the platform wants for voice
- **Adopt another managed voice platform** — Similar tradeoff profile around platform control and vendor dependency
- **Build custom voice infrastructure from scratch** — More control, but too much engineering cost compared with building on LiveKit's primitives

## Consequences

- **Easier:** Voice behavior, observability, and deployment become more controllable by the platform team; new voice work converges on one runtime
- **Harder:** The team owns more voice-platform engineering and migration complexity than with a turnkey managed product

## Evidence

- LiveKit is the target runtime referenced by [ADR-007](007-agno-to-pal-agents-migration.md)
- [ADR-019](019-streaming-session-ownership.md) documents an operational issue encountered on the LiveKit-backed streaming path
- Vendor-specific benchmarks, pricing, and migration details should live in `docs/records/` or implementation plans, where they can be updated without changing the architectural rule
