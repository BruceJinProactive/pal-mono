# Plan: Migrate Tool Result Cache to DB

**Objective:** Replace the in-memory tool result cache in pal-agents with DB-backed persistence in pal-mono, solving the multi-pod consistency problem.

**Status:** Planning
**Created:** 2026-05-19

---

## Current State


| Component         | Location                                                                               | Description                                                                               |
| ----------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| In-memory cache   | `pal-agents/src/pal_agents/engine/_tool_result_cache.py`                               | Process-local dict, keyed by session_id, max 10 results, 30min TTL                        |
| Cache read        | `pal-agents/src/pal_agents/engine/__init__.py` → `build_input_content()`               | Injects cached results as `<previous_tool_results>` block into prompt                     |
| Cache write       | `pal-agents/src/pal_agents/executor/openai/__init__.py` → `_maybe_cache_tool_result()` | Allowlisted tools only (Adora/Toast order, delivery, lookup)                              |
| DB table          | `pal-mono/db/tables/tool_call_records.py`                                              | Already exists with conversation_id, tool_name, is_error, error_type, duration_ms, result |
| DB repository     | `pal-mono/db/pal_repository/tool_call_record.py`                                       | Async repo with add + get_by_conversation                                                 |
| Event emission    | `pal-agents` executor                                                                  | Already emits `Output(content="", events=[...])` chunks with tool_call payloads           |
| Event consumption | `pal-mono/services/message_service/_implementation.py`                                 | Already collects events from empty-content chunks and stores in message body              |


**Problem:** 4 AWS pods each have independent caches. If a user's next turn hits a different pod, prior tool results are lost.

---

## Architecture Decision

We will NOT create a new table. The existing `tool_call_records` table already has the right schema. We will:

1. Expand what gets stored (currently `result=None` for PII safety; we'll store sanitized results for allowlisted tools)
2. Query tool_call_records on agent creation to hydrate context
3. Eventually remove the in-memory cache from pal-agents

---

## Step-by-Step Plan

### Phase 1: Store Tool Results in DB (pal-mono)

#### Step 1.1: Update tool_call_records schema (if needed)

The current `result` column is VARCHAR(1000). Tool results (especially order/lookup) can be larger. Evaluate whether we need:

- **DECIDED:** Migrate `result` column from VARCHAR(1000) to TEXT (store full results)
- Add `session_id` column (currently only `conversation_id` exists — these map 1:1 for voice calls but verify)

**Files to modify:**

- `db/tables/tool_call_records.py` — schema change if needed
- `db/migrations/versions/` — new Alembic migration

#### Step 1.2: Ensure pal-agents emits tool results on empty-content chunks

The existing event emission already includes tool results in the payload:

```python
{"type": "tool_call", "payload": {"tool_name": "...", "result": "...", "status": "success"}}
```

**DECIDED:** Include ALL tool calls from this point on (not just allowlisted). Verify that all tools emit their results in events. If not, ensure `_create_tool_handler` includes full result in event payload.

**Files to check/modify:**

- `pal-agents/src/pal_agents/executor/openai/__init__.py` — verify event payload includes result

#### Step 1.3: Persist tool results from pal-agents outputs in pal-mono

When pal-mono receives pal-agents `tool_call` events, persist each event to the `tool_call_records` table.

**Current flow:**

1. Events are collected during pal-agents response handling
2. Attached to message body as `response_message_body["tool_calls"]`

**New flow (additive):**

1. Events are collected during pal-agents response handling (unchanged)
2. Attached to message body (unchanged)
3. **NEW:** For each tool_call event, fire-and-forget insert into `tool_call_records` with the full result

Apply the same persistence treatment to both pal-agents execution paths:

- Non-streaming: `_dispatch_agent_async(...)` collects `pal_output.events` after `pal_agent.run(pal_input)`
- Streaming: `get_chat_response_stream(...)` collects `chunk.events` from empty-content chunks during `pal_agent.run(pal_input, stream=True)`

Both non-streaming and streaming pal-agents paths live in `services/message_service/_implementation.py`, so update both paths in the same PR.

**Files to modify:**

- `pal-mono/services/message_service/_implementation.py` — add DB persistence calls for both non-streaming and streaming pal-agents event handlers
- `pal-mono/db/pal_repository/tool_call_record.py` — ensure the create/persist path stores the full result field

**Key decisions:**

- **DECIDED:** Store ALL tool calls (successes + errors), no allowlist filter on write
- **DECIDED:** The old allowlist source-of-truth question is obsolete for DB persistence; pal-mono should persist all pal-agents `tool_call` events from this point forward
- **DECIDED:** No truncation/sanitization needed now — rely on TTL-based data retention (2 days or 1 week) to avoid permanent PII storage
- Fire-and-forget pattern (don't block streaming on DB write)

**Failure handling for fire-and-forget writes:**

- On DB write failure: log structured error (conversation_id, tool_name, error) — do NOT retry or block streaming
- Emit a failure metric (e.g., `tool_call_record.write_failure`) for alerting
- Acceptable trade-off: occasional missed records are tolerable since the in-memory cache remains active during Phase 1–2 (dual-write period)
- No dead-letter queue needed — this is supplementary persistence, not critical path

---

### Phase 2: Query DB on Agent Creation (pal-mono)

#### Step 2.1: Add tool results to RuntimeContext or Spec

When building the pal-agents spec/input for a new turn, query `tool_call_records` for the current conversation and pass previous results to pal-agents.

**Option A — Pass via Input extension:**
Add a `previous_tool_results` field to the Input model that pal-agents already accepts or extend it.

**Option B — Pass via Spec/RuntimeContext:**
Add a field to RuntimeContext that carries DB-retrieved tool results.

**DECIDED:** Option B — RuntimeContext, as it is variable by conversation.

**Files to modify:**

- `pal-agents/src/pal_agents/input.py` — add `previous_tool_results` field
- `pal-agents/src/pal_agents/engine/__init__.py` — in `build_input_content()`, prefer Input-provided results over cache
- `pal-mono/services/agent_service/_implementation.py` — in `construct_agent_spec()` or the calling code, query DB and populate Input

#### Step 2.2: Query tool_call_records in pal-mono before agent run

Before calling `pal_agent.run(...)`, query recent tool call records for the conversation:

```python
tool_results = await tool_call_record_repo.get_tool_calls_by_conversation(conversation_id)
```

**DECIDED:** No filter — return all tool call results for the conversation. No allowlist, no max limit.

**Files to modify:**

- `pal-mono/services/message_service/_implementation.py` — query before `pal_agent.run()`
- `pal-mono/db/pal_repository/tool_call_record.py` — ensure the conversation query returns all records without allowlist or max-count filtering

#### Step 2.3: Render DB results in pal-agents engine

In `build_input_content()`, if `input.previous_tool_results` is provided, use those instead of (or merged with) the in-memory cache. The rendered format must match:

```xml
<previous_tool_results>
{"tool_name":"...","tool_result":...}
</previous_tool_results>
```

**Files to modify:**

- `pal-agents/src/pal_agents/engine/__init__.py` — update `build_input_content()` to use Input-provided results

---

### Phase 3: Validate and Cut Over

#### Step 3.1: Dual-write validation

Run both paths simultaneously:

- In-memory cache continues to work as before
- DB results are also queried and logged (but not yet used for prompt)

Compare outputs to ensure DB results match cache results for the same sessions.

#### Step 3.2: Switch to DB-only

Once validated:

1. Toggle pal-agents to prefer DB-provided results over cache
2. If `input.previous_tool_results` is non-empty, skip cache lookup entirely

#### Step 3.3: Remove in-memory cache

**Files to delete/modify in pal-agents:**

- `src/pal_agents/engine/_tool_result_cache.py` — DELETE
- `src/pal_agents/engine/__init__.py` — remove cache imports and fallback logic
- `src/pal_agents/executor/openai/__init__.py` — remove `_maybe_cache_tool_result()` and `_maybe_cache_tool_error()` calls
- `tests/` — remove cache-related tests

---

## Data Flow (Final State)

```text
Turn N:
  User speaks → pal-mono saves message → gets conversation_id
  pal-mono builds Input (no previous_tool_results on turn 1)
  pal-agents runs → tool executes → emits Output(content="", events=[tool_call_event])
  pal-mono receives chunk → persists to tool_call_records table (fire-and-forget)

Turn N+1 (possibly different pod):
  User speaks → pal-mono saves message
  pal-mono queries tool_call_records for conversation_id
  pal-mono builds Input with previous_tool_results populated
  pal-agents runs → engine renders <previous_tool_results> from Input
  Model has full context of prior tool calls
```

---

## Filtering Strategy

**Phase 1 (Store everything):** Persist all tool_call events (successes and errors). This gives us visibility.

**Phase 2+ (No filter on read):** Return ALL tool call results for the conversation. No allowlist filter, no max limit — return everything.

---

## Migration Considerations

- **No downtime required** — additive changes only until Phase 3
- **Backward compatible** — pal-agents cache continues working during transition
- **Pod-safe** — any pod can write/read from shared DB
- **Result size** — DECIDED: migrate VARCHAR(1000) → TEXT (pending Shuo's approval on DB edit)
- **Data retention** — implement TTL-based cleanup (2 days or 1 week) to avoid permanent PII storage; no filtering on read

---

## Testing Strategy

1. **Unit tests:** Repository methods (add + query with filters)
2. **Integration tests:** Streaming handler persists tool_call events to DB
3. **E2E comparison:** Log both cache-based and DB-based results, compare for parity
4. **Multi-pod simulation:** Verify results are available across different service instances

---

## Files Summary

### pal-mono (changes)


| File                                          | Change                                                             |
| --------------------------------------------- | ------------------------------------------------------------------ |
| `db/tables/tool_call_records.py`              | Possibly expand `result` column                                    |
| `db/pal_repository/tool_call_record.py`       | Ensure full result is stored; query all records by conversation    |
| `services/message_service/_implementation.py` | Persist tool events to DB during non-streaming + streaming pal-agents paths; query before agent run |
| `services/agent_service/_implementation.py`   | Pass previous_tool_results when building Input                     |
| `db/migrations/versions/`                     | New migration if schema changes                                    |


### pal-agents (changes)


| File                                          | Change                                      |
| --------------------------------------------- | ------------------------------------------- |
| `src/pal_agents/runtime_context.py` (or equivalent) | Add `previous_tool_results` field to RuntimeContext |
| `src/pal_agents/engine/__init__.py`           | Use Input-provided results; deprecate cache |
| `src/pal_agents/executor/openai/__init__.py`  | Verify event payloads include results       |
| `src/pal_agents/engine/_tool_result_cache.py` | Eventually DELETE                           |


---

## Decisions (from 2026-05-20 discussion)

| Question | Decision |
|----------|----------|
| Result size limit: VARCHAR(1000) sufficient? | **No.** Tool call responses are not small. Must store full result. Migrate `result` column to TEXT. Consult Shuo on DB edit. |
| PII in results / sanitization needed? | **No immediate risk.** Don't need sanitization now. Instead, apply a TTL on stored data (2 days or 1 week) so user-sensitive data is not stored permanently. |
| TTL on read (filter by time like 30 min cache)? | **No.** Do not filter by time on read. Return all results for the conversation. |
| Max 10 most recent results per conversation? | **No.** Return **all** results for the conversation. |
| Filter to only allowlisted tools on store? | **No filter for now.** Store all tool calls from this point on. |
| Add tool results to RuntimeContext or Spec? | **RuntimeContext** — it is variable by conversation. |
| Which tools to include? | **All tool calls** from this point on (no allowlist filtering on write). |
| DB read latency vs in-memory cache? | Open — needs benchmarking. DB read is slower than cache; monitor impact on response latency. |

## Remaining Open Questions

1. **DB migration approval:** Shuo to confirm the VARCHAR(1000) → TEXT migration on `result` column.
2. **TTL cleanup mechanism:** How to implement the data retention policy (2 days or 1 week)? Cron job, pg_cron, or application-level cleanup?
