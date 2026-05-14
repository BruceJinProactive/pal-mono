# Record: HTTP-over-ASGI eval driver (`HttpVoiceDriver`)

**Date:** 2026-05-08
**Jira:** PAL-10389 (follow-up)

## What shipped

### 1. `HttpVoiceDriver` — new eval driver

`services/eval_service/_http_voice_driver.py::HttpVoiceDriver` speaks to pal-mono over its HTTP contract rather than calling service modules directly. Text-transport analogue of a LiveKit voice call:

```
init      POST /v1/internal/voice/init        ({..., "testing": true})
turn N    POST /v1/chat/completions           (streamed SSE)
...
teardown  POST /v1/internal/voice/end-call
```

Transport is `httpx.AsyncClient(transport=ASGITransport(app=api.main.app))` — in-process, no real network, but exercises the same code path the LiveKit agent worker uses in production.

Wired into `services/eval_service/_driver_factory.py` as `driver_mode="http_voice"`. The legacy `driver_mode="http"` (misnamed; actually in-process) is kept for backward compatibility.

### 2. Auto eval-safety at the service layer

`apply_eval_safety` moved from `services/eval_service/_safety.py` to `utils/eval_safety.py` (the old path remains as a backward-compat shim). This breaks a potential circular dependency between `message_service` and `eval_service`.

`services/message_service/_implementation.py` now auto-applies `apply_eval_safety(spec)` whenever the conversation is flagged `is_test=True`, via a new helper `_apply_test_safety_if_needed` called from both spec-construction sites (non-streaming `_dispatch_agent_async` and streaming `get_chat_response_stream`). Runs before any caller-provided `spec_modifier`, so deliberate overrides still win.

Every eval caller path now gets side-effect hardening for free as long as the first message of the conversation carries `metadata.testing=True`:

- `InProcessDriver` — was already passing `Metadata(testing=True)` on every turn; the `spec_modifier=apply_eval_safety` default it still installs is now redundant but harmless (idempotent).
- `HttpVoiceDriver` — sends `testing=True` in the `/internal/voice/init` payload; the route stamps `metadata.testing=True` on the bootstrap Message, which flows into `Conversation.is_test=True`.
- LiveKit real-voice evals — same mechanism whenever the scenario runner sets `testing=True` on init.

### 3. Runner `aclose` hook

`services/eval_service/_runner.py::_run_conversation` now calls `driver.aclose()` (via `getattr(driver, "aclose", None)`) after the turn loop and before tool-call extraction. `HttpVoiceDriver.aclose()` performs `POST /internal/voice/end-call` and populates `last_conversation_id` from the response so the existing tool-call extractor can query the DB by conversation. Legacy drivers without `aclose` (e.g. `InProcessDriver`) are unaffected — the hook is best-effort, and any exception from `aclose` is caught and logged so tool-call extraction still runs against whatever `last_conversation_id` was set.

## Why

Following review feedback on PAL-10389 PR-1, the original plan — have the in-process eval driver call `voice_call_service.bootstrap_call` / `finalize_call` directly — was scrapped. That plan would have had the driver reach past the pal-mono service boundary, coupling eval correctness to internal implementation. A refactor like PAL-10371 (move `create_voice_message` into a service wrapper) would have to be mirrored in the eval driver every time.

The new driver only depends on three HTTP routes. Service refactors inside `services/` or `db/` cannot silently break the eval surface: if the HTTP contract changes, the driver sees it immediately. This also means:

1. **One scenario = one conversation, by construction.** Voice-channel DB plumbing keys `Conversation` lookup on `call_id`, not on status. The `CLOSING → CLOSED → new-row` rotation that breaks api-channel evals (observed in the Sonny's BBQ Pick-4 Combo trace) physically cannot occur on this path.
2. **Tool-call extraction becomes correct without aggregation hacks.** A single `call_id` resolves to a single `Conversation.id`, so `_extract_tool_calls_from_db(conversation_id)` on the record's `last_conversation_id` captures every tool the agent invoked during the scenario.
3. **Regression surface is maximal.** Request parsing, middleware, route dispatching, streaming semantics, error mapping — all exercised for free.

## No scenario file changes required

Existing eval scenarios (YAML / DB-stored) do NOT change. A scenario's content is persona + user turns + expected tool calls + evaluators — all transport-agnostic. Switching from `driver_mode="http"` (legacy InProcessDriver) to `driver_mode="http_voice"` on the same scenario runs the identical dialogue over the HTTP boundary, flips `channel` from `api` to `voice`, and gets the rotation/safety benefits above. Callers control this via the `driver` field on `RunEvalRequest`.

## Layering

`HttpVoiceDriver` imports the FastAPI app via `importlib.import_module("api.main")` inside `create_driver`. This is a deliberate runtime DI seam: the static `services -> api` import would violate the `api -> services -> db` layered-architecture contract, but the `http_voice` driver genuinely needs the app object to dispatch ASGI. The `importlib` indirection is isolated to one well-commented site in the factory; everything else in `services/eval_service/` stays layer-clean. An alternative is to plumb `app` as a parameter from the api-layer route handler down through `create_eval_run` / `_run_eval_background` / `_run_scenario_for_mode` / `create_driver` — deferred as a separate cleanup if/when more modules need app-level DI.

`apply_eval_safety` now lives in `utils/eval_safety.py` (pure function, external deps only — satisfies the `utils must be isolated` contract). The old import path `services.eval_service._safety` is preserved as a re-export.

## What did not change

- Existing `driver_mode="http"` / `InProcessDriver` — untouched. The `spec_modifier=apply_eval_safety` default it installs is now redundant (the service layer auto-applies on `is_test=True`) but harmless.
- `voice` / LiveKit driver mode — untouched, and now picks up auto-safety whenever scenarios set `testing=True`.
- Eval evaluators, `ConversationRecord`, tool-call extraction helper — untouched.
- Scenario files — untouched. Switching a scenario to `driver_mode="http_voice"` is a runner configuration change, not a scenario rewrite.

## Tests

- **`tests/services/eval_service/test_http_voice_driver.py`** (14 tests) — covers lazy init, init-runs-once, stable `call_id` across turns, `call_id` traceability suffix, `aclose` populates `last_conversation_id`, conversation replay in end-call body, idempotent `aclose`, post-close `send_turn` rejection, init/chat/end-call error handling, SSE stream parsing (missing `[DONE]` sentinel, chunk accumulation). Explicitly asserts `testing=True` in the init payload. Uses a stub FastAPI app wired to `ASGITransport` — no `httpx` mocks, real transport.
- **`tests/services/eval_service/test_driver_factory.py::TestCreateDriverHttpVoice`** (4 tests) — covers `"http_voice"` dispatch, customer phone → caller number mapping, scenario-id traceability in `call_id`, uniqueness of `call_id` across consecutive calls.
- **`tests/services/eval_service/test_runner.py::TestRunConversationAcloseHook`** (3 tests) — covers ordering (`aclose` runs before tool-call extraction), graceful handling of drivers without `aclose`, and tolerance of `aclose` failures.
- **`tests/services/message_service/test_eval_safety_auto_apply.py`** (5 tests) — covers auto-application when `conversation.is_test=True`, pass-through when `is_test=False`, `ValueError` tolerance (missing conversation), unexpected-exception logging, and verification that the `services.eval_service._safety.apply_eval_safety` re-export is the same function object as the canonical `utils.eval_safety.apply_eval_safety`.
- All 770 pre-existing `tests/services/eval_service/`, `tests/services/message_service/`, and `tests/api/routes/internal/` tests pass unchanged.

## Validation

`./scripts/validate.sh --check` passes: black / ruff / isort / pyright / lint-imports / toml-sort all clean. `api → services → db` layered contract remains intact.

## Follow-ups

1. Switch all eval scenarios to `driver_mode="http_voice"` once the team signs off. No scenario content changes, just the runner config.
2. Consider deprecating `driver_mode="http"` (legacy `InProcessDriver`) once all runners migrate. The historical misnomer (`"http"` means in-process, not HTTP) can then be cleaned up.
