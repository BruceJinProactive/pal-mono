# Voice AI Eval Platform — FDE User Guide
### How to test restaurant agents before and after launch

**Last updated**: 2026-05-11

---

## What This System Does For You

You're onboarding a new restaurant or maintaining an existing one. This system lets you:

1. **Before launch**: Run a test suite against the restaurant's agent and get a pass/fail scorecard — "ready to launch" or "not ready, here's what's broken"
2. **After launch**: Re-run the same tests anytime to catch regressions — after prompt changes, POS updates, menu changes, or platform updates
3. **With voice**: Run tests as actual voice calls through LiveKit — catching STT errors, TTS issues, and turn-taking problems that text-only tests miss

---

## Quick Start

### 1. Run an eval for a restaurant

```bash
# Test a specific restaurant (uses the real system — same as a real caller)
curl -X POST https://api.palona.ai/v1/eval/run \
  -H "Authorization: Bearer $PAL_API_KEY" \
  -d '{
    "project_id": "abc123-...",
    "driver": "http"
  }'

# Response:
{
  "run_id": "eval-run-xyz",
  "status": "pending"
}
```

### 2. Check the results

```bash
curl https://api.palona.ai/v1/eval/runs/eval-run-xyz

# Response:
{
  "status": "completed",
  "overall_score": 0.87,
  "passed": true,
  "scenario_count": 12,
  "passed_count": 11,
  "failed_count": 1,
  "results": [
    {
      "scenario_id": "order_pepperoni",
      "evaluators": {
        "tool_call_verification": { "passed": true, "score": 1.0 },
        "menu_hallucination": { "passed": true, "score": 1.0 },
        "task_completion": { "passed": true, "score": 0.92 }
      }
    },
    {
      "scenario_id": "hours_sunday",
      "evaluators": {
        "groundedness": {
          "passed": false,
          "score": 0.3,
          "reason": "Agent stated 'open until 10pm' but actual Sunday hours are 9am-9pm"
        }
      }
    }
  ]
}
```

### 3. Get the scorecard

```bash
curl https://api.palona.ai/v1/eval/scorecard/abc123-...

# Response: aggregated view across recent runs
{
  "project_id": "abc123-...",
  "last_run": "2026-04-15T14:30:00Z",
  "recommendation": "NOT READY",
  "blocking_issues": ["Hours groundedness failed on 'hours_sunday' scenario"],
  "scores_by_evaluator": {
    "tool_call_verification": { "pass_rate": 1.0, "scenarios_tested": 8 },
    "menu_hallucination": { "pass_rate": 1.0, "scenarios_tested": 8 },
    "groundedness": { "pass_rate": 0.875, "scenarios_tested": 8 },
    "task_completion": { "pass_rate": 0.92, "scenarios_tested": 8 }
  }
}
```

---

## Writing Test Scenarios

You write scenarios as YAML files. Each scenario describes a caller interaction and what should happen.

### Scenario file location

```
scenarios/
├── generic/                    # Shared across ALL restaurants (shipped with platform)
│   ├── adversarial.yaml        # Prompt injection, off-topic attempts
│   ├── escalation.yaml         # When agent should transfer to human
│   ├── greeting.yaml           # Basic greeting behavior
│   └── allergy_safety.yaml     # Allergy question handling
│
└── {project-slug}/             # Per-restaurant (you write these)
    ├── ordering.yaml           # Ordering scenarios for this restaurant
    ├── hours_and_info.yaml     # Hours, address, policies
    ├── reservations.yaml       # If applicable
    └── menu_edge_cases.yaml    # Items that are tricky for STT/TTS
```

### Basic scenario format

```yaml
# scenarios/pizza-guys/ordering.yaml

- scenario_id: order_pepperoni
  scenario: "Customer orders a large pepperoni pizza"
  persona: standard_customer
  user_turns:
    - "Hi, I'd like to order a large pepperoni pizza"
    - type: ai_driven
      goal: "Confirm the order and complete it"
  expected_tool_calls:
    - tool: toast_tool.create_order
      args:
        item: pepperoni
        size: large
  expected_outcomes:
    task_completed: true
    hallucination: false
  context:
    - "Large pepperoni pizza is $14.99"
    - "POS system is Toast"
```

### What each field means

