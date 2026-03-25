# ADR-007: Agno to Pal-Agents Migration

> **Status:** Accepted
> **Date:** 2026-02-01
> **Decision makers:** Kelvin, Jeff C

## Context

Agno was the platform's initial agent runtime, but the platform outgrew that default as agent complexity increased. The team needed a runtime that made agent behavior easier to reason about and gave the platform tighter control over context, execution, and integration boundaries as prompts, tools, memory, and knowledge became more intertwined.

This was architectural, not just framework preference. The intended runtime shape was spec-driven and stateless: agents should be defined by structured configuration, each run should be atomic with explicit input and output, and stateful concerns such as memory and knowledge should be accessed through clear provider boundaries rather than hidden runtime state. The platform also wanted that runtime isolated from monolith coupling, so shared agent-runtime behavior could evolve in its own package without turning `pal-mono` into the framework implementation surface.

`pal-agents` is the in-house runtime built for that role. It exposes the agent surfaces the platform wants to standardize on and gives the team more control than continuing to build new work directly on Agno.

## Decision

The platform's default agent runtime direction is `pal-agents`, maintained as a dedicated shared package rather than as new framework logic embedded directly in `pal-mono`.

This decision applies to agent-runtime work in `pal-mono`:
- New agent-runtime work should target `pal-agents`.
- Shared runtime behavior and interfaces should be added to `pal-agents` rather than introducing another in-monolith agent framework path.
- Existing Agno paths may remain only where current integrations still depend on them during the migration period.
- Teams should not add new Agno-first agent surfaces unless that work is required to support an existing Agno-dependent integration.

This ADR sets the runtime default and ownership boundary. It does not define the full prompt, tool, or evaluation design of the agent stack.

## Alternatives Considered

- **Keep Agno as the default runtime** — Rejected because it preserves the old default and keeps new platform work tied to a framework that is no longer the strategic fit.
- **Build the new runtime inside `pal-mono` as another internal framework path** — Rejected because the platform wanted the runtime to stay self-contained and easier to evolve independently from monolith-specific dependencies.
- **Remove Agno immediately** — Rejected because existing integrations still depend on Agno and the migration has to preserve compatibility while those paths are retired.
- **Adopt another general-purpose agent framework** — Rejected because the platform wanted tighter control over runtime behavior and interfaces than a heavier third-party framework would provide.

## Consequences

- **Easier:** New agent work converges on one runtime direction; the platform has more control over agent interfaces, context boundaries, and runtime behavior.
- **Harder:** The team must maintain two runtimes during the migration period and own the cost of evolving a dedicated runtime package.

## Evidence

- `services/agent_service/` builds `pal-agents` specs for the newer agent path.
- `services/message_service/` already carries both the `pal-agents` path and legacy compatibility handling.
- `agent/framework/agno.py` remains as the legacy Agno runtime surface.
- The original design direction for this migration included dedicated `pal-agents` and `pal-tools` packages to keep the runtime and tool library isolated from monolith coupling.
