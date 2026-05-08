# Voice AI Evaluation Platform — Requirements

### v1.0 | March 2026

> **This document is the starting point.** It defines *what* we need to achieve — metrics, targets, and acceptance criteria.
> The following documents are derived from these requirements:
> - **[Design Proposal](./proposal.md)** — explains the rationale and design approach to meet these requirements
> - **[Implementation Plan](./implementation-plan.md)** — breaks the proposal into tasks with file-level specs and critical path

---

## How to Read This Document

Each requirement has:
- **ID**: `L{layer}-R{number}` (layer = metrics framework layer from proposal)
- **Phase**: When it ships (1–5). Phase ordering: 1 On-Demand Testing, 2 Audio-Native Eval, 3 Production Scoring, 4 Monitoring + Feedback, 5 CI Gates + A/B Testing
- **Priority**: P0 (must have for phase), P1 (should have), P2 (nice to have)
- **Target**: Quantitative acceptance threshold
- **Verification**: How we prove the requirement is met
- **Plan reference**: Which implementation plan task covers it (or "Gap" if unaddressed)

---

## Layer 0: Agent Versioning & Traceability

*"Can we trace any call back to the exact agent configuration that handled it?"*

| ID | Requirement | Target | Phase | Priority | Verification | Plan Ref |
|---|---|---|---|---|---|---|
| L0-R01 | Every voice call records a deterministic agent fingerprint | 100% of calls have `agent_fingerprint` populated | 1 | P0 | Query Conversation table for null fingerprints — must be 0 | P1-B1 |
| L0-R02 | Same config always produces same fingerprint | Deterministic — identical inputs = identical hash | 1 | P0 | Unit test: build config twice with same inputs, assert fingerprints match | P1-B1 |
| L0-R03 | Any config change produces a different fingerprint | Changing any of: Prompt V2 text, model, tool config, feature flags, voice config changes the hash | 1 | P0 | Unit test: change each component independently, assert fingerprint changes | P1-B1 |
| L0-R04 | Ephemeral runtime context excluded from fingerprint | Current timestamp, runtime-injected additional_context do not affect hash | 1 | P0 | Unit test: same config at two different times produces same fingerprint | P1-B1 |
| L0-R05 | Canonical prompt text stored once per unique hash | Storage is per-unique-fingerprint, not per-call | 1 | P0 | After 1000 calls with same config: exactly 1 snapshot row | P1-C1, P1-E1 |
| L0-R06 | Full agent config snapshot recoverable by fingerprint | JSON snapshot of model, tools, knowledge settings, flags, Prompt V2 components | 1 | P0 | API: given fingerprint, return full config snapshot | P1-E1 |
| L0-R07 | Two config snapshots are diffable | Given two fingerprints, produce a human-readable diff of what changed | 1 | P1 | **Gap** — no diff endpoint or utility in plan | — |
| L0-R08 | `ConversationEvaluationRequested` includes fingerprints | Event carries `agent_fingerprint`, `prompt_fingerprint`, `model_identifier` | 1 | P0 | Integration test: fire event after call, assert fields present | P1-B1 |
| L0-R09 | Prompt V2 capability action edits are append-only | Editing a capability_action creates a new version, previous text preserved | 1 | P1 | **Gap** — proposal flags this as "most urgent sub-problem" but plan does not add version history to capability_actions | — |

---

## Layer 1: Voice Infrastructure

*"Can the system physically handle the call?"*

| ID | Requirement | Target | Phase | Priority | Verification | Plan Ref |
|---|---|---|---|---|---|---|
| L1-R01 | Call completion rate measured | > 90% | 1 | P0 | Datadog dashboard shows completion rate per project | **Gap** — data exists (LiveKit webhooks + conversation records) but no aggregation task |
| L1-R02 | Time to First Audio (TTFA) measured | P95 < 1.7s | 1 | P0 | Datadog metric: `voice.ttfa_ms` with P95 aggregation | **Gap** — needs span annotation in LiveKit agent worker |
| L1-R03 | Per-turn response latency measured | P95 < 3s | 1 | P1 | Datadog metric sliceable by project and agent_fingerprint | **Partial** — `turn_latencies_ms` exists in event but no evaluator consumes it |
| L1-R04 | Word Error Rate (WER) measured | < 8% overall | 2 | P0 | Second STT pass on S3 audio compared against live transcript | P2-B1 |
| L1-R05 | Menu item WER measured | < 5% on restaurant vocabulary | 2 | P0 | Domain-specific WER: extract menu mentions from transcript, compare against ground truth | P2-B1 |
| L1-R06 | Tool call latency measured | P95 < 2s | 1 | P1 | Datadog metric: `voice.tool_latency_ms` per tool type | **Gap** — APM spans exist but no aggregation task |
| L1-R07 | Audio signal-to-noise ratio measured | > 15 dB | 2 | P2 | Audio analysis on S3 recordings | P2-B1 |

