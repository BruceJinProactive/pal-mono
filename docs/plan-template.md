# {{TASK_ID}}: {{TASK_TITLE}}

**Task:** {{NOTION_URL}}
**Est. Hours:** {{EST_HOURS}}
**Blocked by:**
{{ACTIVE_BLOCKERS: bullet list of active blockers with current status and what's needed to unblock. Use "- None" if unblocked.}}

**No longer blocking:**
{{RESOLVED_BLOCKERS: strikethrough list of resolved blockers. Omit section if none.}}

---

## Background

{{BACKGROUND: 2-3 paragraphs. What this task is, why it matters, how it fits into the project. Reference specific Notion docs, design decisions, and related PRs by name. Note which layer(s) of the stack are affected (api / agent / services / db / events / tools).}}

> **Dependency flow reminder:** API → Service → Database. No cross-layer imports outside this chain.
> Check `docs/memory/long-term.md` for established patterns before adding new abstractions.

---

## Implementation Steps

{{STEPS: checkbox steps grounded in the task. Each step covers one logical unit. Reference specific files, class names, and patterns found in the codebase. Add sub-bullets for non-obvious details.}}

- [ ] **Step 1: {{ACTION}}**

  {{DETAIL}}

- [ ] **Step 2: {{ACTION}}**

  {{DETAIL}}

> **If this task touches the database:**
> - [ ] Generate migration: `docker exec -it pal-mono-api alembic -c db/alembic.ini revision --autogenerate -m "description"`
> - [ ] Verify migration: `docker exec -it pal-mono-api alembic -c db/alembic.ini upgrade head`
> - [ ] Add a matching downgrade path in the migration file

> **If this task adds or modifies a Tool:**
> - Inherit from `Toolkit`, use `@tool` decorator (from `ddtrace`, not Agno)
> - Register in `tools/registry.py`
> - Docstrings max 1024 chars; include when-to-use / when-not-to-use
> - Never make LLM calls inside tool methods

> **If this task adds or modifies an EventBridge event:**
> - Define the event class in `events/`
> - Publish after DB writes are committed (fire-and-forget — log failures, don't raise)

---

## Validation

```bash
# 1. Full validation: format, lint, type check, import architecture
./scripts/validate.sh --check

# 2. Start containers if not running
docker-compose up -d --build

# 3. Run tests
docker exec -it pal-mono-api pytest

# 4. If DB schema changed — verify migration applies cleanly
docker exec -it pal-mono-api alembic -c db/alembic.ini upgrade head
docker exec -it pal-mono-api alembic -c db/alembic.ini downgrade -1
docker exec -it pal-mono-api alembic -c db/alembic.ini upgrade head
```

{{VALIDATION_NOTES: any task-specific checks beyond the above. Omit if nothing extra.}}

---

## Risks & Open Questions

{{RISKS: uncertainties, edge cases, decisions to make during implementation. Use "- None identified" if clean.}}

---

## Revision History

{{REVISION_HISTORY: populated only on updates. Format: "- **YYYY-MM-DD**: one-line summary". Omit section on initial creation.}}
