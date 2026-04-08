# P1-D1: InProcessDriver + UserSimulator wiring

**Type:** CODE
**Est. Hours:** 12 (1.5 engineering days)
**Blocked by:** P1-C2 (eval service — done), P1-C3 (eval API routes — done)

---

## Background

The eval runner uses `HTTPDriver` from pal-agents to send test messages to `/v1/chat/`. Since the eval runs inside the same pal-mono process, this means the API makes HTTP calls to itself — requiring a `EVAL_API_BASE_URL` env var per environment. On LAT, the default `localhost:8000` doesn't resolve correctly, causing all 38 scenarios to fail silently.

Additionally, scenarios with `ai_driven` turns (where a simulated user reacts dynamically to agent responses) are not handled — the runner just stringifies the `UserTurn` object. pal-agents has a generic `UserSimulator` class in `evals/eval_multi_turn_agents.py` but it's not exported in the SDK.

This plan has three parts:

1. **InProcessDriver** (pal-mono) — call `get_chat_response_async` directly, no HTTP
2. **UserSimulator extraction** (pal-agents) — move to SDK, make configurable
3. **Wire ai_driven turns** (pal-mono) — use UserSimulator for dynamic turns

Parts 1 and 2 are independent. Part 3 depends on Part 2.

---

## Part 1: InProcessDriver (pal-mono)

**Goal:** Replace HTTPDriver with a driver that calls the chat service in-process.

### Files to create

#### `services/eval_service/_inprocess_driver.py`

```python
from __future__ import annotations
from pal_agents.evals.drivers.protocol import AgentDriver, ConversationTurn, TurnResult
from api.schemas.chat.message import Message, TextObject, Metadata, AuthorType
from db.session import AsyncSessionLocal
from services.message_service import get_chat_response_async
from utils.request_context import RequestContext

class InProcessDriver(AgentDriver):
    """Driver that calls get_chat_response_async directly.

    No HTTP, no URL config. Owns its own AsyncSessionLocal per turn.
    """
    def __init__(self, recipient_identifier: str, sender_identifier: str = "eval-user@test.com") -> None: ...
    async def send_turn(self, message: str, conversation_history: list[ConversationTurn]) -> TurnResult: ...
    def _build_message(self, text: str) -> Message: ...
    def _extract_response_text(self, response_messages: list[Message]) -> str: ...
```

