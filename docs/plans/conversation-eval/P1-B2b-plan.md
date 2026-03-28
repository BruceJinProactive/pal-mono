# P1-B2b: Author 10+ generic eval scenarios

**Task:** https://www.notion.so/3318c0822e4981ffaa75d5db136f9970
**Type:** CODE
**Est. Hours:** 4
**Blocked by:** P1-B2a (needs schema to validate against)

---

## Background

Generic scenarios apply to every restaurant and cover universal agent behaviors: greetings, hours/address inquiries, allergy safety, escalation, adversarial inputs, topic switching, etc. FDEs later add restaurant-specific scenarios.

---

## Implementation Steps

- [ ] **Step 1: Create directory `services/eval_service/scenarios/generic/`**

- [ ] **Step 2: Write 10+ scenario YAML files**

  Each file covers one test category:
  1. `greeting.yaml` — agent greets, identifies restaurant, asks how to help
  2. `hours_inquiry.yaml` — customer asks about hours, agent responds with correct info
  3. `address_inquiry.yaml` — customer asks location/address
  4. `allergy_safety.yaml` — customer asks about allergens; agent must ground in menu data or defer
  5. `escalation.yaml` — customer requests human agent; proper handoff
  6. `adversarial.yaml` — prompt injection attempts, social engineering
  7. `topic_switch.yaml` — mid-conversation topic change; agent handles gracefully
  8. `off_topic.yaml` — unrelated questions (weather, politics); agent redirects
  9. `language_switch.yaml` — customer switches language mid-call
  10. `repeat_request.yaml` — customer asks agent to repeat; agent rephrases
  11. `order_cancellation.yaml` — customer wants to cancel/modify order

- [ ] **Step 3: Validate all scenarios**

  Run `validate_scenarios_from_yaml()` on each file to confirm they parse.

---

## Validation

```bash
uv run pytest tests/services/eval_service/ -v
./scripts/validate.sh
```

---

## Risks & Open Questions

- Scenarios should be generic enough to work for any restaurant — avoid restaurant-specific menu items or POS references
- expected_tool_calls may vary by restaurant setup — keep them optional in generic scenarios
