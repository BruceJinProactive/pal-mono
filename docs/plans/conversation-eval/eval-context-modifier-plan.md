# Plan: Eval customer_phone injection via context_modifier

## Context

After removing `"api"` from the customer_phone channel list (`fix/remove-api-from-customer-phone`),
eval runs no longer get bogus email-derived phone numbers. However, `customer_phone` is now `None`
for API-channel evals, so the LLM doesn't have the phone pre-populated like it would in a real
voice/SMS call. The eval scenarios simulate phone customers but run over the API channel.

We need the eval system to inject `customer_phone` into the agent's RuntimeContext without modifying
the public API schema (`Message.Metadata`). The approach: add an optional `context_modifier` callback
to `get_chat_response_async` that only the eval `InProcessDriver` uses. This also sets up a pattern
for future overrides (e.g. `spec_modifier` for `submit_orders`).

### How the phone flows from YAML → RuntimeContext

```
Scenario YAML                         _runner.py                        _driver_factory.py
─────────────                         ──────────                        ──────────────────
expected_tool_calls:             →  _infer_customer_phone(scenario)  →  create_driver(
  - tool: toast_takeout_create...       returns "5551234567"               customer_phone="5551234567")
    args:                                                                        │
      customer:                                                                  ▼
        phone: '5551234567'
                                  InProcessDriver                     get_chat_response_async
                                  ───────────────                     ──────────────────────
                                  self.customer_phone = "5551234567"  context_modifier=lambda ctx:
                                  builds context_modifier lambda  →     ctx.customer_phone = "5551234567"
                                                                              │
                                                                              ▼
                                                                      RuntimeContext.customer_phone
                                                                      = "5551234567"
                                                                      (LLM sees "Customer Phone: 5551234567")
```

---

## Step 0: Git setup

```bash
cd /Users/ryou/Dev/Palona/pal-mono
git checkout main && git pull
git checkout -b feat/eval-context-modifier
```

---

## Step 1: `services/message_service/_implementation.py`

**What:** Add optional `context_modifier` param to `get_chat_response_async` (line 140).
Apply it immediately after RuntimeContext is constructed (after line 239).

**Current signature** (line 140-141):
```python
async def get_chat_response_async(
    session: AsyncSession, message: Message, request_context: RequestContext
) -> list[Message]:
```

**New signature:**
```python
from collections.abc import Callable

async def get_chat_response_async(
    session: AsyncSession,
    message: Message,
    request_context: RequestContext,
    context_modifier: Callable[[RuntimeContext], None] | None = None,
) -> list[Message]:
```

**Apply modifier** — insert after RuntimeContext construction (after line 239):
```python
            runtime_context = RuntimeContext(
                ...
            )

            if context_modifier:
                context_modifier(runtime_context)
```

**Note:** The `Callable` import needs to be added. `RuntimeContext` is already imported
(from `pal_agents.input`).

---

## Step 2: `services/message_service/__init__.py`

**What:** Thread `context_modifier` through the public facade (lines 22-41).

**Current** (lines 22-41):
```python
@traced("Message Service Async Processing")
async def get_chat_response_async(
    session: AsyncSession, message: Message, request_context: RequestContext
) -> list[Message]:
    ...
    return await _implementation.get_chat_response_async(
        session, message, request_context
    )
```

**New:**
```python
from collections.abc import Callable
from pal_agents.input import RuntimeContext

@traced("Message Service Async Processing")
async def get_chat_response_async(
    session: AsyncSession,
    message: Message,
    request_context: RequestContext,
    context_modifier: Callable[[RuntimeContext], None] | None = None,
) -> list[Message]:
    ...
    return await _implementation.get_chat_response_async(
        session, message, request_context, context_modifier=context_modifier
    )
```

---

## Step 3: `services/eval_service/_runner.py`

**What:** Add `_infer_customer_phone` helper (mirrors pal-agents `run_loop.py:1341-1361`).
Call it in `_run_scenario_for_mode` and pass result to `create_driver`.

**Add helper** (above `_run_scenario_for_mode` at ~line 343):
```python
def _infer_customer_phone(scenario: EvalScenario) -> str | None:
    """Extract customer phone from scenario expected_tool_calls.

    Mirrors pal-agents run_loop._infer_customer_phone: checks
    expected_tool_calls[*].args.customer.phone for the first non-empty value.
    """
    for tc in scenario.expected_tool_calls:
        customer = tc.args.get("customer", {})
        phone = str(customer.get("phone", "")).strip()
        if phone:
            return phone
    return None
```

**Update `_run_scenario_for_mode`** (lines 366-368):

Current:
```python
    driver = create_driver(
        driver_mode, recipient_id, channel=channel, scenario_id=scenario.scenario_id
    )
```

New:
```python
    customer_phone = _infer_customer_phone(scenario)
    driver = create_driver(
        driver_mode, recipient_id, channel=channel,
        scenario_id=scenario.scenario_id, customer_phone=customer_phone,
    )
```

---

## Step 4: `services/eval_service/_driver_factory.py`

**What:** Accept `customer_phone` and pass it to `InProcessDriver`.

**Current** `create_driver` signature (line 14-18):
```python
def create_driver(
    driver_mode: str,
    project_identifier: str,
    channel: str = "api",
    scenario_id: str | None = None,
) -> InProcessDriver:
```

