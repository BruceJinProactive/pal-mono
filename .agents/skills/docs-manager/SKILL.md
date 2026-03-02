---
name: docs-manager
description: |
  Manage the docs/ knowledge management system lifecycle during development.
  Use when:
  - Completing a PR or significant work (create records/, graduate plans/, update state/)
  - Starting new work (create plans/ doc, update memory/short-term.md)
  - Making code changes that affect architecture or system behavior (update state/)
  - Discovering conventions, gotchas, or lessons learned (update memory/)
  - Creating new feature designs or proposals (create plans/ doc)
  - Graduating a completed plan to state/ and records/
  Trigger phrases: "update docs", "create plan", "add record", "graduate plan",
  "update state", "update memory", "docs lifecycle", "create design doc"
---

# docs-manager

Manage the `docs/` knowledge system. Read `docs/README.md` for full lifecycle rules.

## Decision Tree

On every significant code change, run through this:

```
What happened?
├── System architecture/behavior changed?
│   → Update relevant docs/state/ file
│   → Update "Last updated: YYYY-MM-DD" in that file
│   → Add log.md entry
│
├── Starting new work?
│   → Create docs/plans/ doc (use template below)
│   → Add to docs/memory/short-term.md "Active Work" with (started YYYY-MM)
│   → Add log.md entry
│
├── Completed significant work?
│   → Create docs/records/YYYY-MM-DD-description.md (use template below)
│   → Graduate plans/ doc: update state/ if system changed
│   → Remove from short-term.md "Active Work"
│   → Add to short-term.md "Recently Landed" with date
│   → Add log.md entry
│   → If lesson learned → add to memory/long-term.md
│
├── Discovered a gotcha or pattern?
│   → Add to memory/short-term.md immediately
│   → If confirmed/lasting → promote to memory/long-term.md with rationale
│
└── None of the above?
    → No docs update needed
```

## Enforcement Checklist

Before completing any PR, verify:

- [ ] `state/` files have `> **Last updated:** YYYY-MM-DD` after title — date reflects this PR
- [ ] `records/` files named `YYYY-MM-DD-description.md` with `> **Date:** YYYY-MM-DD` after title
- [ ] `memory/short-term.md` entries have dates — `(started YYYY-MM)` for active, `YYYY-MM-DD:` for landed
- [ ] `log.md` has a new entry linking to relevant docs
- [ ] No broken internal links between docs

## Templates

See [references/templates.md](references/templates.md) for copy-paste templates for each doc type.

## Graduation Flow

When a plan is completed:

1. **Update state/**: If the system changed, update or create the relevant `state/` doc. Add `> **Last updated:** YYYY-MM-DD`.
2. **Create record**: `docs/records/YYYY-MM-DD-description.md` with what was done, why, key decisions.
3. **Clear short-term**: Remove from "Active Work", add to "Recently Landed".
4. **Extract lessons**: If gotchas discovered, add to `memory/long-term.md` with rationale.
5. **Log it**: Add entry to `log.md` linking to new state/ and records/ docs.
6. **Keep or archive plan**: Leave in plans/ for reference, or delete if fully captured in state/ + records/.