---

## Layer 2: Execution (Correctness)

*"Does the agent do the right thing on the call?"*

### Evaluators

| ID | Requirement | Target | Phase | Priority | Verification | Plan Ref |
|---|---|---|---|---|---|---|
| L2-R01 | E1: Tool call verification | Tool invocation correctness > 95% | 1 | P0 | Deterministic: expected vs actual tool calls per scenario | P1-C2 |
| L2-R02 | E2: Menu hallucination detection | Hallucination rate < 2% | 1 | P0 | LLM judge: verify menu items mentioned exist in knowledge base | P1-C2 |
| L2-R03 | E3: Hours/info groundedness | Groundedness > 95% | 1 | P0 | Deterministic + LLM: compare stated facts against Project fields | P1-C2 |
| L2-R04 | E4: Allergy safety | 100% accuracy (zero tolerance) | 1 | P0 | LLM judge: verify allergy answers are grounded or agent defers | P1-C2 |
| L2-R05 | E5: Responsiveness | Score > 0.85 avg | 1 | P1 | LLM judge (GEval + rubrics) — already built in pal-agents | P1-C2 |
| L2-R06 | E6: Faithfulness | Score > 0.90 avg | 1 | P1 | LLM judge (claim-by-claim) — already built in pal-agents | P1-C2 |
| L2-R07 | E7: Voice appropriateness | Score > 0.80 avg | 1 | P1 | DAG metric + Python pre-filter — already built in pal-agents | P1-C2 |
| L2-R08 | E8: Task completion | > 80% of scenarios | 1 | P1 | LLM judge (ConversationalGEval) — already built in pal-agents | P1-C2 |
| L2-R09 | E9: Role adherence | Score > 0.90 avg | 1 | P1 | LLM judge (RoleAdherenceMetric) — already built in pal-agents | P1-C2 |
| L2-R10 | E10: Adversarial resistance | 100% refusal on injection scenarios | 4 | P0 | Scripted adversarial scenarios + deterministic pass/fail | **Gap** — no plan task |
| L2-R11 | E11: Escalation correctness | Correct escalation/non-escalation per scenario | 4 | P1 | Rule-based: detect escalation tool call vs scenario expectation | **Gap** — no plan task |
| L2-R12 | E12: Topic continuity | Context preserved after topic switch | 4 | P1 | LLM judge (multi-turn) | **Gap** — no plan task |
| L2-R13 | E13: Upsell compliance | > 85% compliance for accounts that require it | 4 | P1 | LLM judge or keyword detection, per-account configurable | **Gap** — no plan task |
| L2-R14 | Tool argument accuracy | > 90% | 1 | P0 | Subset of E1: verify args match expected values | P1-C2 |

### Scenario Infrastructure

| ID | Requirement | Target | Phase | Priority | Verification | Plan Ref |
|---|---|---|---|---|---|---|
| L2-R20 | FDE-authored YAML scenario format | FDEs can author scenarios without writing code | 1 | P0 | YAML schema documented, validated on load | P1-B2 |
| L2-R21 | Generic scenario library | >= 10 scenarios covering adversarial, escalation, greeting, allergy, topic switch | 1 | P0 | Count scenarios in `scenarios/generic/` | P1-B2 |
| L2-R22 | Per-restaurant scenario sets | FDE authors restaurant-specific scenarios during onboarding | 1 | P0 | `load_scenarios(project_id)` returns generic + per-restaurant | P1-B2 |
| L2-R23 | Hybrid replay: scripted waypoints + AI-driven fill-in | Scenarios support both scripted turns and AI-driven persona turns | 1 | P0 | Scenario YAML supports `type: ai_driven` turns | P1-B2 |
| L2-R24 | Caller personas | >= 3 personas: standard, confused, adversarial | 1 | P1 | Persona definitions loadable by scenario | P1-A1 |
| L2-R25 | Scenario flakiness detection | Scenarios where pass/fail flips across runs are auto-flagged | 1 | P2 | **Gap** — proposal mentions this but plan has no implementation |

---

## Layer 3: Call Experience

*"Does the call feel good?"*

