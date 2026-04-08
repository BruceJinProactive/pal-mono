# Prompt Traceability for All Conversations

**Scope:** Prompt V2 text. All conversations (voice, chat, eval).
**Goal:** Know the exact prompt used for any conversation. Compare prompts between any two conversations.
**Depends on:** `build_with_fingerprint()`, `upsert_agent_config_snapshot()`, `agent_config_snapshots` table — all on main.

---

## Background

### What exists today (verified on main at 18c11938)

| Component | Status |
|-----------|--------|
| `build_with_fingerprint()` in `services/agent_service/_raw_config.py:105` | Built. Wraps `build()`, calls `compute_agent_fingerprint()` internally, returns `(AgentConfig, agent_fp, prompt_fp, config_dict)`. |
| `upsert_agent_config_snapshot()` in `services/eval_service/_snapshot.py` | Built. Fire-and-forget, owns its own session. |
| `AgentConfigSnapshot` table | Built. PK = `fingerprint` (agent fingerprint). Stores `system_prompt_hash`, `system_prompt_text`, `config_snapshot` JSONB. |
| `conversations.agent_fingerprint` + `conversations.prompt_fingerprint` | Columns exist. **Only populated for voice calls.** |
| Voice init fingerprinting (`_voice.py:340-377`) | Done. Constructs `RawConfig`, calls `build_with_fingerprint()`, stamps conversation, upserts snapshot. |
| Chat endpoint fingerprinting (`/v1/chat/`) | **Not implemented.** |
| Eval runner fingerprinting | **Not implemented.** Uses HTTPDriver which calls `/v1/chat/`. |
| History/diff APIs | **Do not exist.** |

### The key insight

There are three conversation entry points. Only one has fingerprinting:

| Entry point | Fingerprinting? | Why |
|-------------|----------------|-----|
| Voice init (`_voice.py`) | Yes | Constructs `RawConfig`, calls `build_with_fingerprint()` directly |
| Chat (`/v1/chat/`) | **No** | Calls `construct_agent_config()` which calls `raw_config.build()` — not `build_with_fingerprint()` |
| Eval (HTTPDriver) | **No** | Calls `/v1/chat/` — inherits chat's lack of fingerprinting |

**Fix chat, and eval gets fingerprinting for free.** HTTPDriver just sends HTTP requests to `/v1/chat/`. If `/v1/chat/` fingerprints every conversation, eval runs using HTTPDriver are automatically covered.

### Design: background task, zero changes to existing functions

`construct_agent_config()` and `construct_agent_spec()` remain untouched. Instead, fingerprinting runs as a **fire-and-forget background task** after the chat response flow, following the same pattern voice init uses for `upsert_agent_config_snapshot()`.

```
/v1/chat/ request
  → get_chat_response_async()
    → construct_agent_spec() or construct_agent_config()   ← UNCHANGED
    → ... generate response ...
    → fire background: _fingerprint_conversation(agent_id, project_id, ...)
        → owns its own AsyncSessionLocal
        → loads agent, project (re-reads from DB)
        → RawConfig(...).build_with_fingerprint(session)
        → stamps conversation.agent_fingerprint + prompt_fingerprint
        → upsert_agent_config_snapshot(...)
```

**Tradeoff:** Re-loads agent/project from DB in the background task (already cached at DB level). Acceptable because:
- Runs in background — zero latency impact on chat response
- Only runs on first message per conversation (`not conversation.agent_fingerprint` guard)
- No changes to `construct_agent_config()`, `construct_agent_spec()`, or any existing function

### Storage and query pattern

- **Per conversation:** `conversations.agent_fingerprint` (64-char hash, already exists as column)
- **Per unique config:** `agent_config_snapshots` row with `system_prompt_text` (full prompt) + `config_snapshot` (JSONB)
- **Query:** `conversation.agent_fingerprint` → `agent_config_snapshots.fingerprint` (PK lookup) → `system_prompt_text`
- **Diff:** load `agent_fingerprint` from two conversations → look up both snapshots → compare `system_prompt_text` via `difflib.unified_diff`

---

## What this plan adds

1. **Background fingerprinting task** — `_fingerprint_conversation()` in message_service, fired after chat response
2. **Store fingerprints on conversation + upsert snapshot** — inside the background task
3. **History API** — `GET /v1/eval/history/{project_id}?limit=N` returns last N conversations with prompt text
4. **Diff API** — `GET /v1/eval/conversations/{id}/prompt-diff?compare_to={id}` returns unified text diff

