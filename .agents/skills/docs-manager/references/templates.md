# Templates

Copy-paste templates for each docs/ category.

## state/ Template

```markdown
# [System Name]

> **Last updated:** YYYY-MM-DD

## Overview

Brief description of this system and its purpose.

## Architecture

How the system works, key components, data flow.

## Key Files

| File | Purpose |
|------|---------|
| `path/to/file.py` | Description |
```

## plans/ Template

```markdown
# [Feature/Change Name] — Design

## Overview

What this plan proposes and why.

## Goals

- Goal 1
- Goal 2

## Scope

**In scope:**
- Item 1

**Out of scope:**
- Item 1

## Architecture / Design

How this will work. Diagrams, data flow, key decisions.

## Implementation Plan

1. Step 1
2. Step 2

## Open Questions

- Question 1
```

## records/ Template

File naming: `YYYY-MM-DD-description.md`

```markdown
# [What Was Done]

> **Date:** YYYY-MM-DD

## Summary

1-3 sentence overview of the completed work.

## What Changed

- Change 1
- Change 2

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Chose X over Y | Because... |

## Lessons Learned

- Lesson 1 (consider adding to memory/long-term.md)
```

## log.md Entry

```markdown
### YYYY-MM-DD
- Brief description of change → `docs/path/to/relevant-doc.md`
```

## memory/short-term.md Entry

Active work:
```markdown
- **Feature name** (started YYYY-MM) — Brief description. → `docs/plans/path.md`
```

Recently landed:
```markdown
- YYYY-MM-DD: Brief description → `docs/state/path.md`
```

## memory/long-term.md Entry

```markdown
- **Topic** (YYYY-MM-DD): What was learned — because [rationale]. See `docs/path.md`.
```