| ID | Requirement | Target | Phase | Priority | Verification | Plan Ref |
|---|---|---|---|---|---|---|
| L3-R01 | Interruption handling scored | > 85% | 2 | P0 | Audio analysis: detect caller interruption + verify agent stopped | P2-B1 |
| L3-R02 | Barge-in collision rate measured | < 0.5/minute | 2 | P0 | Audio analysis: count simultaneous speech > 1s | P2-B1 |
| L3-R03 | Silence gaps detected | < 2 gaps > 3s per call | 2 | P0 | Audio analysis on S3 recordings | P2-B1 |
| L3-R04 | Speech tempo measured | 10–15 phonemes/second | 2 | P1 | Audio analysis | P2-B1 |
| L3-R05 | TTS pronunciation correctness | Menu items pronounced correctly | 3 | P1 | STT round-trip: TTS audio → STT → compare against intended text | **Gap** — not in any plan task |
| L3-R06 | Caller repetition rate | < 10% of calls | 1 | P1 | Transcript analysis: detect repeated caller utterances | **Gap** — no plan task, but transcript-only (shippable in Phase 1) |
| L3-R07 | Clarification loop detection | < 5% of calls stuck in loops | 1 | P1 | Transcript analysis: detect repeated agent clarification requests | **Gap** — no plan task, but transcript-only (shippable in Phase 1) |
| L3-R08 | Escalation rate within bounds | < 15% per account | 1 | P1 | Count escalation tool calls / total calls per account | **Gap** — data exists, needs aggregation |
| L3-R09 | Sentiment trajectory stable or positive | No declining sentiment mid-call | 1 | P2 | LLM judge or sentiment model on transcript segments | **Gap** — no plan task |
| L3-R10 | Operator feedback score | > 80% positive | 1 | P1 | Aggregate `feedback_service` thumbs up/down per agent | **Gap** — data exists in feedback_service, needs aggregation |

---

## Layer 4: Business Outcomes

*"Is the voice agent making the restaurant money?"*

| ID | Requirement | Target | Phase | Priority | Verification | Plan Ref |
|---|---|---|---|---|---|---|
| L4-R01 | Order conversion rate measured | > 70% for ordering calls | 3 | P1 | Calls with ordering intent that result in placed order (tool call) | **Gap** — no evaluator or metric |
| L4-R02 | Reservation conversion rate measured | > 65% for reservation calls | 3 | P1 | Calls with reservation intent that result in booking | **Gap** — no evaluator or metric |
| L4-R03 | Upsell compliance | > 85% for accounts that require it | 4 | P1 | See L2-R13 | **Gap** |
| L4-R04 | Containment rate | > 85% (calls resolved without human) | 3 | P1 | 1 - (escalation calls / total calls) per account | **Gap** — no metric |
| L4-R05 | Average handle time | < 3 min for standard orders | 3 | P2 | Call duration from conversation records | **Gap** — no metric |

---

## Platform Requirements

*Cross-cutting requirements for the eval platform itself.*

### On-Demand Testing (Mode 1)

| ID | Requirement | Target | Phase | Priority | Verification | Plan Ref |
|---|---|---|---|---|---|---|
| P-R01 | Trigger eval for a specific project via API | `POST /v1/eval/run` returns 202 + run_id | 1 | P0 | Integration test | P1-C3 |
| P-R02 | HTTPDriver: test through real system | Scenarios run through `/v1/chat/` with real prompts, real tools | 1 | P0 | Eval run with `driver=http` produces results | P1-A1, P1-C2 |
| P-R03 | DirectDriver: test agent in isolation | Scenarios run in-process with config snapshot + mock tools | 1 | P0 | Eval run with `driver=direct` produces results without pal-mono | P1-A1, P1-C2 |
| P-R04 | Scorecard output | Per-scenario pass/fail, overall score, failure reasons with judge reasoning | 1 | P0 | `GET /v1/eval/scorecard/{project_id}` returns structured results | P1-C3 |
| P-R05 | Suite speed (direct) | < 3 min per restaurant | 1 | P0 | Timed test run with 10 scenarios | P1-C2 |
| P-R06 | Suite speed (http) | < 5 min per restaurant | 1 | P0 | Timed test run with 10 scenarios | P1-C2 |
| P-R07 | Batch mode | One command tests all active projects | 1 | P0 | `scripts/run_eval_batch.py --all-active` | P1-F1 |
| P-R08 | Batch speed | 50 restaurants < 30 min (parallelized) | 1 | P1 | Timed batch run | P1-F1 |
| P-R09 | Onboarding go/no-go recommendation | Scorecard outputs "ready" or "not ready" with specific failure reasons | 1 | P0 | Scorecard includes recommendation field | **Gap** — plan has scorecard but no explicit go/no-go logic |
| P-R10 | Regression delta vs previous run | Show per-metric change from last run | 1 | P1 | `GET /v1/eval/scorecard` includes trend | P1-C2 |

### Production Scoring (Mode 2)

| ID | Requirement | Target | Phase | Priority | Verification | Plan Ref |
|---|---|---|---|---|---|---|
| P-R20 | Every voice call scored post-call | 100% of calls, within 60s of call end | 3 | P0 | Monitor: time between call end event and eval result write | P3-A1 |
| P-R21 | Zero impact on live calls | Fully async, never in call path | 3 | P0 | Architectural review — no sync calls from voice handler to eval | P3-A1 |
| P-R22 | Per-conversation scores API | Retrieve all metric scores for a specific call | 3 | P0 | `GET /v1/eval/conversation/{id}/scores` | P3-A2 |
| P-R23 | Datadog quality dashboard | Per-project, per-metric score trends, sliceable by agent_fingerprint | 3 | P0 | Dashboard exists with correct tags | P3-B1 |
| P-R24 | Operator feedback pipeline | Thumbs-down auto-creates review queue entry | 3 | P1 | **Gap** — not in plan |

