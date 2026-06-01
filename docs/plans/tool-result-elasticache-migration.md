# Plan: Migrate Tool Result Cache to AWS ElastiCache

**Objective:** Replace the process-local `pal-agents` tool result cache with
shared AWS ElastiCache-backed storage so recent tool outputs survive pod changes.

**Status:** Planning
**Created:** 2026-05-19
**Last updated:** 2026-06-01

This plan supersedes the earlier DB-backed direction. Detailed
ElastiCache implementation notes live in
`docs/plans/tool-result-elasticache.md`.

---

## Current State

| Component | Location | Description |
| --------- | -------- | ----------- |
| In-memory cache | `pal-agents/src/pal_agents/engine/_tool_result_cache.py` | Process-local dict keyed by `session_id`, max 10 results, 30 minute TTL |
| Cache read | `pal-agents/src/pal_agents/engine/__init__.py` -> `build_input_content()` | Injects cached results as a `<previous_tool_results>` block |
| Cache write | `pal-agents/src/pal_agents/executor/openai/__init__.py` -> `_maybe_cache_tool_result()` | Writes allowlisted tool results to the process-local cache |
| Event emission | `pal-agents` executor | Emits `tool_call` events with tool name, status, arguments, and result data |
| Event consumption | `pal-mono/services/message_service/_implementation.py` | Collects `tool_call` events from empty-content chunks and stores them in message bodies |
| DB records | `pal-mono/db/tables/tool_call_records.py` | Existing persistent table for tool-call records; not the target cache backend for this plan |

**Problem:** Multiple AWS pods have independent process-local caches. If the
next user turn is routed to a different pod, the previous tool results are not
available for prompt hydration.

---

## Architecture Decision

Use AWS ElastiCache for recent tool-result context.

Key decisions:

- Keep one Redis/Valkey list per conversation:
  `tool-results:v1:{conversation_id}`.
- Write sanitized, prompt-useful tool results, not raw tool payloads.
- Include a short `result_summary`, allowlisted `cacheable_result`, and optional
  sanitized `input_summary`.
- Strip cached entries down to `tool_name` plus `tool_result` before prompt
  injection, matching the current compact cache rendering.
- Use `RPUSH` and `EXPIRE` on write.
- Do not `LTRIM` by count by default; long ordering conversations may need early
  tool results later in the same conversation.
- Control memory with TTL, per-item byte limits, payload allowlisting, and
  CloudWatch alarms.
- Treat ElastiCache writes and reads as best-effort. Fail open if cache is
  unavailable.
- Keep existing DB tool-call records as separate eval/debug/audit data if
  needed, but do not migrate the tool result cache to DB for this work.

Boto3 can manage ElastiCache resources, but runtime cache data access uses a
Redis/Valkey client such as `redis-py`.

---

## Data Model

Each cached item is compact JSON:

```json
{
  "tool_name": "toast_takeout_create_order_v1",
  "input_summary": "Create a takeout order for the selected cart",
  "result_summary": "Order was created and is pending payment.",
  "cacheable_result": {
    "status": "success",
    "order_state": "pending_payment"
  },
  "status": "success",
  "error_type": null,
  "captured_at": "2026-06-01T15:30:00Z"
}
```

The cache writer must explicitly allowlist fields. It must redact or drop
secrets, auth tokens, payment details, customer contact PII, addresses,
free-form notes, and integration payload fields that are not needed for the
next-turn prompt.

The full cache item should not be injected into context. Cache-only metadata can
support storage, debugging, and filtering, but the prompt renderer should emit
only the compact current-cache shape:

```json
{"tool_name":"toast_takeout_create_order_v1","tool_result":{"status":"success","order_state":"pending_payment"}}
```

If only an explanatory result is safe and useful, render:

```json
{"tool_name":"toast_takeout_create_order_v1","tool_result":"Order was created and is pending payment."}
```

---

