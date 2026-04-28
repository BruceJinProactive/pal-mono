# ADR-013: Datadog for All Observability

> **Status:** Superseded by [ADR-020](020-otel-langfuse-observability.md)
> **Date:** 2024-01-01
> **Decision makers:** Jun Lee

## Context

The platform needs unified observability including APM, LLM observability, and distributed tracing. The company already uses Datadog, so extending it to this project provides a single pane of glass for all monitoring.

## Decision

~~The platform uses Datadog for all observability: APM, LLM observability, and distributed tracing.~~

**Superseded:** As of 2026-04-25 (PAL-10113, PR #4090), observability is governed by [ADR-020](020-otel-langfuse-observability.md), which standardizes on the Grafana LGTM stack for Ops (Loki/Tempo/Mimir) and Langfuse for LLM traces. Datadog is being removed from the platform: `ddtrace.llmobs` has already been deleted, and `utils/dd.py` (Datadog StatsD) is legacy and being migrated to OTel metrics → Mimir.

## Alternatives Considered

- **Self-hosted (Grafana + Prometheus + Jaeger)** — Significant operational overhead to maintain observability stack
- **AWS CloudWatch + X-Ray** — Limited LLM observability; less powerful APM than Datadog
- **New Relic / Dynatrace** — Comparable but Datadog's LLM observability (LLMObs) is more mature for AI workloads

## Consequences

- **Easier:** Single platform for all observability; company-wide familiarity; integrated LLM observability
- **Harder:** Vendor lock-in; ongoing cost; dependent on Datadog service availability