---

## Data Flow

### During a chat conversation (or eval run via HTTPDriver)

```
POST /v1/chat/ { message }
  → get_chat_response_async()
    → construct_agent_spec() / construct_agent_config()    ← UNCHANGED
    → generate chat response                               ← UNCHANGED
    → fire background: _fingerprint_conversation(agent_id, project_id, user_id, conversation_id, channel)
        → AsyncSessionLocal()                              # owns its own session
        → check conversation.agent_fingerprint             # skip if already stamped
        → load agent, project from DB
        → RawConfig(...).build_with_fingerprint(session)
          → build()                                        # builds AgentConfig
          → prompt_factory_v2.build()                      # canonical prompts for hashing
          → compute_agent_fingerprint()                    # SHA-256 (internal)
          → returns (config, agent_fp, prompt_fp, config_dict)
        → conversation.agent_fingerprint = agent_fp
        → conversation.prompt_fingerprint = prompt_fp
        → commit
        → upsert_agent_config_snapshot(agent_fp, prompt_text, config_dict)
```

### Fetching a diff

```
GET /v1/eval/conversations/{id_a}/prompt-diff?compare_to={id_b}
  → load conversation_a.agent_fingerprint, conversation_b.agent_fingerprint
  → if same → { prompt_changed: false }
  → look up agent_config_snapshots for each → get system_prompt_text
  → difflib.unified_diff(text_a, text_b)
  → return { prompt_changed: true, diff: "..." }
```

---

## Implementation Steps

### Step 1: Add `_fingerprint_conversation()` background task

**File:** `services/message_service/_implementation.py`

Add a self-contained async function that owns its own session. Follows the same pattern as `upsert_agent_config_snapshot()` in `services/eval_service/_snapshot.py`.

```python
_background_tasks: set[asyncio.Task[None]] = set()  # Module-level, prevents GC


async def _fingerprint_conversation(
    agent_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    channel: Channel,
) -> None:
    """Compute and store agent fingerprints for a conversation.

    Fire-and-forget background task. Owns its own session.
    Skips if conversation already has a fingerprint.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Check if already fingerprinted
            conversation_repo = db.ConversationRepositoryAsync(session)
            conversation = await conversation_repo.get_conversation_by_id(conversation_id)
            if conversation.agent_fingerprint:
                return  # already stamped

            # Load agent and project
            agent_repo = db.AgentRepositoryAsync(session)
            db_agent = await agent_repo.get_agent(agent_id=agent_id)
            if not db_agent or not db_agent.account:
                return

            project_repo = db.ProjectRepositoryAsync(session)
            db_project = await project_repo.get_project(project_id)
            if not db_project:
                return

            # Build RawConfig and compute fingerprints
            raw_config = _raw_config.RawConfig(
                agent=db_agent,
                project=db_project,
                account=db_agent.account,
                user_id=user_id,
                conversation_id=conversation_id,
                channel=channel,
            )
            config, agent_fp, prompt_fp, config_dict = (
                await raw_config.build_with_fingerprint(session)
            )

            # Stamp conversation
            conversation.agent_fingerprint = agent_fp
            conversation.prompt_fingerprint = prompt_fp
            await session.commit()

            # Upsert snapshot (fire-and-forget, owns its own session)
            prompt_text = (config.persona.description if config else "") or ""
            await upsert_agent_config_snapshot(
                fingerprint=agent_fp,
                agent_id=agent_id,
                project_id=project_id,
                config_dict=config_dict,
                prompt_hash=prompt_fp,
                prompt_text=prompt_text,
            )
    except Exception:
        logger.exception("Failed to fingerprint conversation %s", conversation_id)
```

Then in `get_chat_response_async()`, after both flows (pal-agents and legacy), fire the task:

```python
# After Step 2 (both flows), before Step 3:
fp_task = asyncio.create_task(
    _fingerprint_conversation(
        agent_id=agent_id,
        project_id=project_id,
        user_id=user.id,
        conversation_id=request_message.conversation_id,
        channel=message.channel,
    )
)
_background_tasks.add(fp_task)
fp_task.add_done_callback(_background_tasks.discard)
```

**Key decisions:**