## Step-by-Step Plan

### Phase 1: Provision And Configure ElastiCache

Provision ElastiCache for Valkey or Redis OSS in the same VPC/subnets as the API
pods.

Add app configuration:

```text
TOOL_RESULT_CACHE_ENABLED=true
TOOL_RESULT_CACHE_HOST=...
TOOL_RESULT_CACHE_PORT=6379
TOOL_RESULT_CACHE_USERNAME=...
TOOL_RESULT_CACHE_SECRET_KEY=...
TOOL_RESULT_CACHE_TTL_SECONDS=1800
TOOL_RESULT_CACHE_MAX_ITEM_BYTES=32768
```

Authentication options:

- Redis/Valkey username and password from AWS Secrets Manager.
- IAM auth for Valkey 7.2+ or Redis OSS 7+ with TLS enabled.

Files to modify:

- `pyproject.toml` - add `redis>=5,<7`
- `local.env.example` - document cache config
- deployment/config files - provide ElastiCache endpoint and secret keys

### Phase 2: Add A Cache Adapter In pal-mono

Add a small async adapter responsible for Redis client lifecycle and cache
operations.

Suggested file:

- `services/tool_result_cache.py`

Responsibilities:

- Build a singleton async Redis client or connection pool per process.
- Close the client on application shutdown.
- `append_tool_result(conversation_id, payload)`:
  - sanitize/allowlist payload via `build_cacheable_tool_result(...)`
  - reject entries over `TOOL_RESULT_CACHE_MAX_ITEM_BYTES`
  - `RPUSH` the compact JSON item
  - `EXPIRE` the key using `TOOL_RESULT_CACHE_TTL_SECONDS`
- `get_tool_results(conversation_id)`:
  - `LRANGE` the list
  - parse JSON
  - drop malformed entries
  - return oldest-to-newest results

### Phase 3: Write Tool Results From pal-mono

`pal-agents` already emits `tool_call` events. `pal-mono` should write those
events to ElastiCache after sanitization.

Apply this to both pal-agents paths:

- Non-streaming: `_dispatch_agent_async(...)` after `pal_agent.run(pal_input)`
  returns `pal_output.events`.
- Streaming: `get_chat_response_stream(...)` when empty-content chunks carry
  `chunk.events`.

Writes should be fire-and-forget or otherwise non-blocking. On failure, log a
structured warning/metric and continue the user response.

Files to modify:

- `services/message_service/_implementation.py`
- `tests/services/message_service/test_tool_call_events.py`

### Phase 4: Read Tool Results Before Agent Run

Before each `PalAgent.run(...)`, `pal-mono` should query ElastiCache for the
current `conversation_id`.

Pass the parsed results to `pal-agents` through one of:

- `PalInput.previous_tool_results`
- `RuntimeContext.previous_tool_results`

`RuntimeContext` is easiest to wire because it already carries per-conversation
request context and allows extra fields, but a first-class `PalInput` field may
be cleaner long term.

Files to modify:

- `services/message_service/_implementation.py`
- `pal-agents/src/pal_agents/input.py`
- `pal-agents/src/pal_agents/engine/__init__.py`

### Phase 5: Render External Results In pal-agents

Update `build_input_content()` so externally supplied previous tool results are
rendered into the existing prompt block after stripping cache-only fields:

```xml
<previous_tool_results>
{"tool_name":"...","tool_result":{...}}
</previous_tool_results>
```

Default injected fields:

- `tool_name`
- `tool_result`

Do not inject `captured_at`, `status`, `error_type`, or `input_summary` by
default. A sanitized `input_summary` can be included only for a tool-specific
case where it adds context that is not already in chat history.

During rollout, prefer externally supplied ElastiCache results and fall back to
the current in-memory cache when no external results are present.

### Phase 6: Validate And Cut Over

Run a dual-read period:

