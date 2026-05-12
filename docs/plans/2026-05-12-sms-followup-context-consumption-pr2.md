# PR 2: Include SMS Followup Context In Existing Text Pipeline

## Goal

Keep the current pal-mono text sending pipeline intact, but enrich the SMS formatting LLM input when `pal-agents` returns an `sms_followup` event. The phone response should stay concise; the companion SMS should include the payment link and item recap when structured followup context is available.

## Current Behavior

`get_messages_from_agent_output(...)` converts agent output into outbound messages. For voice responses containing a URL, it currently creates:

- a generic voice message telling the caller to check SMS
- an SMS message using the raw `output.content`

This works only because Adora currently embeds the payment URL and item recap into `output.content`. Once PR 1 removes the recap from the phone output, pal-mono needs to use the new `sms_followup` event as extra context for SMS formatting.

Relevant files:

- `services/message_service/_utils.py`
- `services/message_service/_implementation.py`
- `tools/sms_tool/_llm.py`
- `tools/sms_tool/_implementation.py`

## Desired Behavior

Preserve the existing trigger and delivery mechanics:

- Continue detecting voice responses with links.
- Continue creating the companion SMS.
- Continue sending via the existing relay/message persistence path.
- Do not introduce a new delivery service.

Only add optional enrichment:

```python
sms_followup = find_sms_followup(output.events)
if sms_followup:
    formatter_input["sms_followup"] = sms_followup
```

The SMS formatter should treat `sms_followup` as authoritative when present.

## Implementation Steps

- [ ] Confirm event availability at the message-service boundary.

  Verify that pal-mono receives `pal_output.events` from `pal-agents` in non-streaming. For streaming, check whether collected chunk events are carried into the final message conversion path. If they are not, collect `sms_followup` events alongside `collected_events` and make them available where companion SMS messages are generated.

- [ ] Add a small event helper.

  In `services/message_service/_utils.py`, add a helper like:

  ```python
  def get_sms_followup_event(output: Any) -> dict[str, Any] | None:
      ...
  ```

  It should scan `output.events` for `event["type"] == "sms_followup"` and return the first valid event. Keep validation minimal and defensive.

- [ ] Preserve the existing voice URL branch.

  In `get_messages_from_agent_output(...)`, keep the same branch that creates the voice message and SMS message. Before building the SMS text, check for `sms_followup`.

- [ ] Feed SMS followup into the SMS formatting LLM.

  Add a formatter function that accepts the current SMS source text plus optional followup context. This can live beside the existing SMS LLM helper, but it should not replace unrelated `SMSTool.send_order_summary` behavior unless needed.

  Prompt rule:

  - If `sms_followup` is present, include the payment URL and item recap from it.
  - Keep the message concise and SMS-friendly.
  - Do not invent missing items, totals, links, or timing.
  - Preserve language from `sms_followup.language` when present.

- [ ] Add fallback behavior.

  If no `sms_followup` exists, keep current behavior exactly: SMS body comes from the existing `msg_text` path.

  If the SMS formatting LLM fails, fall back to a deterministic SMS body built from `sms_followup` fields. If that is not possible, fall back to current `msg_text`.

- [ ] Add tests.

  Cover:

  - Voice output with URL and no `sms_followup` behaves exactly as today.
  - Voice output with URL and `sms_followup` sends an SMS that includes the item recap.
  - LLM formatter failure falls back without blocking SMS delivery.
  - Phone response remains the generic voice message in the URL branch.

## Validation

Run targeted tests:

```bash
uv run pytest tests/services/message_service tests/tools/sms_tool
```

Run lint/format checks if files are changed:

```bash
uv run ruff check
uv run ruff format
```

## Risks

- Streaming may require a small plumbing change if chunk `events` are currently collected for observability but not passed to message conversion.
- Avoid making the SMS tool responsible for order placement semantics. It should only format and send provided context.
- The old URL-detection trigger is broad. This PR should not widen its behavior beyond optional `sms_followup` enrichment.
