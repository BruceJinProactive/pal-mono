---
name: docs-reviewer
description: |
  Audit the docs/ knowledge management system for health, staleness, and compliance.
  Use when:
  - Reviewing a PR (check if code changes should have updated docs)
  - Periodic docs audit ("audit docs", "check docs health")
  - Checking for stale documentation or broken links
  - Validating docs conventions before merging
  Trigger phrases: "audit docs", "review docs", "check docs", "docs stale",
  "docs health", "verify docs", "docs compliance", "check documentation"
---

# docs-reviewer

Audit the `docs/` knowledge system for compliance and freshness.

## Quick Start

Run the audit script for automated checks:

```bash
python3 .claude/skills/docs-reviewer/docs-reviewer/scripts/audit_docs.py
```

Then manually review the items the script cannot catch (semantic staleness, missing docs for changed systems).

## Automated Checks (via script)

The `scripts/audit_docs.py` script verifies:

1. **state/ metadata**: Every file has `> **Last updated:** YYYY-MM-DD` on line 3
2. **records/ naming**: Files follow `YYYY-MM-DD-description.md` pattern
3. **records/ metadata**: Every file has `> **Date:** YYYY-MM-DD` on line 3
4. **short-term dates**: Active work entries have `(started` date markers
5. **Internal links**: All `docs/` cross-references point to files that exist

## Manual Review Checklist

The script catches structural issues. These require human judgment:

### PR Review

When reviewing a PR, check:

- [ ] Did the PR change system architecture? → Is `state/` updated?
- [ ] Did the PR complete planned work? → Is there a `records/` entry?
- [ ] Did the PR start new work? → Is `memory/short-term.md` updated?
- [ ] Did the PR discover gotchas? → Is `memory/long-term.md` updated?
- [ ] Is there a `log.md` entry for this change?

### Periodic Audit (monthly)

- [ ] `memory/short-term.md` — Any "Active Work" entries with no git activity in 4+ weeks?
- [ ] `memory/long-term.md` — Any entries no longer accurate? Any missing entries?
- [ ] `state/` — Any files with `Last updated` older than 3 months? Verify still accurate.
- [ ] `plans/` — Any completed plans that should graduate to `state/` + `records/`?
- [ ] `plans/` — Any abandoned plans that should be archived to `records/`?
