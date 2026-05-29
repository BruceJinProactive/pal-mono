# Voice SLO Metrics

> **Date:** 2026-05-28

## Context

The `pal-mono voice` observability review identified that HTTP metrics in Grafana were only proxies for two proposed SLOs:

- **Voice call close** — `pal-mono` must receive the end-call report, close the conversation, and update the phone call record.
- **Chat turn bridge** — `/v1/chat/completions` must complete a voice turn through `pal-mono` to the agent stack with non-empty assistant output, no fallback/error path, `[DONE]`, and successful persistence.

HTTP 2xx alone was insufficient because `end_voice_call` can return body-level errors with HTTP 200, and chat streaming could emit `[DONE]` after fallback or empty error chunks.

## What changed

- Added the OTel counter `voice.call.close`, exported to Mimir as `voice_call_close_total`, with `outcome` and `reason` labels.
- Added the OTel histogram `voice.call.close.duration`, exported as `voice_call_close_duration_milliseconds`, measured through the close/update transaction.
- Added the OTel counter `chat.completions.turn.bridge`, exported as `chat_completions_turn_bridge_total`, with `outcome`, `reason`, and `framework` labels.
- Added the OTel histogram `chat.completions.turn.bridge.duration`, exported as `chat_completions_turn_bridge_duration_milliseconds`, measured from request receipt through terminal stream outcome.

## Label lifecycle

`framework` is a migration-era label used to compare `pal_agents` against the legacy `agno` path. Once Agno is fully removed from the codebase and all voice chat traffic uses pal-agents, deprecate this label from dashboards/SLO queries and remove it from future instrumentation if it no longer adds diagnostic value.

## SLO semantics

- Voice close success is `outcome="success", reason="completed"`.
- Voice close failures include `conversation_not_found`, `db_close_failed`, and `phone_call_missing`. Billing and eval dispatch remain diagnostics and do not change the close SLO result.
- Chat bridge success is `outcome="success", reason="completed"`.
- Chat bridge failures include `empty_output`, `request_persist_failed`, `response_persist_failed`, `fallback_response`, and `client_cancelled`.

## Tests

- `tests/api/routes/internal/test_voice_slo_metrics.py`
- `tests/api/routes/chat/test_chat_completions.py`