Key design decisions:
- Each `send_turn` opens its own `AsyncSessionLocal` — eval background task already owns its session for result writes, driver needs a separate one for chat processing
- Constructs `Message` matching the same shape `chat.py` expects: `author_type="user"`, `channel="api"`, `type="text"`, `metadata.testing=True`
- `testing=True` flag ensures DD traces are dropped (same as HTTPDriver's `metadata.testing`)
- Extracts response text from the returned `list[Message]` by finding the last agent message

### Files to modify

#### `services/eval_service/_driver_factory.py`

- Remove `HTTPDriver` import and `EVAL_API_BASE_URL` env var
- `create_driver("http", project_id)` returns `InProcessDriver(recipient_identifier=project_id)`
- Keep `driver_mode` parameter name for API compatibility (rename is a separate concern)

### Acceptance criteria

- [ ] `POST /v1/eval/run { driver: "http" }` works on any environment without `EVAL_API_BASE_URL`
- [ ] `InProcessDriver.send_turn()` returns agent response text in `TurnResult.content`
- [ ] Each turn creates and closes its own DB session
- [ ] `metadata.testing = True` is set (DD traces suppressed)
- [ ] Existing unit tests in `tests/services/eval_service/test_driver_factory.py` updated
- [ ] New unit tests for `InProcessDriver` with mocked `get_chat_response_async`

---

## Part 2: UserSimulator extraction (pal-agents)

**Goal:** Move the generic `UserSimulator` from eval scripts into the `evals` SDK package so pal-mono can import it.

### Current location

`evals/eval_multi_turn_agents.py:301` — `class UserSimulator`
- Uses `AmazonBedrockModel` (Claude Sonnet via Bedrock)
- `generate_user_message(persona, scenario, expected_outcome, history, turn_number) -> str`
- Returns `[END]` when conversation should conclude
- Hardcoded model, no configurability

### Files to create (pal-agents)

#### `evals/simulator.py`

```python
class UserSimulator:
    """LLM-based simulated user for multi-turn eval conversations.

    Generates contextual user messages based on persona, scenario, and goal.
    Returns [END] when the conversation should conclude.
    """
    def __init__(self, model_id: str = "us.anthropic.claude-sonnet-4-20250514-v1:0") -> None: ...
    async def generate_user_message(
        self,
        persona: str,
        scenario: str,
        goal: str,
        conversation_history: list[ConversationTurn],
        turn_number: int,
    ) -> str: ...
```

Changes from current:
- Accept `model_id` parameter (default Claude Sonnet 4)
- Use `ConversationTurn` from `evals.drivers.protocol` instead of DeepEval `Turn`
- Keep prompt template from `eval_multi_turn_agents.py` (proven in production evals)

### Files to modify (pal-agents)

#### `evals/__init__.py`

- Export `UserSimulator` from `evals.simulator`

#### `evals/eval_multi_turn_agents.py`

- Replace inline `UserSimulator` class with import from `evals.simulator`
- Verify existing eval scripts still work

### Acceptance criteria

- [ ] `from pal_agents.evals.simulator import UserSimulator` works
- [ ] `pip install pal-agents[eval]` includes simulator
- [ ] `generate_user_message()` returns realistic user messages given persona + scenario
- [ ] Returns `[END]` when conversation goal is met
- [ ] Existing `eval_multi_turn_agents.py` scripts work unchanged
- [ ] Unit tests for simulator in `evals/tests/test_simulator.py`

---

## Part 3: Wire ai_driven turns in pal-mono (DONE)

**Goal:** Handle `ai_driven` scenario turns using the UserSimulator.

**Status:** Completed — uses `UserSimulator` from pal-agents SDK v0.2.242 (`pal_agents.evals.simulator`). Part 2 shipped alongside this work.

### Files to modify

#### `services/eval_service/_runner.py`

Update `_run_conversation()`:

```python
async def _run_conversation(
    driver: AgentDriver,
    scenario: EvalScenario,
    simulator: UserSimulator | None = None,
) -> ConversationRecord:
    record = ConversationRecord(scenario=scenario)
    history: list[ConversationTurn] = []

    for turn_number, turn in enumerate(scenario.user_turns):
        if isinstance(turn, UserTurn) and turn.type == UserTurnType.AI_DRIVEN:
            # Use simulator to generate dynamic user message
            if simulator is None:
                simulator = UserSimulator()
            message = await simulator.generate_user_message(
                persona=scenario.persona,
                scenario=scenario.scenario,
                goal=turn.goal or "",
                conversation_history=history,
                turn_number=turn_number,
            )
            if message == "[END]":
                break
        elif isinstance(turn, UserTurn):
            message = turn.text or turn.goal or ""
        else:
            message = str(turn)

        result: TurnResult = await driver.send_turn(message, history)
        # ... rest unchanged
```

#### `services/eval_service/_runner.py` — `_run_eval_background()`

- Instantiate `UserSimulator` once per eval run
- Pass to `_run_conversation(driver, scenario, simulator)`

### Files created

#### `services/eval_service/_user_simulator.py`

- Re-exports `UserSimulator` from `pal_agents.evals.simulator`
- Defines `END_SENTINEL = "[END]"` constant used by the runner

### Acceptance criteria

- [x] Scripted turns work exactly as before (no regression)
- [x] `ai_driven` turns generate contextual user messages via simulator
- [x] Conversation ends when simulator returns `[END]`
- [x] Simulator instantiated once per eval run (not per scenario)
- [x] Unit tests with mocked simulator for ai_driven turn handling

---

## Execution Order

```
Part 1 (InProcessDriver)          Part 2 (UserSimulator extraction)
    pal-mono ~4h                       pal-agents ~4h
         |                                  |
         |                                  v
         |                          Part 3 (Wire ai_driven turns)
         |                               pal-mono ~4h
         v                                  |
    Deploy + verify                    Deploy + verify
    (scripted scenarios work)          (ai_driven scenarios work)
```

Part 1 unblocks immediate testing on all environments. Part 2 + 3 can follow.

---

## Dependency Summary

| Part | Repo | Effort | Depends on | Unblocks |
|------|------|--------|------------|----------|
| Part 1: InProcessDriver | pal-mono | 4h | — | Eval works on LAT/STG/PRD |
| Part 2: UserSimulator extraction | pal-agents | 4h | — | Part 3 |
| Part 3: Wire ai_driven turns | pal-mono | 4h | Part 2, pal-agents release | ai_driven scenarios |
