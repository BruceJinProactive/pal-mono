# P1-B1d: Wire fingerprints into voice init + events

**Task:** PAL-9413
**Type:** CODE
**Est. Hours:** 3
**Blocked by:** B1a (compute_agent_fingerprint), B1b (build_with_fingerprint), B1c (DB columns + migration) — all DONE

---

## Background

B1a–B1c established the fingerprinting primitives and DB schema. This task wires them into the live voice call flow:

1. During `init_voice_call`, compute fingerprints by calling `RawConfig.build_with_fingerprint()` and persist them on the newly created `Conversation` row.
2. Add `agent_fingerprint` and `prompt_fingerprint` fields to the `ConversationEvaluationRequested` event schema so the downstream evaluator receives them.
3. Pass the stored fingerprints through `_publish_livekit_evaluation_event` into the event payload.

### Key findings from codebase investigation

- **`RawConfig.build_with_fingerprint()`** already exists at `services/agent_service/_raw_config.py:103` and returns `(AgentConfig, agent_fingerprint, prompt_fingerprint, config_dict)`. It is safe to call with the same `session` used in the init handler.
- **`init_voice_call`** (`api/routes/internal/_voice.py`) does NOT currently construct a `RawConfig`. It calls `project_service.get_project_async()` (which loads `project.account`) and `user_service`, but does NOT load the agent. The agent must be fetched separately via `AgentRepositoryAsync`.
- After step 4 (`message_repo.create_voice_message()`), the conversation is committed to the DB. The conversation object is not returned — to get `conversation_id` we must either query by `call_id` or return it from the message. The cleanest approach is to call `conversation_repo.get_conversation_by_call_id(call_id)` immediately after step 4 to retrieve the row and store fingerprints directly on it.
- **`ConversationEvaluationRequested`** (`events/schema.py:230`) has no fingerprint fields today. Fields must be added as optional with `field(default=None)` so existing callers (e.g. any non-voice path) are unaffected.
- **`_publish_livekit_evaluation_event`** already creates its own `AsyncSessionLocal` session to load project/account. It should also load the conversation to retrieve the stored fingerprints and pass them into the event.

---

## Implementation Steps

### Step 1: Add fingerprint fields to `ConversationEvaluationRequested`

File: `events/schema.py`

Add two optional fields to the dataclass (after `audio_recording`):

```python
agent_fingerprint: str | None = None
prompt_fingerprint: str | None = None
```

The `BaseEvent.to_detail()` serializer already skips `None` values, so no other change is needed here.

### Step 2: Compute and persist fingerprints in `init_voice_call`

File: `api/routes/internal/_voice.py`

Add a new Step 9 after the existing Step 8 (speech rate mapping), before the `return` statement.

**What to import/add:**

```python
from db.repositories.agent_repository import AgentRepositoryAsync
from services.agent_service._raw_config import RawConfig
from db.tables.types import Channel
```

**Logic outline for Step 9:**

```python
# --- Step 9: Compute and persist agent fingerprints ---
try:
    # Load the agent (project.agent_id is available after Step 2 loaded project)
    agent_repo = AgentRepositoryAsync(session)
    db_agent = await agent_repo.get_agent(agent_id=project.agent_id)

    if db_agent and db_agent.account:
        raw_config = RawConfig(
            agent=db_agent,
            project=project,
            account=db_agent.account,
            user_id=user.id,
            conversation_id=uuid.uuid4(),  # placeholder — fingerprint is config-only, not session-specific
            channel=Channel.VOICE,
        )
        _, agent_fp, prompt_fp, _ = await raw_config.build_with_fingerprint(session)

        # Retrieve the just-created conversation and stamp it
        conversation_repo = db.ConversationRepositoryAsync(session)
        conversation = await conversation_repo.get_conversation_by_call_id(call_id)
        if conversation:
            conversation.agent_fingerprint = agent_fp
            conversation.prompt_fingerprint = prompt_fp
            await session.commit()
            logger.info(
                "[init_voice_call] Fingerprints stored",
                extra={**_log_extra, "agent_fingerprint": agent_fp[:8]},
            )
        else:
            logger.warning(
                "[init_voice_call] Conversation not found for fingerprinting",
                extra=_log_extra,
            )
    else:
        logger.warning(
            "[init_voice_call] Agent not found or missing account — skipping fingerprint",
            extra=_log_extra,
        )
except Exception:
    # Fingerprinting is non-critical — log and continue; call must not fail
    logger.exception(
        "[init_voice_call] Failed to compute/persist fingerprints",
        extra=_log_extra,
    )
```

