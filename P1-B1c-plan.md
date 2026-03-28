# P1-B1c: Add fingerprint columns to Conversation + migration

**Task:** https://www.notion.so/3318c0822e4981acabd5d7330e7509af
**Type:** CODE
**Est. Hours:** 2
**Blocked by:** None

---

## Background

The Conversation table needs two new nullable indexed columns to store agent and prompt fingerprints. These are 64-char hex SHA-256 hashes stored on every voice call for traceability.

Current Conversation model is in `db/tables/conversations.py` and uses `Mapped[]` typed columns with `mapped_column()`.

---

## Implementation Steps

- [ ] **Step 1: Add columns to Conversation model**

  File: `db/tables/conversations.py`

  Add after existing columns (e.g., after `language` or at end of column definitions):
  ```python
  agent_fingerprint: Mapped[str | None] = mapped_column(
      String(64), nullable=True, index=True
  )
  prompt_fingerprint: Mapped[str | None] = mapped_column(
      String(64), nullable=True, index=True
  )
  ```

  Import `String` from `sqlalchemy` if not already imported.

- [ ] **Step 2: Verify Conversation is exported in `db/tables/__init__.py`**

  It should already be exported. Confirm before generating migration.

- [ ] **Step 3: Generate Alembic migration**

  ```bash
  docker exec -it pal-mono-api alembic -c db/alembic.ini revision --autogenerate -m "add-agent-fingerprint-to-conversations"
  ```

- [ ] **Step 4: Verify migration**

  ```bash
  docker exec -it pal-mono-api alembic -c db/alembic.ini upgrade head
  docker exec -it pal-mono-api alembic -c db/alembic.ini downgrade -1
  docker exec -it pal-mono-api alembic -c db/alembic.ini upgrade head
  ```

---

## Validation

```bash
./scripts/validate.sh
# Verify columns in psql:
docker exec -it pal-mono-db psql -U postgres -d palona -c "\d conversations" | grep fingerprint
```

Expected: Two VARCHAR(64) nullable columns with indexes.

---

## Risks & Open Questions

- Migration must be additive only (nullable columns) — no risk to existing data
- If Docker isn't running, migration generation will need to wait