- `conversation.agent_fingerprint` guard inside the task: skips if already stamped (idempotent).
- Owns its own `AsyncSessionLocal` — no interference with the chat response session.
- All exceptions swallowed — fingerprinting failure never breaks chat.
- `upsert_agent_config_snapshot()` is awaited inside the task (not a nested background task) since we're already in background.
- `prompt_text` comes from `config.persona.description` — the fully built prompt. Same pattern as voice init (`_voice.py:375`).

**No changes to existing functions:** `construct_agent_config()`, `construct_agent_spec()`, `build_with_fingerprint()` all remain untouched.

---

### Step 2: Diff API — compare prompts between two conversations

**Files to create:**

#### `api/routes/eval/__init__.py`

```python
from fastapi import APIRouter

eval_router = APIRouter(prefix="/eval", tags=["eval"])

from api.routes.eval._implementation import *  # noqa: E402, F401, F403
```

#### `api/routes/eval/_implementation.py`

```python
@eval_router.get("/conversations/{conversation_id}/prompt-diff")
async def get_prompt_diff(
    conversation_id: uuid.UUID,
    compare_to: uuid.UUID,
    session: AsyncSession = Depends(db.get_db_async),
) -> dict:
    try:
        return await diff_prompt_between_conversations(conversation_id, compare_to, session)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
```

#### Service function in `services/eval_service/_prompt_traceability.py`

```python
import difflib

async def diff_prompt_between_conversations(
    conversation_id_a: uuid.UUID,
    conversation_id_b: uuid.UUID,
    session: AsyncSession,
) -> dict[str, Any]:
    """Produce a unified diff of prompt text between two conversations."""
    conversation_repo = db.ConversationRepositoryAsync(session)
    snapshot_repo = AgentConfigSnapshotRepositoryAsync(session)

    conv_a = await conversation_repo.get_conversation_by_id(conversation_id_a)
    conv_b = await conversation_repo.get_conversation_by_id(conversation_id_b)

    fp_a = conv_a.agent_fingerprint
    fp_b = conv_b.agent_fingerprint

    if fp_a == fp_b:
        return {
            "prompt_changed": False,
            "agent_fingerprint_a": fp_a,
            "agent_fingerprint_b": fp_b,
            "diff": None,
        }

    text_a = ""
    text_b = ""

    if fp_a:
        snap_a = await snapshot_repo.get_by_fingerprint(fp_a)
        if snap_a:
            text_a = snap_a.system_prompt_text

    if fp_b:
        snap_b = await snapshot_repo.get_by_fingerprint(fp_b)
        if snap_b:
            text_b = snap_b.system_prompt_text

    diff_lines = difflib.unified_diff(
        text_a.splitlines(keepends=True),
        text_b.splitlines(keepends=True),
        fromfile=f"conversation-{conversation_id_a}",
        tofile=f"conversation-{conversation_id_b}",
    )

    return {
        "prompt_changed": True,
        "agent_fingerprint_a": fp_a,
        "agent_fingerprint_b": fp_b,
        "diff": "".join(diff_lines),
    }
```

Note: `get_conversation_by_id()` raises `ValueError` if not found — the route handler should catch this and return 404.

---

### Step 3: History API — last N conversations with prompt text

#### API route in `api/routes/eval/_implementation.py`

```python
@eval_router.get("/history/{project_id}")
async def get_eval_history(
    project_id: uuid.UUID,
    limit: int = 10,
    session: AsyncSession = Depends(db.get_db_async),
) -> dict:
    return await get_conversation_history_with_prompts(project_id, limit, session)
```

#### Service function in `services/eval_service/_prompt_traceability.py`