Notes:
- The `conversation_id` passed to `RawConfig` here is a throwaway UUID because `build_with_fingerprint` only uses it to populate `AgentMetadata.session_id`, which is excluded from the stable config hash. The fingerprint itself depends only on agent/project/account/channel fields.
- Fingerprinting is wrapped in a broad `except` so any failure (e.g. agent not configured, DB timeout) does NOT break the voice init response. The LiveKit agent must still receive its config.
- `project` must be refreshed to include `agent_id` if it was expired. Check whether `project.agent_id` is accessible after the existing refreshes — if not, add `agent_id` to the `attribute_names` list in the `session.refresh()` call in step 4.

### Step 3: Pass fingerprints through `_publish_livekit_evaluation_event`

File: `api/routes/internal/_voice.py`

**In `end_voice_call`:** Before Step 5 (Stripe billing), capture fingerprints from the conversation:

```python
agent_fingerprint_for_event = conversation.agent_fingerprint
prompt_fingerprint_for_event = conversation.prompt_fingerprint
```

These must be captured before `session.commit()` in Step 3 (where the conversation is updated and committed) causes the object to detach. Add to the locals captured at lines 426–430.

**In the `asyncio.create_task(...)` call**, add the two new keyword arguments:

```python
task = asyncio.create_task(
    _publish_livekit_evaluation_event(
        ...
        agent_fingerprint=agent_fingerprint_for_event,
        prompt_fingerprint=prompt_fingerprint_for_event,
    )
)
```

**In `_publish_livekit_evaluation_event`:** Add the two parameters to the function signature:

```python
async def _publish_livekit_evaluation_event(
    ...
    agent_fingerprint: str | None,
    prompt_fingerprint: str | None,
) -> None:
```

Wire them into the event construction:

```python
event = ConversationEvaluationRequested(
    ...
    agent_fingerprint=agent_fingerprint,
    prompt_fingerprint=prompt_fingerprint,
)
```

### Step 4: Write tests

File: `tests/routes/internal/test_voice_fingerprint.py` (new file)

Test cases:

- **Fingerprint stored on conversation during init:** Mock `AgentRepositoryAsync.get_agent` and `RawConfig.build_with_fingerprint` to return known values. Mock `ConversationRepositoryAsync.get_conversation_by_call_id` to return a mock conversation. Assert `conversation.agent_fingerprint` and `conversation.prompt_fingerprint` are set.
- **Init succeeds even when fingerprint fails:** Mock `build_with_fingerprint` to raise an exception. Assert `init_voice_call` still returns a valid `VoiceInitResponse` (non-critical path).
- **Fingerprints present in published event:** Mock `end_voice_call` path — set `conversation.agent_fingerprint = "abc..."` and assert the `ConversationEvaluationRequested` event passed to `publish_event` has `agent_fingerprint="abc..."`.
- **Fingerprints absent (None) do not crash event publication:** Pass `agent_fingerprint=None` and verify event publishes without error (relies on `to_detail()` skipping None values).

Follow the `MagicMock` pinning rule from `CLAUDE.md`: explicitly set all `str | None` fields on mock request objects to avoid `TypeError` from `re.match()` / `.startswith()`.

---

## Affected Files

| File | Change |
|------|--------|
| `api/routes/internal/_voice.py` | Step 9 in `init_voice_call`; new params + wiring in `end_voice_call` and `_publish_livekit_evaluation_event` |
| `events/schema.py` | Add `agent_fingerprint: str | None` and `prompt_fingerprint: str | None` to `ConversationEvaluationRequested` |
| `tests/routes/internal/test_voice_fingerprint.py` | New test file |

No new DB migrations needed (columns exist from B1c).

---

## Validation

```bash
uv run pytest tests/routes/internal/test_voice_fingerprint.py -v
./scripts/validate.sh
```

---

## Risks & Open Questions

- **`project.agent_id` availability:** After `session.refresh(project, attribute_names=["id", "timezone"])` in Step 4, `agent_id` may be expired. Verify at implementation time — if expired, add `"agent_id"` to that refresh call.
- **`db_agent.account` loaded:** `AgentRepositoryAsync.get_agent` already does `selectinload(Agent.account)` (confirmed in `db/repositories/agent_repository.py:21`), so `db_agent.account` is safe to access without an extra refresh.
- **Double build cost:** `build_with_fingerprint` calls `build()` internally, which also calls `prompt_factory_v2.build()`. This adds latency to `init_voice_call`. Acceptable at init time (non-streaming), but worth measuring. If it proves too slow, fingerprinting can be moved to a background task similar to the eval event pattern.
- **`conversation_id` placeholder:** Passing `uuid.uuid4()` as the `conversation_id` to `RawConfig` is intentional — `compute_agent_fingerprint` does not include `session_id` in the hash. Verify this assumption holds by re-reading `_fingerprint.py` at implementation time.
