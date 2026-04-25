# ADR-013: Datadog for All Observability

> **Status:** Superseded by OTel + Langfuse (2026-04-24)
> **Date:** 2024-01-01
> **Decision makers:** Jun Lee

## Context

The platform needs unified observability including APM, LLM observability, and distributed tracing. The company already uses Datadog, so extending it to this project provides a single pane of glass for all monitoring.

## Decision

~~The platform uses Datadog for all observability: APM, LLM observability, and distributed tracing.~~

**Superseded:** As of 2026-04-24, the platform uses:
- **OpenTelemetry (OTel)** for general distributed tracing (exported to Grafana Tempo)
- **Langfuse SDK v4** for LLM observability (`@observe` decorators)
- `ddtrace` and `datadog` packages have been fully removed from the codebase.

## Alternatives Considered

- **Self-hosted (Grafana + Prometheus + Jaeger)** — Significant operational overhead to maintain observability stack
- **AWS CloudWatch + X-Ray** — Limited LLM observability; less powerful APM than Datadog
- **New Relic / Dynatrace** — Comparable but Datadog's LLM observability (LLMObs) is more mature for AI workloads

## Consequences

- **Easier:** Single platform for all observability; company-wide familiarity; integrated LLM observability
- **Harder:** Vendor lock-in; ongoing cost; dependent on Datadog service availability