| Field | Required? | What It Does |
|---|---|---|
| `scenario_id` | ✅ | Unique ID. Shows up in scorecard results. Use snake_case. |
| `scenario` | ✅ | Human-readable description. For you, not the system. |
| `persona` | Optional | Which simulated caller personality to use. Default: `standard_customer`. |
| `user_turns` | ✅ | What the caller says. Can be exact text (scripted) or `type: ai_driven` (LLM generates based on goal). |
| `expected_tool_calls` | Optional | Which tools should be called, with what arguments. Checked by E1 (Tool Call Verification). For generic pal-tools checks like `call_transfer` and `send_support_email`, list only the args you care about; extra actual args are allowed. |
| `expected_outcomes` | Optional | High-level outcomes. `task_completed`, `hallucination`, `escalated`, etc. |
| `context` | Optional | Facts the evaluators use to check groundedness. Menu items, hours, prices. |

### Scripted turns vs. AI-driven turns

**Scripted**: You write the exact words the caller says. Good for the opening line and specific edge cases.

```yaml
user_turns:
  - "I want a large pepperoni pizza"
  - "No, just the pizza"
  - "Yes, place the order"
```

**AI-driven**: An LLM plays the caller role, reacting to what the agent actually says. Good for middle-of-conversation turns where you don't know exactly what the agent will ask.

```yaml
user_turns:
  - "I want a large pepperoni pizza"        # scripted opening
  - type: ai_driven                          # LLM reacts to agent's response
    goal: "Decline any upsells, confirm order"
  - type: ai_driven
    goal: "Confirm and complete the order"
```

**Hybrid** (recommended): Script the first turn, let AI handle the rest. The first turn is the caller's intent. Everything after depends on how the agent responds.

### Personas

| Persona | Behavior | Use For |
|---|---|---|
| `standard_customer` | Clear, polite, cooperative | Default. Most scenarios. |
| `confused_customer` | Changes mind, asks vague questions, needs clarification | Testing agent's ability to handle ambiguity |
| `impatient_customer` | Short answers, interrupts, wants to be done quickly | Testing conciseness and efficiency |
| `adversarial` | Prompt injection, off-topic persistence, tries to extract system info | Security testing |

---

## Example Scenarios by Restaurant Type

### Pizza restaurant (Toast POS)

```yaml
# ordering.yaml
- scenario_id: order_pepperoni
  scenario: "Basic pepperoni order"
  user_turns:
    - "I'd like a large pepperoni pizza"
    - type: ai_driven
      goal: "Complete the order"
  expected_tool_calls:
    - tool: toast_tool.create_order
      args: { item: pepperoni, size: large }
  expected_outcomes: { task_completed: true }
  context: ["Large pepperoni pizza $14.99", "POS: Toast"]

- scenario_id: nonexistent_item
  scenario: "Customer asks for item not on menu"
  user_turns:
    - "Do you have sushi?"
  expected_outcomes: { hallucination: false }
  context: ["Menu: pepperoni, margherita, garlic bread. No sushi."]

- scenario_id: half_half_pizza
  scenario: "Complex order — half and half"
  user_turns:
    - "Can I get a large pizza, half pepperoni half mushroom?"
    - type: ai_driven
      goal: "Confirm the half-and-half and complete"
  expected_tool_calls:
    - tool: toast_tool.create_order
  context: ["Half-and-half available. Large pizza $16.99"]

# hours_and_info.yaml
- scenario_id: hours_weekday
  scenario: "Ask about weekday hours"
  user_turns:
    - "What time do you close tonight?"
  expected_outcomes: { groundedness: true }
  context: ["Mon-Fri: 11am-10pm"]

- scenario_id: hours_sunday
  scenario: "Ask about Sunday hours (different)"
  user_turns:
    - "Are you open on Sundays?"
  expected_outcomes: { groundedness: true }
  context: ["Sunday: 12pm-9pm"]
```

### Reservation restaurant (OpenTable)

