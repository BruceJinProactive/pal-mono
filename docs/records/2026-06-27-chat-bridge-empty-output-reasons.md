# Chat Bridge Empty Output Reasons

> **Date:** 2026-06-27

## Context

The voice SLO dashboard showed most unhealthy Chat Turn Bridge outcomes under
the single `failure/empty_output` reason. That bucket was too broad to diagnose:
a textless bridge completion could mean no stream, no yielded chunks, only empty
chunks, URL filtering removing all speakable content, or pal-agents emitting
tool artifacts without assistant text.

## What changed

- Split generic `failure/empty_output` bridge outcomes into low-cardinality
  `reason` values on the existing `chat.completions.turn.bridge` metric:
  - `empty_no_stream`
  - `empty_no_chunks`
  - `empty_only_empty_chunks`
  - `empty_url_filtered`
  - `empty_tool_only`
  - `empty_unknown`
- Added non-PII structured logging when a voice bridge completes without
  speakable assistant output.
- Added a message-service bridge observation event for pal-agents tool artifacts
  so tool-only streams can be distinguished from streams that simply yielded no
  chunks.

## Dashboard behavior

The metric name and labels are unchanged except for the new `reason` values, so
the existing Bridge Outcome Rate panel should show the new categories
automatically because it groups by `(outcome, reason)`.

The SLO numerator remains `outcome="success", reason="completed"`. All new
empty-output categories remain `outcome="failure"`, so the existing SLO and
budget-burn queries continue to count them as bad events.

## Tests

- `uv run pytest -q tests/api/routes/chat/test_chat_completions.py`
