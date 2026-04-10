# Tool Call Records Table — Conversation Tool Execution Tracking

**Date**: 2026-04-08
**Author**: System
**Status**: Implemented

## Context

The conversation evaluator needs to track tool execution outcomes across conversations to enable failure detection, debugging, and metric computation. Previously, tool call data existed only transiently in agent memory and was lost after conversation completion.

Without persistent tool call records, there is no way to:
- Detect recurring tool failures across conversations
- Compute tool reliability metrics for evaluation pipelines
- Debug tool execution issues after a conversation ends
- Track tool execution duration and performance patterns

## Decision

Add a new `tool_call_records` table to persist tool execution outcomes per conversation, with an async repository for fire-and-forget recording.

### New Table: `tool_call_records`

SQLAlchemy model tracking tool execution outcomes:
- `id` (UUID) — primary key
- `conversation_id` (UUID, indexed) — references `conversations.id` via DB foreign key
- `tool_name` (VARCHAR 255) — name of the tool that was called
- `is_error` (BOOLEAN, default false) — whether execution resulted in error
- `error_type` (VARCHAR 255, nullable) — error category if applicable
- `duration_ms` (INTEGER, nullable) — execution duration in milliseconds
- `result` (VARCHAR 1000, nullable) — truncated result or error message
- `created_at` (TIMESTAMP WITH TIMEZONE, server default now())

### Repository: `ToolCallRecordRepositoryAsync`

Two async methods:
- `add_tool_call_record()` — fire-and-forget insertion (commits immediately)
- `get_tool_calls_by_conversation()` — retrieve all records for a conversation

Repository follows established async-only pattern with error handling and rollback on SQLAlchemy exceptions.

### Relationship: `Conversation.tool_call_records`

Adds a back-populating relationship to the Conversation model:
```python
tool_call_records: Mapped[list["ToolCallRecord"]] = relationship(
    "ToolCallRecord", back_populates="conversation"
)
```

## Consequences

### Benefits
- Enables cross-container persistence of tool execution data for evaluator metrics
- Foundation for tool failure tracking (PAL-9004)
- Supports debugging of tool issues after conversation completion
- Allows aggregate analysis of tool reliability patterns

### Tradeoffs
- Additional table increases schema surface area
- Fire-and-forget commits bypass transaction boundaries (intentional for non-critical data)
- Result field capped at 1000 chars — full payloads not stored

## Related
- `db/tables/tool_call_records.py` — SQLAlchemy model
- `db/repositories/tool_call_record_repository.py` — async repository
- `tests/db/repositories/test_tool_call_record_repository.py` — 8 unit tests
- `db/migrations/versions/2026-04-08_51e1be7bca04_add_tool_call_records_table.py` — Alembic migration
- PAL-9004 — Tool call failure tracking (parent epic)
