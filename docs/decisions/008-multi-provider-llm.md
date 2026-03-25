# ADR-008: Multi-Provider LLM Support

> **Status:** Accepted
> **Date:** 2025-07-01
> **Decision makers:** Kelvin, Jeff C

## Context

Different parts of the platform have different LLM needs. Chat, voice, monitoring, and multimodal workflows optimize for different tradeoffs across latency, reasoning quality, modality, structured output behavior, and cost. Provider choice is therefore part of how the platform optimizes capability and quality over time, not a one-time vendor selection.

This means one global provider abstraction is not the right default. In some places the platform benefits from a local provider-agnostic boundary so models can be switched or upgraded without changing every caller. In other places the feature itself is provider-specific, and forcing it through a repo-wide abstraction would either hide useful capabilities or create a lowest-common-denominator interface.

## Decision

The platform may use multiple LLM providers, but provider choice is owned at the subsystem boundary.

This decision applies to LLM integrations across the codebase:
- A subsystem may be single-provider, multi-provider, or provider-agnostic based on its own product and operational needs.
- Introduce a local abstraction only when that subsystem truly needs provider interchangeability or routing.
- When a subsystem exposes a provider-agnostic model boundary, callers in that subsystem should depend on that boundary rather than on provider SDK details.
- Direct provider-specific clients are acceptable when the capability is inherently provider-specific or when a broader abstraction would add complexity without real benefit.
- The codebase does not guarantee one uniform provider matrix or one mandatory global LLM abstraction across all subsystems.

## Alternatives Considered

- **Single provider everywhere** — Rejected because different subsystems have different latency, modality, cost, and capability needs.
- **One global provider abstraction for the whole repo** — Rejected because it over-constrains subsystems and pushes them toward the lowest common denominator.
- **Centralize all provider access behind a gateway such as LiteLLM** — Rejected because it adds another global dependency and still does not remove the need for subsystem-specific behavior.

## Consequences

- **Easier:** Each subsystem can choose the simplest boundary that fits its needs, while still hiding provider churn behind a local abstraction where that flexibility matters.
- **Harder:** The codebase will not have one uniform provider abstraction everywhere, so provider behavior and integration patterns may differ across subsystems.

## Evidence

- `agent/model/` represents one LLM integration boundary for the legacy agent runtime.
- `services/monitoring_service/_providers.py` uses its own local multi-provider abstraction for monitoring-specific needs.
- Other features in the repo call provider SDKs directly where the capability is intentionally provider-specific.
