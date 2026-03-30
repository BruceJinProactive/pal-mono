# P1-C1d: Implement AgentConfigSnapshotRepository

**Task:** https://www.notion.so/3318c0822e4981e083face88b362e428
**Type:** CODE
**Est. Hours:** 2
**Blocked by:** P1-C1a (AgentConfigSnapshot table migration), P1-B1a (compute_agent_fingerprint, which produces the fingerprint PK used here)

---

## Background

`AgentConfigSnapshot` is a write-once, content-addressed store: the primary key is the `fingerprint` (SHA-256 hex string produced by `compute_agent_fingerprint()`). If the same agent config is seen twice it must not insert a duplicate row — it should return the existing snapshot and update `last_seen_at`.

This "get or create" / upsert semantic is the defining feature of this repository. All other reads are secondary lookup helpers.

---

## Implementation Steps

- [ ] **Step 1: Create `db/repositories/agent_config_snapshot_repository.py`**

  ```python
  from __future__ import annotations

  import uuid
  from datetime import datetime, timezone

  from sqlalchemy import select
  from sqlalchemy.dialects.postgresql import insert as pg_insert
  from sqlalchemy.exc import SQLAlchemyError
  from sqlalchemy.ext.asyncio import AsyncSession

  from db.tables import AgentConfigSnapshot
  from utils.log import logger


  class AgentConfigSnapshotRepositoryAsync:
      """Async repository for agent config snapshot operations."""

      def __init__(self, session: AsyncSession) -> None:
          self.session = session
  ```

  Implement these methods:

  - `get_or_create(snapshot: AgentConfigSnapshot) -> tuple[AgentConfigSnapshot, bool]`
    - Use a PostgreSQL `INSERT … ON CONFLICT (fingerprint) DO UPDATE SET last_seen_at = now()` via `sqlalchemy.dialects.postgresql.insert`
    - Return `(snapshot, created)` where `created` is `True` on insert, `False` on conflict
    - Detecting `created`: after `execute()`, check `result.rowcount` or compare `first_seen_at == last_seen_at` on the refreshed row — choose whichever is cleaner at implementation time
    - `flush()` → `refresh()` on the returned object before returning
    - Raise `SQLAlchemyError` on failure

  - `get_by_fingerprint(fingerprint: str) -> AgentConfigSnapshot | None`
    - `select(AgentConfigSnapshot).filter(AgentConfigSnapshot.fingerprint == fingerprint)`
    - Return `None` on `SQLAlchemyError`

  - `get_by_agent_id(agent_id: uuid.UUID) -> list[AgentConfigSnapshot]`
    - `select(AgentConfigSnapshot).filter(AgentConfigSnapshot.agent_id == agent_id)`
    - Order by `first_seen_at DESC` (most-recent config first)
    - Return `[]` on `SQLAlchemyError`

- [ ] **Step 2: Export from `db/repositories/__init__.py`**

  Add `AgentConfigSnapshotRepositoryAsync` to the module's public exports.

- [ ] **Step 3: Write tests in `tests/db/repositories/test_agent_config_snapshot_repository.py`**

  Use `AsyncMock` / `MagicMock` for the session; pin all optional `MagicMock` fields explicitly.

  Test cases:
  - `get_or_create` — new fingerprint: inserts and returns `(snapshot, True)`; existing fingerprint: returns existing row with `created=False` and `last_seen_at` updated; `SQLAlchemyError` propagates and calls `rollback()`
  - `get_by_fingerprint` — found returns the snapshot; not-found returns `None`; `SQLAlchemyError` returns `None`
  - `get_by_agent_id` — returns all snapshots for agent ordered by `first_seen_at DESC`; empty list when none found; `[]` on `SQLAlchemyError`

---

## Validation

```bash
uv run pytest tests/db/repositories/test_agent_config_snapshot_repository.py -v
./scripts/validate.sh
```

---

## Risks & Open Questions

- The `INSERT … ON CONFLICT DO UPDATE` approach requires that `fingerprint` is declared as a unique constraint (or primary key) at the DB level — confirm the migration created this correctly before implementing.
- SQLAlchemy's async `session.execute(pg_insert(...))` returns a `CursorResult`, not an ORM object; a follow-up `get_by_fingerprint` call (or `session.get`) will be needed to get a fully-mapped `AgentConfigSnapshot` after the upsert. Plan for two round-trips inside `get_or_create`.
- `get_by_agent_id` could return a large list if an agent has many distinct configs over time. Pagination can be added later; omit it from the initial implementation.
