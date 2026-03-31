# P1-E1: Agent config snapshot on call init

**Task:** https://www.notion.so/3318c0822e4981e8a284da53fad20885
**Type:** CODE
**Est. Hours:** 4
**Blocked by:** P1-B1 (done), P1-C1 (done)

---

## Background

P1-B1 added fingerprint computation to voice init (`_voice.py` Step 9). P1-C1 created the `AgentConfigSnapshot` table and its repository with `get_or_create` (upsert). This task connects them: after fingerprints are computed during `init_voice_call`, fire a background task that upserts an `AgentConfigSnapshot` row so we have a permanent record of every distinct agent configuration seen in production.

---

## Files to create

| File | Purpose |
|------|---------|
| `services/eval_service/_snapshot.py` | Service module wrapping the snapshot upsert |
| `tests/services/eval_service/test_snapshot.py` | Unit tests for `_snapshot.py` |
| `tests/api/routes/internal/test_voice_snapshot.py` | Integration tests for the wiring in `_voice.py` |

## Files to modify

| File | Change |
|------|--------|
| `api/routes/internal/_voice.py` | Fire background snapshot task after fingerprint computation in Step 9 |
| `services/eval_service/__init__.py` | Export `upsert_agent_config_snapshot` |

---

## Implementation Steps

### Step 1: Create `services/eval_service/_snapshot.py`

Thin service wrapping the repository upsert. Owns its own `AsyncSessionLocal` session for fire-and-forget use.

```python
async def upsert_agent_config_snapshot(
    fingerprint: str,
    agent_id: uuid.UUID,
    project_id: uuid.UUID,
    config_dict: dict[str, Any],
    prompt_hash: str,
    prompt_text: str,
) -> None:
```

- Creates `AsyncSessionLocal()` — never uses request-scoped session
- Constructs `AgentConfigSnapshot` ORM object
- Calls `AgentConfigSnapshotRepositoryAsync.get_or_create(snapshot)`
- Commits and logs "Created" or "Updated last_seen_at"
- Entire body wrapped in `except Exception` with logging (fire-and-forget safety)

### Step 2: Update `services/eval_service/__init__.py`

Export `upsert_agent_config_snapshot` in `__all__`.

### Step 3: Wire into `_voice.py` Step 9

After fingerprints are computed and stored on conversation:

1. Change destructuring from `_, agent_fp, prompt_fp, _` to `config, agent_fp, prompt_fp, config_dict`
2. Extract `system_prompt_text = config.persona.description if config else ""`
3. Fire background task:
   ```python
   snapshot_task = asyncio.create_task(
       upsert_agent_config_snapshot(
           fingerprint=agent_fp,
           agent_id=db_agent.id,
           project_id=project_id,
           config_dict=config_dict,
           prompt_hash=prompt_fp,
           prompt_text=system_prompt_text,
       )
   )
   _background_tasks.add(snapshot_task)
   snapshot_task.add_done_callback(_background_tasks.discard)
   ```

### Step 4: Write tests

**`tests/services/eval_service/test_snapshot.py`** — Unit tests:
- `test_upsert_creates_snapshot_on_new_fingerprint` — assert commit + "Created" log
- `test_upsert_updates_last_seen_on_existing_fingerprint` — assert "Updated" log
- `test_upsert_swallows_db_errors` — no exception propagates
- `test_upsert_swallows_unexpected_errors` — no exception propagates

**`tests/api/routes/internal/test_voice_snapshot.py`** — Integration tests:
- `test_snapshot_task_fired_after_fingerprint_computed` — correct args
- `test_init_succeeds_when_snapshot_upsert_fails` — voice init not blocked
- `test_snapshot_not_fired_when_agent_not_found` — guard clause works

---

## Session Ownership

```
init_voice_call(request, session)        # request-scoped session
  +-- Step 9: build_with_fingerprint(session)  # reads via request session
  |     +-- conversation.agent_fingerprint = agent_fp
  |     +-- await session.commit()
  +-- asyncio.create_task(upsert_agent_config_snapshot(...))  # fire-and-forget
        +-- async with AsyncSessionLocal() as session:  # NEW owned session
              +-- repo.get_or_create(snapshot)
              +-- await session.commit()
```

---

## Acceptance Criteria

- After 10 calls with same config: exactly 1 snapshot row, `last_seen_at` updated
- After capability change: new row with new fingerprint
- Background task does not block voice init response (< 1ms added)
- If snapshot upsert fails, voice init still succeeds
- `_background_tasks` set holds snapshot task reference (GC prevention)

---

## Validation

```bash
uv run pytest tests/services/eval_service/test_snapshot.py -v
uv run pytest tests/api/routes/internal/test_voice_snapshot.py -v
uv run pytest tests/api/routes/internal/test_voice_fingerprint.py -v
./scripts/validate.sh
```
