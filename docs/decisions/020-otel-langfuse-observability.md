# ADR-020: LGTM Stack for Operations, Langfuse for LLM Observability

> **Status:** Accepted
> **Date:** 2026-04-27
> **Decision makers:** Jun Lee

## Context

[ADR-013](013-datadog-observability.md) standardized on Datadog as the single pane of glass for APM, distributed tracing, and LLM observability. Two forces broke that model:

1. **LLM observability needs outgrew Datadog LLMObs.** Multi-agent, multi-provider workloads need per-tool spans, prompt/response capture, evaluator linkage, and cost attribution that LLMObs did not provide.
2. **Ops observability is consolidating on the Grafana LGTM stack** (Loki for logs, Grafana for dashboards, Tempo for traces, Mimir for metrics) across the platform team, independent of LLM tooling.

The migration off Datadog is partially complete:
- Traces moved to OTel → Tempo (PAL-10113, PR #4090). `ddtrace.llmobs` is removed from the codebase.
- Logs are wired through the OTel `LoggingHandler` in `utils/log.py` with `OTEL_LOGS_EXPORTER=otlp`, targeting Loki.
- LLM observability moved to Langfuse SDK v4 with `@observe` decorators in `agent/agent.py`, `agent/framework/agno.py`, and tool `_implementation.py` files.
- **Metrics have not migrated yet.** `utils/dd.py` still exports `statsd` (Datadog StatsD) to ~18 call sites.

This ADR records the target state for all observability pathways and the rule for new code during and after the Datadog phase-out.

## Decision

The platform uses the Grafana **LGTM stack** for operational observability and **Langfuse** for LLM observability. Datadog is being removed and must not be extended.

### Target pathways

| Concern | Backend | Instrumentation |
|---|---|---|
| LLM traces (agent turns, tool calls, prompts, responses) | **Langfuse** (SDK v4) | `@observe` decorators |
| General distributed traces (HTTP, DB, queues, EventBridge) | **Tempo** (Grafana) | OTel SDK via `utils/otel.py` (`@traced`) |
| Logs | **Loki** (Grafana) | Python `logging` → OTel `LoggingHandler` → OTLP (configured in `utils/log.py`) |
| Metrics (counters, histograms, gauges) | **Mimir** (Grafana) | OTel metrics SDK (`opentelemetry.metrics.get_meter`) |

### Rules

1. **New code must not add Datadog usage.** No new imports of `utils.dd.statsd`, no new `ddtrace` calls, no new `datadog.*` SDK usage.
2. **Existing `utils/dd.py` call sites are legacy.** They stay functional during the migration but must be migrated to OTel metrics when the module they live in is next touched. `utils/dd.py` itself is slated for deletion once callers reach zero.
3. **LLM instrumentation uses Langfuse, not OTel tracing or metrics.** Agent entry points, streaming generators, framework adapters, and tool `_implementation.py` functions use `@observe` (or equivalent Langfuse span APIs). Do not re-instrument LLM code paths with `@traced` — it duplicates and confuses traces.
4. **Trace structure around `agent/agent.py` is load-bearing.** The top-level `@observe` plus the inner streaming-generator `@observe` wrapper must be preserved; collapsing or reordering them breaks trace isolation.
5. **General tracing uses `utils/otel.py` (`@traced`), not raw `opentelemetry.trace` calls in application code.** Raw OTel is fine inside `utils/otel.py` itself or other infrastructure wrappers.
6. **Logs do not require explicit instrumentation.** Standard `logging` calls already flow through the OTel handler configured in `utils/log.py`. Do not add side-channel log shippers.

Scope: application-level instrumentation in `pal-mono`. Infrastructure-level monitoring (AWS CloudWatch alarms, container health, load-balancer metrics) is out of scope.

Exceptions: none. New needs that don't fit (e.g., a business-metric pipeline, synthetic monitoring) require a new ADR rather than reintroducing Datadog or adding a fourth backend.

## Alternatives Considered

- **Stay on Datadog across the board** — Rejected. LLMObs did not keep up with eval platform needs, and the platform team has standardized on LGTM for Ops outside this repo; maintaining a Datadog island creates dashboard and on-call fragmentation.
- **Langfuse for LLM + Datadog retained for Ops** — Rejected. Partially consistent with the current (transitional) state, but leaves long-term vendor lock-in and duplicate cost, and diverges from platform-wide Ops direction.
- **Single-vendor replacement (New Relic, Honeycomb, Dynatrace)** — Rejected. No single vendor matches Langfuse's depth on LLM traces *and* LGTM's fit with the platform team's self-hosted Grafana posture.
- **OTel-only (including LLM)** — Rejected for LLM. OTel GenAI semantic conventions are maturing but still lack the prompt/response fidelity, evaluator linkage, and UI purpose-built for LLM debugging that Langfuse provides today.

## Consequences

- **Easier:** One Ops stack (LGTM) aligned with the rest of the platform team; LLM traces gain per-tool spans, prompt/response capture, and direct linkage to eval runs; no Datadog bill long term.
- **Harder:** Observability is split between two backends (LGTM + Langfuse); engineers must know which pathway applies. Correlating an LLM trace with an HTTP trace requires joining Langfuse and Tempo by trace/span IDs rather than a single UI. The metrics migration (OTel metrics → Mimir) is still in front of us; ~18 `utils/dd.py` call sites need to be rewritten, and dashboards/alerts rebuilt on Mimir before `utils/dd.py` can be deleted.

## Evidence

- Tracing: `utils/otel.py` (`@traced` decorator over `opentelemetry.trace`).
- Logs: `utils/log.py` (`LoggingHandler` + `OTEL_LOGS_EXPORTER=otlp`).
- LLM: `agent/agent.py`, `agent/framework/agno.py`, tool `_implementation.py` files using `langfuse.observe`.
- Datadog legacy (to be migrated): `utils/dd.py` (`datadog.DogStatsd`), ~18 call sites across the codebase.
- Migration records: PAL-10112 (Langfuse dependency, PR #4089) and PAL-10113 (LLMObs removal, PR #4090).
- Superseded: [ADR-013](013-datadog-observability.md).
