# Eval `spec_modifier` — prevent real order submission during eval runs

**Date**: 2026-04-28
**Status**: Implemented
**Related**: `docs/records/2026-03-28-eval-platform-schema.md`, `docs/plans/conversation-eval/eval-context-modifier-plan.md`, ADR-007 (pal-agents migration)

## Context

Eval runs use `services/eval_service/_inprocess_driver.py::InProcessDriver`, which calls `message_service.get_chat_response_async` directly against real project configs loaded from the DB. The pal-agents `Spec` is built by `services/agent_service/construct_agent_spec`, which reads `ProjectIntegration` rows and passes values straight through to pal-agents spec builders.

Concretely, `services/agent_service/_pal_agent_tool_registry.py::_build_toast_v3_spec` forwards the `submit_orders` field from the project's Toast integration config into `ToastSpec`. pal-agents' Toast provider (`providers/toast/_implementation.py:498`) gates real `POST /orders` calls on `spec.toast.submit_orders`:

- `submit_orders=False` → order is priced and a payment link is generated, **no order is placed**.
- `submit_orders=True` → order **is submitted for real**.

For pilot projects with `submit_orders: true` in their live config, running an eval scenario would place real Toast orders against the real restaurant. pal-agents keeps its own internal evals safe by hard-coding `submit_orders=False` in every snapshot spec and test, but pal-mono had no equivalent override — the eval `InProcessDriver` trusted whatever the DB said.

The `context_modifier` pattern (shipped earlier; see `eval-context-modifier-plan.md`) solved the analogous problem for `RuntimeContext` (injecting `customer_phone` without polluting the public `Message.Metadata` schema). Its "Future extensibility" section explicitly called out `spec_modifier` as the symmetric hook. This record captures executing on that.

## What shipped

### New public hook: `spec_modifier`

`message_service.get_chat_response_async` now accepts an optional
`spec_modifier: Callable[[Spec], None] | None`, symmetric to `context_modifier`. It runs exactly once, immediately after `construct_agent_spec` returns and before `PalAgent(spec=spec)` is instantiated. Production callers (chat API, streaming path, sync path) pass nothing; behavior is unchanged.

```python
# services/message_service/__init__.py
async def get_chat_response_async(
    session: AsyncSession,
    message: Message,
    request_context: RequestContext,
    context_modifier: Callable[[RuntimeContext], None] | None = None,
    spec_modifier: Callable[[Spec], None] | None = None,
) -> list[Message]: ...
```

```python
# services/message_service/_implementation.py (async, pal-agents branch)
spec = await agent_service.construct_agent_spec(...)

if spec_modifier:
    spec_modifier(spec)

pal_agent = PalAgent(spec=spec)
```

### Default eval safety: `services/eval_service/_safety.py`

New module with `apply_eval_safety(spec: Spec) -> None` and `UnsafeEvalSpecError`. Current guarantees:

- **Toast** — forces `spec.toast.submit_orders = False` whenever `spec.toast.enabled`. No `POST /orders` can be issued from an eval run.
- **Adora** — forces `spec.adora.force_payment_link = True` whenever `spec.adora.enabled`. With `force_payment_link=True`, `AdoraV2Tool.fulfill_order` coerces the order's `payment_type` to `PAYMENT_LINK`; without a completed payment link the order does not reach the POS, so eval runs cannot place real Adora orders. See `tools/adora_v2_tool/_implementation.py` (`force_payment_link` branch in `fulfill_order`).

Any future provider with side-effecting behavior should extend this single choke point.

### `InProcessDriver` wiring

`InProcessDriver.__init__` now takes `spec_modifier: Callable[[Spec], None] | None`. If `None` (the default, and also what `None` is coerced to), it installs `apply_eval_safety`. `send_turn` forwards the stored modifier to `get_chat_response_async`. `_driver_factory.create_driver` accepts an optional `spec_modifier` passthrough for callers that need custom behavior; the factory default is the driver default.

### Scope decisions

Out of scope (deliberate):

- **Streaming path and sync `get_chat_response`.** Evals don't use them. Matches the earlier `context_modifier` scoping.
- **Voice eval runner (`_voice_eval_runner.py`).** Separate pipeline.
- **Changing `_build_toast_v3_spec` or any production code path.** The safety net lives in the eval layer; production `submit_orders` behavior is untouched.
- **Mocking pal-agents HTTP clients.** Works only for Toast, requires deep patching, doesn't generalize. `submit_orders` is the officially supported knob.

## Files changed

| File | Change |
|------|--------|
| `services/message_service/__init__.py` | Added `spec_modifier` kwarg on the async facade; import `Spec`; forward to `_implementation`. |
| `services/message_service/_implementation.py` | Added `spec_modifier` kwarg to async `get_chat_response_async`; applied after `construct_agent_spec`. |
| `services/eval_service/_safety.py` (new) | `apply_eval_safety` — forces Toast `submit_orders=False` and Adora `force_payment_link=True`. |
| `services/eval_service/_inprocess_driver.py` | New ctor arg `spec_modifier` defaulting to `apply_eval_safety`; forwarded to `get_chat_response_async`. |
| `services/eval_service/_driver_factory.py` | Optional `spec_modifier` passthrough. |
| `tests/services/eval_service/test_safety.py` (new) | Unit tests for the safety modifier. |
| `tests/services/eval_service/test_inprocess_driver.py` | Tests that default is `apply_eval_safety`, `None` falls back to it, custom modifier is stored and forwarded. |
| `tests/services/eval_service/test_driver_factory.py` | Tests for `spec_modifier` passthrough and default. |

## Verification

- `uv run pytest tests/services/eval_service/test_safety.py tests/services/eval_service/test_inprocess_driver.py tests/services/eval_service/test_driver_factory.py tests/services/message_service/` → 64 passed.
- `./scripts/validate.sh` → clean (black, ruff, isort, pyright 0 errors, import-linter 2/2 kept, toml-sort).

## Consequences

### Benefits

- Eval runs against any Toast- or Adora-enabled project are guaranteed safe regardless of the project's DB config (Toast `submit_orders`, Adora `force_payment_link`).
- Single choke point (`apply_eval_safety`) — future side-effecting flags only require editing one function.
- Zero production impact: the hook is default-`None` and unused on the chat API and streaming paths.

### Risks / limitations

- **A future spec field with side effects added without updating `apply_eval_safety`** would re-open the hole. Mitigated by colocating safety with eval tests, a module docstring enumerating covered flags, and the single-choke-point design.
- **Mutation ordering.** If future code between `construct_agent_spec` and `PalAgent(spec=spec)` reads the spec, it will observe the modifier's changes. This is intentional — the modifier is the last word on the spec before the engine runs.

## Follow-ups

1. **Audit other providers** (GenericAPI, MiniTable reservations, future integrations) for side-effecting operations and extend `apply_eval_safety` as they land.
2. Consider a pal-agents-level `Spec.dry_run: bool` umbrella flag so the safety modifier becomes a one-liner instead of per-provider edits.