### Monitoring & Feedback Loop (Mode 2.5)

| ID | Requirement | Target | Phase | Priority | Verification | Plan Ref |
|---|---|---|---|---|---|---|
| P-R30 | Anomaly alerting | Quality drop > 15% in 1hr vs 7-day baseline → Slack alert within 10 min | 4 | P0 | Trigger synthetic regression, verify alert fires | P4-A1 |
| P-R31 | Hallucination zero-tolerance alert | Any hallucination → immediate alert | 4 | P0 | Trigger hallucination, verify immediate alert | P4-A1 |
| P-R32 | Promote failed call to regression test | One API call creates scenario from production transcript | 4 | P0 | `POST /v1/eval/scenarios/promote` | P4-A2 |
| P-R33 | Weekly per-account quality reports | Scores by dimension, trend, top 3 failure patterns | 4 | P1 | **Gap** — not in plan |

### CI Quality Gate (Mode 3)

| ID | Requirement | Target | Phase | Priority | Verification | Plan Ref |
|---|---|---|---|---|---|---|
| P-R40 | PR gate on qualifying changes | PRs touching prompts/tools/agent logic trigger eval | 5 | P0 | GitHub Actions workflow triggers on correct paths | P5-A1 |
| P-R41 | Merge blocked on regression | Regression > 5% on any scenario → merge blocked | 5 | P0 | PR with intentional regression is blocked | P5-A1 |
| P-R42 | PR comment with score deltas | Per-project, per-scenario delta posted within 10 min | 5 | P0 | PR comment rendered correctly | P5-A1 |
| P-R43 | Prompt A/B testing | Route X% of calls to variant, track quality per variant, statistical significance | 5 | P1 | **Gap** — in proposal but not in plan |

---

## Gap Summary

Requirements not yet covered in the implementation plan:

| Category | Gap | Impact | Recommendation |
|---|---|---|---|
| **Voice infra metrics (Phase 1)** | L1-R01, R02, R03, R06 — call completion, TTFA, turn latency, tool latency have no aggregation task | Data already exists but isn't surfaced | Add Datadog metric aggregation tasks to Phase 1 |
| **Capability action versioning** | L0-R09 — mutable overrides destroy history | Proposal calls this "the most urgent sub-problem" | Add append-only version history task to Phase 1 |
| **Config diff utility** | L0-R07 — no way to diff two fingerprints | Fingerprints answer "did it change?" but not "what changed?" | Add diff endpoint to Phase 1 Wave 1C |
| **Transcript-based call experience** | L3-R06, R07, R08, R10 — repetition, clarification loops, escalation rate, operator feedback | Detectable from transcripts/existing data today, no audio needed | Add as Phase 1 evaluators |
| **TTS pronunciation** | L3-R05 — not in any plan task | Mispronounced menu items degrade caller experience | Add STT round-trip evaluator to Phase 3 (depends on audio pipeline) |
| **Sentiment trajectory** | L3-R09 — no plan task | Declining sentiment indicates conversation going off rails | Add to Phase 1 (transcript-only) |
| **Business outcome metrics** | L4-R01 through L4-R05 — none implemented | Cannot measure whether agents make restaurants money | Add conversion/containment metrics to Phase 3 Datadog work |
| **Operator feedback pipeline** | P-R24 — feedback_service data unused | Proposal says "data sits unused — needs aggregation" | Add to Phase 3 |
| **Weekly reports** | P-R33 — not in plan | No regular quality visibility for stakeholders | Add to Phase 4 |
| **Go/no-go logic** | P-R09 — scorecard has no explicit recommendation | FDE still has to interpret raw scores | Add threshold-based recommendation to scorecard in Phase 1 |
| **A/B testing** | P-R43 — in proposal but not in plan | Cannot compare prompt variants with statistical rigor | Add to Phase 5 |
| **Flakiness detection** | L2-R25 — scenarios that flip pass/fail | Flaky tests erode trust in the eval system | Add flaky detection to Phase 1 runner |

---

## Changelog

| Date | Change | Author |
|---|---|---|
| 2026-03-26 | Initial requirements extracted from proposal v1.0, cross-referenced against implementation plan | — |
| 2026-03-26 | Aligned phase numbering to canonical ordering: 1 On-Demand, 2 Audio, 3 Production, 4 Monitoring, 5 CI. Updated Plan Refs to match renumbered implementation plan tasks. | — |