```python
async def get_conversation_history_with_prompts(
    project_id: uuid.UUID,
    limit: int,
    session: AsyncSession,
) -> dict[str, Any]:
    """Fetch last N conversations for a project with prompt text and change detection."""
    conversation_repo = db.ConversationRepositoryAsync(session)
    snapshot_repo = AgentConfigSnapshotRepositoryAsync(session)

    # Get recent conversations for this project
    conversations = await conversation_repo.get_by_project(
        project_id, limit=limit
    )

    # Batch-load snapshots for distinct fingerprints
    fingerprints = {c.agent_fingerprint for c in conversations if c.agent_fingerprint}
    snapshots: dict[str, AgentConfigSnapshot] = {}
    for fp in fingerprints:
        snap = await snapshot_repo.get_by_fingerprint(fp)
        if snap:
            snapshots[fp] = snap

    # Build response with prompt_changed flags (oldest first for comparison)
    results: list[dict[str, Any]] = []
    prev_prompt_hash: str | None = None

    for conv in reversed(conversations):
        snap = snapshots.get(conv.agent_fingerprint) if conv.agent_fingerprint else None
        current_prompt_hash = snap.system_prompt_hash if snap else None

        prompt_changed = (
            prev_prompt_hash is not None
            and current_prompt_hash is not None
            and current_prompt_hash != prev_prompt_hash
        )

        results.append({
            "conversation_id": str(conv.id),
            "agent_fingerprint": conv.agent_fingerprint,
            "prompt_fingerprint": snap.system_prompt_hash if snap else None,
            "prompt_text": snap.system_prompt_text if snap else None,
            "prompt_changed": prompt_changed,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
        })

        if current_prompt_hash:
            prev_prompt_hash = current_prompt_hash

    results.reverse()  # newest first
    return {"project_id": str(project_id), "conversations": results}
```

Note: `conversation_repo.get_by_project()` needs to be added to `ConversationRepositoryAsync`. It queries conversations by `project_id` ordered by `created_at desc` with a limit. The `prompt_changed` flag compares `system_prompt_hash` (prompt-only hash) rather than `agent_fingerprint` (full config hash), so model/tool changes don't trigger false "prompt changed" flags.

---

### Step 4: Tests

#### `tests/services/message_service/test_fingerprint_conversation.py`

| Test | What it verifies |
|------|-----------------|
| `test_fingerprints_conversation_on_first_message` | `conversation.agent_fingerprint` + `prompt_fingerprint` populated |
| `test_skips_already_fingerprinted` | Already-stamped conversation not re-computed |
| `test_upserts_snapshot` | `upsert_agent_config_snapshot` called with correct args |
| `test_swallows_exceptions` | Errors don't propagate |

#### `tests/api/routes/eval/test_prompt_diff.py`

| Test | What it verifies |
|------|-----------------|
| `test_diff_returns_unified_diff` | Two conversations with different prompts produce valid diff |
| `test_diff_no_change` | Same fingerprint → `prompt_changed: false` |
| `test_diff_conversation_not_found` | Returns 404 |
| `test_diff_missing_snapshot` | Graceful handling |

#### `tests/api/routes/eval/test_history.py`

| Test | What it verifies |
|------|-----------------|
| `test_history_returns_prompt_text` | Prompt text included from snapshot |
| `test_history_flags_prompt_changed` | Detects prompt changes between conversations |
| `test_history_handles_null_fingerprint` | Legacy conversations handled gracefully |
| `test_history_respects_limit` | Limit parameter works |

---

## API Reference

### `GET /v1/eval/conversations/{conversation_id}/prompt-diff?compare_to={conversation_id}`

Compare the prompt text between any two conversations.

**Response (changed):**
```json
{
  "prompt_changed": true,
  "agent_fingerprint_a": "abc123...",
  "agent_fingerprint_b": "def456...",
  "diff": "--- conversation-aaa\n+++ conversation-bbb\n@@ -42,3 +42,3 @@\n-Always confirm the order.\n+Suggest a drink pairing first."
}
```

**Response (unchanged):**
```json
{
  "prompt_changed": false,
  "agent_fingerprint_a": "abc123...",
  "agent_fingerprint_b": "abc123...",
  "diff": null
}
```

### `GET /v1/eval/history/{project_id}?limit=N`

Last N conversations for a project with prompt text and change detection.

**Response:**
```json
{
  "project_id": "abc-123",
  "conversations": [
    {
      "conversation_id": "conv-3",
      "agent_fingerprint": "def456...",
      "prompt_fingerprint": "aaa111...",
      "prompt_text": "You are Bella from Bella Italia...",
      "prompt_changed": true,
      "created_at": "2026-04-08T14:30:00Z"
    },
    {
      "conversation_id": "conv-2",
      "agent_fingerprint": "abc123...",
      "prompt_fingerprint": "bbb222...",
      "prompt_text": "You are Bella from Bella Italia...",
      "prompt_changed": false,
      "created_at": "2026-04-07T10:00:00Z"
    }
  ]
}
```

---

## Affected Files

### New files

