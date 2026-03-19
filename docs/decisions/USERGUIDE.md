# ADR User Guide

This guide defines how ADRs work in this repository.

## Purpose

An ADR records a significant architectural decision so future changes have a clear rule to follow.

ADRs are prescriptive:
- They say what we intend to do or keep doing.
- They define constraints and defaults for future work.
- They can be used to reject code changes that violate the decision.

ADRs are not descriptive:
- They are not codebase inventory.
- They are not postmortems.
- They are not implementation notes or migration logs.
- They should not be accepted if the team does not want future work to follow them.

If you only want to explain how the system currently works, use `docs/state/`.
If you want to explain what happened during an incident, migration, or fix, use `docs/records/`.

## When To Write An ADR

Create an ADR when a change introduces or changes a significant default, boundary, or tradeoff, for example:
- Architectural boundaries between layers or modules
- Data ownership and persistence rules
- API or streaming patterns that future features must follow
- Security or compliance controls
- Major infrastructure or vendor choices
- Rules that intentionally constrain implementation options

Do not create an ADR for:
- Routine refactors
- Small library swaps with no architectural impact
- Temporary experiments
- Facts that are true today but are not intended to guide future work

## Required Qualities

Every ADR should be:
- Prescriptive: it states a rule, default, or policy
- Durable: it should remain useful after the current PR is merged
- Scoped: it is clear where the decision applies
- Testable: reviewers can tell whether a change follows it
- Honest about tradeoffs: it lists what gets easier and harder

## ADR Structure

Use this shape:

```md
# ADR-{NNN}: Short Decision Title

> **Status:** Accepted | Superseded | Deprecated
> **Date:** YYYY-MM-DD
> **Decision makers:** Names

## Context

What problem forces a decision now? Keep this tight.

## Decision

State the rule clearly. Use direct language such as:
- "The platform uses ..."
- "Services must ..."
- "Streaming endpoints must not ..."
- "Tables may ..."

Include scope and exceptions explicitly.

## Alternatives Considered

- Option A — why it was rejected
- Option B — why it was rejected

## Consequences

- Easier: ...
- Harder: ...

## Evidence

Optional. Link supporting docs, incidents, benchmarks, vendor docs, or code paths.
```

## Writing Rules

- Write the `Decision` section as policy, not observation.
- Do not justify an accepted ADR by saying "the code already does this." That is evidence, not rationale.
- Prefer narrow ADRs over broad slogans. "No ORM relationships anywhere" is brittle. "Repositories must avoid lazy-loading in request paths" is enforceable and scoped.
- If a decision is conditional, write the condition. Example: "For long-lived streaming responses, the generator must own its DB session."
- If there are exceptions, name them.
- Use concrete nouns from this codebase. Avoid generic architecture language when a repo-specific rule is clearer.

## How To Change A Decision

Do not rewrite an old accepted ADR so it means something new.

When direction changes:
1. Create a new ADR with the next number.
2. Mark the old ADR as `Superseded by ADR-{NNN}`.
3. Explain why the previous rule no longer fits.
4. Update affected docs in `docs/state/`, `docs/README.md`, and any team guides if needed.

If the old ADR was simply wrong or too absolute, preserve it and supersede it with a narrower replacement.

## Relationship To Other Docs

- `docs/decisions/`: policy and architectural direction
- `docs/state/`: how the system currently works
- `docs/records/`: what changed, why it happened, and lessons learned
- `docs/plans/`: proposed designs before implementation

## Review Checklist

Before merging an ADR, verify:
- The decision is intended to constrain future code
- The title states the decision, not the problem
- The `Decision` section is explicit and scoped
- The alternatives are real options that were considered
- The consequences include at least one downside
- The ADR belongs in `decisions/` instead of `state/` or `records/`

## Template

```md
# ADR-{NNN}: {Decision Title}

> **Status:** Accepted
> **Date:** YYYY-MM-DD
> **Decision makers:** {Names}

## Context

{Why a decision is needed now}

## Decision

{The rule or default this repository will follow}

## Alternatives Considered

- **{Option 1}** — {Why rejected}
- **{Option 2}** — {Why rejected}

## Consequences

- **Easier:** {Benefits}
- **Harder:** {Costs / constraints}

## Evidence

- {Optional supporting references}
```
