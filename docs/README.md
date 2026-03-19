# docs/ — Codebase Knowledge Management

Tool-agnostic documentation system for humans and AI agents working on pal-mono.

## Reading Order

| Default Read Order | Path | What | When to read |
|----------|------|------|--------------|
| P0 | `CLAUDE.md` (root) | Operating rules, commands | Auto-loaded by Claude/OpenCode |
| P1 | `docs/memory/short-term.md` | Active work, don't-touch zones | Before starting ANY task |
| P1 | `docs/memory/long-term.md` | Conventions, gotchas, patterns | Before writing code |
| P2 | `docs/log.md` | Recent changes (last ~10 entries) | To understand recent context |
| P3 | `docs/state/` | Current system architecture | When working on a specific system |
| P3 | `docs/plans/` | Active designs and proposals | When implementing planned work |
| P3 | `docs/records/` | Completed work and decisions | When understanding past decisions |
| P3 | `docs/decisions/` | Architecture decision records (authoritative policy) | When changing architecture, boundaries, or defaults; code and docs changes must obey accepted ADRs |

## Structure

```
docs/
├── README.md              ← You are here
├── log.md                 ← Chronological changelog (append-only)
│
├── memory/                ← Agent context layer
│   ├── long-term.md       ← Conventions, patterns, gotchas (curated, stable)
│   └── short-term.md      ← Active work, current sprint (ephemeral)
│
├── state/                 ← Current system (living reference)
│   ├── architecture.md    ← System-wide architecture overview
│   ├── auth.md            ← Current auth system + endpoint permissions
│   ├── billing.md         ← Billing + Stripe integration
│   ├── notifications.md   ← Stripe webhook setup
│   └── business-updater/  ← Event-driven business data updater system
│
├── decisions/             ← Architecture Decision Records (ADRs)
│   ├── README.md          ← Index of all decisions
│   └── {NNN}-{title}.md   ← Individual decisions with context + rationale
│
├── plans/                 ← Future work (active designs)
│   ├── livekit-migration/ ← Vapi → LiveKit voice migration
│   ├── billing/           ← Billing architecture design
│   ├── prompt-v2/         ← Capability-based prompt system
│   ├── auth/              ← Checkpoint permission migration
│   ├── notifications/     ← Billing notifications V1/V2
│   ├── operations/        ← Routines, monitoring, inputs, notifications
│   └── business-updater/  ← Planned but not implemented features
│
└── records/               ← Past work (detailed, date-prefixed)
    └── 2025-02-14-monitoring-trace-fix.md

## Lifecycle Rules

### state/ — Living Reference
- **Updated when**: The system changes (same PR as the code change)
- **Never**: Stale — if the code changed, the doc must too
- **Required**: Each file must contain `> **Last updated:** YYYY-MM-DD` after the title — update this date on every change
- **Template**: Describes the system as it exists TODAY

### decisions/ — Architecture Decision Records
- **Created when**: A significant architectural choice is made (technology, pattern, tradeoff)
- **Naming**: `{NNN}-{kebab-case-title}.md` (numbered for ordering)
- **Required**: Status, Date, Decision makers, Context, Decision, Consequences, Evidence
- **Never deleted**: When a decision changes, mark old ADR `Superseded by ADR-{NNN}` and create a new one
- **Prescriptive**: ADRs define architecture policy and defaults for future work, not a description of the current codebase
- **Guide + template**: See `docs/decisions/USERGUIDE.md`

### plans/ — Active Designs
- **Created when**: Designing a new feature or significant change
- **Lives here while**: Work is active or not yet started
- **Graduates to**: `state/` (if system changed) + `records/` (detailed write-up) when completed
- **Template**: Design/proposal with goals, scope, architecture, and implementation plan

### records/ — Past Work
- **Created when**: Significant work is completed
- **Naming**: `YYYY-MM-DD-description.md` (date-prefixed for chronology)
- **Required**: Each file must contain `> **Date:** YYYY-MM-DD` after the title
- **Never modified**: Append-only — these are historical records
- **Template**: What was done, why, key decisions, lessons learned

### log.md — Changelog
- **Updated when**: Any significant change (same PR as the code)
- **Entry format**: `- Brief description → docs/path/to/relevant-doc.md`
- **Never pruned**: Chronological record of all changes

### memory/long-term.md — Institutional Knowledge
- **Updated when**: A new convention, gotcha, or lesson is discovered
- **Every entry must have a "because"**: No rules without rationale
- **Curated periodically**: Monthly review to prune stale entries, consolidate duplicates
- **Promotion flow**: Discovered during work → short-term → confirmed → long-term

### memory/short-term.md — Active Context
- **Updated when**: Starting/finishing significant work
- **Sections**: Active Work, Recently Landed, Known Issues or Recent Resolutions, Don't Touch, Upcoming
- **Required**: Every entry must include a date — `(started YYYY-MM)` for active work, `YYYY-MM-DD:` prefix for recently landed
- **Refreshed at**: Sprint/cycle boundaries — clear completed items, add new ones
- **Stale items**: >4 weeks with no activity → remove or promote to plan/record

## Update Rules

### The Golden Rule
**Docs update in the same PR as the code change.** Not after. Not "I'll do it later." Same PR.

### Who Updates What

| Action | Who | When |
|--------|-----|------|
| Add short-term entry | Developer starting work | Before first commit |
| Clear short-term entry | Developer finishing work | In the merge PR |
| Add long-term entry | Anyone discovering a gotcha | In the PR that discovered it |
| Curate long-term | Team / periodic review | Monthly or sprint boundary |
| Update state/ | Whoever changes the system | Same PR as code change |
| Create records/ entry | Whoever completes significant work | Post-merge |
| Add log.md entry | Whoever makes a significant change | Same PR as code change |

### PR Checklist
Add to your PR template:
```text
## Docs
- [ ] `state/` updated if architecture/system changed
- [ ] `records/` entry if significant work completed
- [ ] `memory/short-term.md` updated if active work changed
- [ ] `memory/long-term.md` updated if lesson learned / new convention
- [ ] `log.md` entry added
```

## Memory Promotion Flow

```text
Working on code → discover gotcha/pattern
    ↓
Add to memory/short-term.md (immediately)
    ↓
Work completes → lesson confirmed
    ├── Update state/ (if system changed)
    ├── Create records/ entry (if significant)
    ├── Remove from short-term.md "Active Work"
    ├── Add to short-term.md "Recently Landed"
    └── Promote to memory/long-term.md (if lasting lesson)
    ↓
Sprint boundary
    ├── Clear "Recently Landed" older than 4 weeks
    ├── Review "Active Work" — still active?
    └── Review long-term.md — still accurate?
```

## For AI Agents

This system is designed to work with ANY AI coding tool (Claude Code, OpenCode, Codex, Cursor, etc.).

Each tool's instruction file (CLAUDE.md, AGENTS.md, etc.) points here. The docs/ directory has no tool-specific conventions — it's plain markdown readable by anything.

**Agent workflow:**

1. Instruction file auto-loads → "I know the rules and where to look"
2. Task arrives → read `memory/short-term.md` → "I know what's active and fragile"
3. Read `memory/long-term.md` → "I know the conventions and gotchas"
4. Need specifics → follow pointers to `state/`, `plans/`, or `records/`
5. After completing work → **propose doc updates** (human approves in PR)
