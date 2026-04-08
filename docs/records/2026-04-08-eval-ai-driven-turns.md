# Eval AI-Driven Turns + Caller-Provided Channel Identifier

**Date**: 2026-04-08
**Author**: Jacob Wang
**Status**: Implemented

## Context

The eval runner (P1-C2) only supported static turns — fixed text sent to the agent. Real conversations are dynamic, so we needed AI-driven turns using `UserSimulator` from pal-agents SDK. Additionally, the runner was looking up channel identifiers by project UUID, which failed on LAT because the chat service resolves projects by channel identifier (e.g. `api:pokeworks-san_jose`), not by UUID.

## Changes

### AI-Driven Turns (P1-C3 Part 3)

- Wired `UserSimulator` (from `pal_agents.evals.simulator`, SDK v0.2.242) into `_run_conversation()` for `TurnType.AI_DRIVEN` scenario turns
- Simulator generates contextual user messages based on persona, scenario, goal, and conversation history
- `END_SENTINEL = "[END]"` stops the conversation early when the simulator decides it's done
- Re-export from SDK in `services/eval_service/_user_simulator.py`

### Caller-Provided Channel Identifier

- `RunEvalRequest` now requires `channel_identifier` (e.g. `"api:pokeworks-san_jose"`)
- Threaded through: API route → `create_eval_run()` → `_schedule_eval_background()` → `_run_eval_background()`
- Replaced `_resolve_channel_identifier()` (DB lookup) with `_parse_channel_identifier()` (simple string split)
- Removed `get_project_by_id_async` dependency from eval runner

### Why caller-provided instead of DB lookup

Projects can have multiple channel identifiers across different channels (api, voice, etc.). Auto-resolving by picking the first match was fragile and ambiguous. The caller knows which channel they want to evaluate against, so they pass it explicitly.

## Files

- `services/eval_service/_runner.py` — `_run_conversation` handles AI_DRIVEN turns, `_parse_channel_identifier` replaces DB lookup
- `services/eval_service/_user_simulator.py` — re-export of `UserSimulator` + `END_SENTINEL`
- `services/eval_service/_driver_factory.py` — `channel` param on `create_driver`
- `services/eval_service/_inprocess_driver.py` — `channel` param on `InProcessDriver`
- `api/schemas/eval/requests.py` — `channel_identifier` field
- `api/routes/eval/_implementation.py` — passes `channel_identifier` to service
- `tests/services/eval_service/test_runner.py` — 3 new AI-driven tests, all updated for channel_identifier

## Related

- P1-C2: `docs/records/2026-03-28-eval-platform-schema.md` — eval schema foundation
- P1-C3: `docs/records/2026-03-31-eval-api-routes.md` — API routes this builds on
- `docs/plans/conversation-eval/P1-inprocess-driver-plan.md` — implementation plan