- Keep the current in-memory cache.
- Write ElastiCache entries.
- Read ElastiCache before agent runs.
- Log cache hit/miss and result counts.
- Compare behavior for same-pod and cross-pod turns.

Once cross-pod behavior is verified:

1. Prefer ElastiCache results in prompt hydration.
2. Remove the process-local tool result cache from `pal-agents`.
3. Keep cache operations best-effort so Redis issues do not break conversations.

---

## Final Data Flow

```text
Turn N:
  User speaks
  pal-mono saves message and gets conversation_id
  pal-mono reads previous results from ElastiCache
  pal-mono builds PalInput / RuntimeContext with previous_tool_results
  pal-agents runs and emits tool_call events
  pal-mono sanitizes events and writes cache entries to ElastiCache

Turn N+1, possibly on another pod:
  User speaks
  pal-mono reads tool-results:v1:{conversation_id}
  pal-agents receives previous_tool_results
  engine renders <previous_tool_results>
  model has prior tool context across pods
```

---

## Retention And Memory Strategy

- Use Redis key TTL for expiry.
- Do not count-trim the list by default.
- Enforce a per-item byte limit.
- Store only sanitized, prompt-useful fields.
- Monitor memory, evictions, list sizes, Redis errors, and cache hit/miss rate.
- If production data shows runaway lists inside the TTL window, add a
  conversation-level byte cap or tool-specific compression/summarization before
  reintroducing count-based trimming.

---

## Testing Strategy

1. Unit tests for `build_cacheable_tool_result(...)` redaction/allowlisting.
2. Unit tests for cache adapter write/read behavior using a fake Redis client.
3. Message service tests that streaming and non-streaming `tool_call` events are
   sent to the cache adapter.
4. Prompt rendering tests in `pal-agents` for externally supplied previous tool
   results.
5. Cross-pod simulation: write from one process, read from another.
6. Failure tests: Redis timeout/unavailable should not break chat or streaming.

---

## Files Summary

### pal-mono

| File | Change |
| ---- | ------ |
| `pyproject.toml` | Add Redis Python client |
| `local.env.example` | Add cache configuration |
| `services/tool_result_cache.py` | New ElastiCache adapter |
| `services/message_service/_implementation.py` | Write sanitized tool events and read previous results before agent run |
| `tests/services/message_service/test_tool_call_events.py` | Cover cache write hooks |

### pal-agents

| File | Change |
| ---- | ------ |
| `src/pal_agents/input.py` | Add external previous tool result field, or rely on `RuntimeContext` extra field |
| `src/pal_agents/engine/__init__.py` | Prefer external previous tool results over process-local cache |
| `src/pal_agents/engine/_tool_result_cache.py` | Remove after ElastiCache cutover |
| `tests/` | Add/update previous tool result rendering tests |

---

## Decisions

| Question | Decision |
| -------- | -------- |
| Backend | AWS ElastiCache for recent tool-result context |
| Data operations | Use Redis/Valkey client, not Boto3 |
| Key shape | `tool-results:v1:{conversation_id}` |
| Value shape | Sanitized compact JSON entries with `result_summary`, optional `input_summary`, and allowlisted `cacheable_result` |
| Prompt injection shape | Strip to `tool_name` plus `tool_result` by default |
| Raw results | Do not cache raw tool payloads |
| Secrets/PII | Redact/drop before caching |
| List limit | No count trimming by default |
| Expiry | Redis key TTL |
| Failure behavior | Best-effort; log/metric and continue |
| DB table changes | Not required for the cache migration |

## Remaining Open Questions

1. ElastiCache deployment shape: serverless vs replication group.
2. Authentication mode: Secrets Manager password vs IAM auth.
3. Exact TTL for production: 30 minutes vs longer conversation window.
4. Whether to use `PalInput.previous_tool_results` or
   `RuntimeContext.previous_tool_results` as the final `pal-agents` API.
5. Which tool families need custom `result_summary` builders first.