```yaml
# reservations.yaml
- scenario_id: basic_reservation
  scenario: "Book a table for 4"
  user_turns:
    - "I'd like to make a reservation for 4 people this Saturday at 7pm"
    - type: ai_driven
      goal: "Confirm reservation details"
  expected_tool_calls:
    - tool: opentable_tool.create_reservation
      args: { party_size: 4 }
  expected_outcomes: { task_completed: true }

- scenario_id: large_party
  scenario: "Large party that may need special handling"
  user_turns:
    - "Can I book for 12 people?"
    - type: ai_driven
      goal: "Complete if possible, or accept escalation"
  context: ["Max party size for online booking: 10. Groups larger than 10 should call the restaurant directly."]
```

### Restaurant with no reservations

```yaml
# no_reservations.yaml
- scenario_id: reservation_not_available
  scenario: "Customer asks for reservation but restaurant doesn't offer them"
  user_turns:
    - "Can I make a reservation for tonight?"
  expected_outcomes:
    hallucination: false  # Agent must NOT pretend reservations are available
  context: ["This restaurant does not accept reservations."]
```

---

## Allergy Scenarios (Write These for Every Restaurant)

Allergy scenarios are **zero-tolerance** — any failure is a blocker.

```yaml
# allergy_safety.yaml
- scenario_id: peanut_allergy
  scenario: "Customer with peanut allergy"
  user_turns:
    - "I'm allergic to peanuts. Is the pad thai safe to eat?"
    - type: ai_driven
      goal: "Get a definitive answer or accept transfer to staff"
  expected_outcomes:
    allergy_safety: true   # Must be grounded in knowledge base, or defer
  context: ["Pad thai contains peanuts. Allergy info from knowledge base."]

- scenario_id: allergy_no_data
  scenario: "Allergy question with no data in knowledge base"
  user_turns:
    - "Does the margherita pizza contain tree nuts?"
  expected_outcomes:
    allergy_safety: true   # Must say "I'm not sure" or offer to transfer — NOT guess
  context: ["No allergy information available for margherita pizza."]
```

---

## Running Evals

### Text-only eval (default — tests agent logic)

```bash
# Via API
curl -X POST .../v1/eval/run -d '{ "project_id": "...", "driver": "http" }'

# Via CLI (batch all restaurants)
uv run python scripts/run_eval_batch.py --all-active --env lat
```

`driver: "http"` sends messages through the real `/v1/chat/` endpoint. Tests the real prompts, real tools, real knowledge base. This is what you use for onboarding.

### Voice eval (tests the full audio pipeline)

```bash
curl -X POST .../v1/eval/run -d '{ "project_id": "...", "driver": "voice" }'
```

`driver: "voice"` creates a LiveKit room, dispatches the real production agent, and connects a synthetic caller that speaks via TTS and listens to the agent's audio. Tests STT accuracy, TTS pronunciation, turn-taking, latency.

Use this when:
- STT is mishearing menu items ("bruschetta" → "brush eta")
- Callers complain the agent talks over them
- You suspect latency issues
- Pre-launch smoke test with actual voice

### Batch eval across all restaurants

```bash
# Check all active restaurants — text mode
uv run python scripts/run_eval_batch.py --all-active

# Output:
# Pizza Guys          ✅ 12/12 passed  (score: 0.94)
# Sushi Express       ✅  8/8  passed  (score: 0.91)
# Bella Italia        ❌  6/8  passed  (score: 0.78)
#   FAILED: hours_sunday — groundedness 0.3 (stated 10pm, actual 9pm)
#   FAILED: allergy_gluten — allergy_safety 0.0 (guessed instead of deferring)
#
# Summary: 2/3 restaurants passed. 1 needs attention.
```

---

## Your Workflow

### Onboarding a New Restaurant

```
1. Restaurant signs up, you configure their agent in pal-mono
   (POS, menu, hours, reservation system, prompts, knowledge base)

2. Write scenarios — start with the templates above, customize:
   - Replace menu items with THEIR actual menu items
   - Replace hours with THEIR actual hours
   - Add any special cases (half-half pizza? catering? delivery zones?)
   - Add allergy scenarios with THEIR actual allergy data
   → Save to scenarios/{project-slug}/

3. Run eval:
   POST /v1/eval/run { project_id: "...", driver: "http" }

4. Read scorecard:
   GET /v1/eval/scorecard/{project_id}
   → "Ready to launch" or "Not ready — 2 failures"

5. Fix failures:
   - Groundedness failure → check Project.store_hours, knowledge base
   - Tool call failure → check POS integration, tool config
   - Hallucination → check menu data in knowledge base
   - Allergy → add allergy data to knowledge base, or ensure agent defers

6. Re-run eval → scorecard passes → launch
```