**New:**
```python
def create_driver(
    driver_mode: str,
    project_identifier: str,
    channel: str = "api",
    scenario_id: str | None = None,
    customer_phone: str | None = None,
) -> InProcessDriver:
```

**Update InProcessDriver construction** (lines 49-53):

Current:
```python
        return InProcessDriver(
            recipient_identifier=project_identifier,
            sender_identifier=sender,
            channel=channel,
        )
```

New:
```python
        return InProcessDriver(
            recipient_identifier=project_identifier,
            sender_identifier=sender,
            channel=channel,
            customer_phone=customer_phone,
        )
```

---

## Step 5: `services/eval_service/_inprocess_driver.py`

**What:** Accept `customer_phone`, build a `context_modifier` lambda, pass it to
`get_chat_response_async`.

**Update `__init__`** (lines 25-34):

Current:
```python
    def __init__(
        self,
        recipient_identifier: str,
        sender_identifier: str = "eval-user@test.com",
        channel: str = "api",
    ) -> None:
        self.recipient_identifier = recipient_identifier
        self.sender_identifier = sender_identifier
        self.channel = Channel(channel)
        self.last_conversation_id: str | None = None
```

New:
```python
    def __init__(
        self,
        recipient_identifier: str,
        sender_identifier: str = "eval-user@test.com",
        channel: str = "api",
        customer_phone: str | None = None,
    ) -> None:
        self.recipient_identifier = recipient_identifier
        self.sender_identifier = sender_identifier
        self.channel = Channel(channel)
        self.last_conversation_id: str | None = None
        self.customer_phone = customer_phone
```

**Update `send_turn`** (lines 53-61):

Current:
```python
        async with AsyncSessionLocal() as session:
            try:
                request_context = RequestContext()
                response_messages = await get_chat_response_async(
                    session=session,
                    message=chat_message,
                    request_context=request_context,
                )
```

New:
```python
        phone = self.customer_phone

        def _context_modifier(ctx: RuntimeContext) -> None:
            if phone:
                ctx.customer_phone = phone

        async with AsyncSessionLocal() as session:
            try:
                request_context = RequestContext()
                response_messages = await get_chat_response_async(
                    session=session,
                    message=chat_message,
                    request_context=request_context,
                    context_modifier=_context_modifier,
                )
```

**Add import** at top of file:
```python
from pal_agents.input import RuntimeContext
```

---

## Test updates

### `tests/services/eval_service/test_inprocess_driver.py`

- **`TestBuildMessage`**: No change needed (doesn't test customer_phone).
- **`TestSendTurn`**: Verify `get_chat_response_async` is called with `context_modifier` kwarg.
  Add a test for a driver with `customer_phone="5551234567"` that asserts the modifier sets
  `ctx.customer_phone`.

### `tests/services/eval_service/test_driver_factory.py`

- Add test: `create_driver(..., customer_phone="5551234567")` → driver.customer_phone == "5551234567"
- Add test: `create_driver(...)` without customer_phone → driver.customer_phone is None

### `tests/services/eval_service/test_runner.py`

- Line 313 asserts `create_driver` call args. Update to include `customer_phone=...` kwarg
  matching whatever `_infer_customer_phone` returns from the test scenario fixture.
- Add unit test for `_infer_customer_phone`:
  - Scenario with `expected_tool_calls[*].args.customer.phone` → returns phone
  - Scenario with no customer in args → returns None
  - Scenario with empty phone → returns None

---

## Files modified

| File | Change |
|------|--------|
| `services/message_service/_implementation.py` | Add optional `context_modifier` param (line 140), apply after RuntimeContext (line 239) |
| `services/message_service/__init__.py` | Thread `context_modifier` through facade (line 22) |
| `services/eval_service/_runner.py` | Add `_infer_customer_phone` helper, call in `_run_scenario_for_mode` (line 366) |
| `services/eval_service/_driver_factory.py` | Accept + pass `customer_phone` param (line 14, 49) |
| `services/eval_service/_inprocess_driver.py` | Store phone (line 25), build modifier + pass to service (line 53) |
| `tests/services/eval_service/test_inprocess_driver.py` | Test context_modifier is passed, test phone injection |
| `tests/services/eval_service/test_driver_factory.py` | Test customer_phone passthrough |
| `tests/services/eval_service/test_runner.py` | Update create_driver assertion, add _infer_customer_phone tests |

## Impact

| Flow | Impact |
|------|--------|
| **Chat API route** (`api/routes/chat/chat.py`) | Unaffected — passes no modifier, default `None` |
| **Streaming path** | Unaffected — not touched |
| **Voice evals** | Unaffected — uses separate `_voice_eval_runner` pipeline |
| **InProcessDriver** | Only eval caller, only one that passes modifiers |

## Future extensibility

The same pattern supports a `spec_modifier: Callable[[Spec], None] | None = None` param
for overriding agent spec fields (e.g. `submit_orders=False`). Would be applied after
`construct_agent_spec` at line 206, threaded through the same chain.

## Verification

1. `./scripts/validate.sh`
2. `uv run pytest tests/services/message_service/ tests/services/eval_service/ -x -q`
3. Re-run eval via API and confirm customer phone/name fields match expected values in results