| File | Purpose |
|------|---------|
| `api/routes/eval/__init__.py` | Eval router |
| `api/routes/eval/_implementation.py` | Diff + history route handlers |
| `services/eval_service/_prompt_traceability.py` | Diff + history service functions |
| `tests/services/message_service/test_fingerprint_conversation.py` | Background task tests |
| `tests/api/routes/eval/test_prompt_diff.py` | Diff API tests |
| `tests/api/routes/eval/test_history.py` | History API tests |

### Modified files

| File | Change |
|------|--------|
| `services/message_service/_implementation.py` | Add `_fingerprint_conversation()`, fire it in `get_chat_response_async()` |
| `db/repositories/conversation_repository.py` | Add `get_by_project()` to `ConversationRepositoryAsync` |
| `api/routes/v1_router.py` | Include eval_router |
| `api/routes/endpoints.py` | Add `EVAL` constant |

### No changes needed

| File | Why |
|------|-----|
| `services/agent_service/_implementation.py` | `construct_agent_config()` and `construct_agent_spec()` untouched |
| `services/agent_service/__init__.py` | No new exports |
| `api/routes/internal/_voice.py` | Already has fingerprinting |
| `db/tables/conversations.py` | `agent_fingerprint` + `prompt_fingerprint` columns already exist |
| `db/tables/agent_config_snapshots.py` | Table already exists |
| `services/eval_service/_snapshot.py` | `upsert_agent_config_snapshot()` already exists |
| `services/eval_service/_runner.py` | Eval uses HTTPDriver → `/v1/chat/` → gets fingerprinting for free |
| `db/tables/eval_runs.py` | No new columns needed |

---

## Task Ordering

```
Step 1: _fingerprint_conversation() background task + wire into get_chat_response_async()
  |
  +---> Step 2: Diff API      (depends on Step 1)
  |
  +---> Step 3: History API    (depends on Step 1, needs get_by_project() repo method)
  |
  v
Step 4: Tests  (depends on Steps 2 + 3)
```

---

## Risks and Open Questions

### Extra DB reads in background task

`_fingerprint_conversation()` re-loads agent and project from DB (already loaded during `construct_agent_config()`). This is acceptable because:
- Runs in background — zero latency impact on chat response
- Only runs on first message per conversation
- Agent/project rows are likely still in PostgreSQL's shared_buffers cache

### Performance of `build_with_fingerprint()`

`build_with_fingerprint()` calls `build()` (builds full AgentConfig) then calls `prompt_factory_v2.build()` for canonical hashing. The config build is the main cost. Since the background task runs after the chat response is already generated, this has zero impact on response latency.

### `ConversationRepositoryAsync.get_conversation_by_id()` raises ValueError

Unlike most repo methods that return `None`, this one raises `ValueError` if not found. The background task wraps everything in try/except so this is safe. The diff API route handler should catch `ValueError` and return 404.

### `conversation_repo.get_by_project()`

Does not exist yet. Needs to be added to `ConversationRepositoryAsync`: query conversations by `project_id` ordered by `created_at desc` with a limit.

### Streaming responses

Background task fires after `get_chat_response_async()` returns, regardless of streaming. Since it owns its own session, no session lifecycle concerns with ADR-019.

### Legacy conversations

All existing conversations without fingerprints return `prompt_text: null, prompt_changed: false`. No backfill. Going forward only.

### `agent_fingerprint` vs `prompt_fingerprint` for change detection

The diff API compares full `agent_fingerprint`. The history API compares `system_prompt_hash` (prompt only) for the `prompt_changed` flag. Model/tool changes won't trigger false "prompt changed" flags.

---

## Acceptance Criteria

- [ ] Chat conversations have `agent_fingerprint` + `prompt_fingerprint` populated after first message
- [ ] Full prompt text stored in `agent_config_snapshots` per unique fingerprint
- [ ] Eval runs via HTTPDriver get fingerprints for free (no eval-specific code needed)
- [ ] Voice conversations continue to work (no regression)
- [ ] `construct_agent_config()` and `construct_agent_spec()` unchanged
- [ ] `GET /v1/eval/conversations/{id}/prompt-diff?compare_to={id}` returns unified diff
- [ ] `GET /v1/eval/history/{project_id}?limit=N` returns conversations with prompt text and `prompt_changed`
- [ ] Chat response latency not affected (fingerprinting runs in background)
- [ ] Fingerprinting failure does not break chat responses
- [ ] Legacy conversations without fingerprints handled gracefully
- [ ] `./scripts/validate.sh` passes
- [ ] All new tests pass