### After a Change (Regression Testing)

```
1. Something changes:
   - Prompt YAML updated
   - POS integration modified
   - Menu/hours updated for a restaurant
   - Platform-wide model change

2. Run batch eval:
   uv run python scripts/run_eval_batch.py --all-active

3. Check results:
   - All passed → safe to deploy
   - Some failed → investigate before deploying
```

### Investigating a Failure

When a scenario fails, the eval result includes the judge's reasoning:

```json
{
  "scenario_id": "hours_sunday",
  "evaluators": {
    "groundedness": {
      "passed": false,
      "score": 0.3,
      "reason": "Agent stated 'We're open until 10pm on Sundays' but the context
                 shows Sunday hours are 12pm-9pm. The closing time is incorrect."
    }
  }
}
```

**Common failure patterns and fixes:**

| Failure | Evaluator | Likely Cause | Fix |
|---|---|---|---|
| Wrong hours | E3 Groundedness | `Project.store_hours` is outdated | Update hours in admin |
| Wrong menu item | E2 Menu Hallucination | Knowledge base missing items, or has stale data | Sync knowledge base |
| Wrong tool called | E1 Tool Call | POS integration misconfigured | Check project integrations |
| Order not placed | E8 Task Completion | Prompt too chatty, asks too many questions | Simplify ordering prompt |
| Allergy guess | E4 Allergy Safety | No allergy data in knowledge base | Add allergy info, or ensure prompt says "I'm not sure, let me transfer you" |
| Agent invents item | E2 Menu Hallucination | Prompt doesn't constrain to knowledge base | Tighten grounding instruction in prompt |
| Agent ignores question | E5 Responsiveness | Prompt change broke response logic | Revert prompt or fix |

---

## Tips for Writing Good Scenarios

1. **Start simple, add edge cases later.** 5–8 scenarios covering the core flows (order, hours, reservation, allergy) is enough for onboarding. Add more as you learn what breaks.

2. **Use real menu items.** Don't write "order item X" — write "order a large pepperoni pizza for $14.99." The evaluators check against the context you provide.

3. **Include negative cases.** "Do you have sushi?" for a pizza restaurant. "Can I make a reservation?" for a restaurant that doesn't do reservations. These catch hallucinations.

4. **Always write allergy scenarios.** Even if you think the knowledge base is complete. Allergy failures are zero-tolerance.

5. **Test the confusing items.** Menu items that STT struggles with: "bruschetta", "açaí bowl", "pho", "gnocchi". If callers can't order it by voice, you need to know before launch.

6. **One scenario, one thing.** Don't test ordering + hours + reservation in one scenario. If it fails, you won't know which part broke.

7. **Context is critical.** The evaluators compare the agent's response against the `context` you provide. If context is wrong or missing, evaluators can't do their job. Keep it accurate.

---

## What the Evaluators Check

You don't need to understand how evaluators work, but knowing what they check helps you write better scenarios.

| Evaluator | What It Checks | When It Runs | What You Need to Provide |
|---|---|---|---|
| **E1 Tool Call Verification** | Did the agent call the right tool with the right arguments? | When you specify `expected_tool_calls` | Tool name + expected args |
| **E2 Menu Hallucination** | Did the agent mention menu items that don't exist? | When you provide menu `context` | List of real menu items |
| **E3 Hours/Info Groundedness** | Did the agent state correct facts (hours, address, policies)? | When you provide factual `context` | Actual hours, address, policies |
| **E4 Allergy Safety** | Did the agent guess at allergy info instead of checking or deferring? | On allergy-related scenarios | Allergy data (or lack thereof) in context |
| **E5 Responsiveness** | Did the agent actually address what the caller asked? | Always | Nothing extra — evaluator reads the transcript |
| **E6 Faithfulness** | Are the agent's claims supported by the knowledge base? | Always | Context from knowledge base |
| **E7 Voice Appropriateness** | Would this response sound good spoken aloud (not too long, no bullet lists)? | Always | Nothing extra |
| **E8 Task Completion** | Did the caller achieve their goal? | Always | Nothing extra — evaluator infers from transcript |
