# Eval Platform Phase 2 — Audio-Native Evaluation Completion Record

**Date**: 2026-04-28
**Status**: Substantially implemented (3 small follow-ups tracked separately)
**Supersedes plan**: `docs/plans/conversation-eval/phase2-audio-native-proposal.md`
**Follow-ups**: `docs/plans/conversation-eval/phase2-followups-plan.md`

## Context

Phase 2 of the Voice AI Evaluation Platform added audio-native evaluation: LiveKit-event-driven turn/interruption/latency metrics, audio evaluators (E14–E18), and a synthetic caller that joins LiveKit rooms directly to drive multi-turn voice scenarios. See `docs/plans/conversation-eval/proposal.md` for the broader design context.

Because this work spanned two repos, this record lists what shipped in each.

## What shipped

### P2-A1 — Instrument pal-agents voice worker (`pal-livekit-agent-cloud`)

| Plan item | Shipped in |
|-----------|-----------|
| `CallMetricsReport` dataclass + `TurnLatency` + `InterruptionEvent` | `models/types.py` |
| `MetricsAccumulator` — subscribes to `MetricsCollectedEvent`, accumulates STT/LLM/TTS latencies and interruption events | `infra/metrics.py` |
| Event capture: `overlapping_speech`, `agent_speech_interrupted`, `agent_false_interruption`, `close` | `session/handlers.py` |
| End-call HTTP request to pal-mono includes metrics report | `session/handlers.py::send_session_end_report` |
| Shim re-export for backwards compatibility | `metrics_report.py` |

Landed across Notion tasks PAL-10200 / PAL-10201 / PAL-10202 (`c4cf646`, `53dc688`, `bb4c948`) during the April 2026 refactor that introduced the `models/` / `infra/` / `providers/` / `session/` layers.

### P2-A2 — Receive + store audio metrics (pal-mono)

| Plan item | Shipped in |
|-----------|-----------|
| `VoiceEndCallRequest.call_metrics` accepts the new payload | `api/routes/internal/_voice.py`, request tests in `tests/api/routes/internal/test_voice_end_call_metrics.py` |
| `ConversationEvaluationRequested` event carries audio metrics | `events/schema.py`, `tests/api/routes/internal/test_voice_end_call_event.py` |
| Persistence hooks for per-turn latencies and interruption events | `services/eval_service/_voice_result_collector.py` |

### P2-B1 — Audio evaluators (pal-mono)

| Evaluator | Source | Wired in `_evaluators.py`? |
|-----------|--------|----------------------------|
| E14 interruption | `services/eval_service/evaluators/interruption.py` | ✅ |
| E15 latency / silence | `services/eval_service/evaluators/latency_silence.py` | ✅ |
| E16 STT accuracy (WER, Whisper ground truth) | `services/eval_service/evaluators/stt_accuracy.py` | ✅ |
| E17 speech rate | `services/eval_service/evaluators/speech_rate.py` | ✅ |
| E17 audio quality (SNR, clipping, DC offset) | `services/eval_service/evaluators/audio_quality.py` | ❌ Module + tests exist, not imported by the runner — see follow-ups |
| E18 speech fidelity (LALM-as-Judge) | `services/eval_service/evaluators/speech_fidelity.py` | ✅ |

Both E14 and E15 derive directly from the instrumented `CallMetricsReport` (no audio processing) as designed.

### P2-C1 — Voice call simulation (pal-mono + pal-agents)

| Plan item | Shipped in |
|-----------|-----------|
| `SyntheticCaller` — joins LiveKit room, publishes TTS audio, receives agent audio, detects turn boundaries | `services/eval_service/_synthetic_caller.py` (delegates audio I/O to `pal_agents.evals.voice.*`) |
| `VoiceConversationRunner` / `run_voice_scenario` — multi-turn loop, scenario + persona + LLM-generated utterances | `services/eval_service/_voice_eval_runner.py` |
| Room orchestration (create room, dispatch production agent, connect caller, collect results) | `pal_agents.evals.voice.room_orchestrator.LiveKitRoomOrchestrator`, invoked from `_voice_eval_runner.py` |
| Result collection — transcript, tool calls, latencies, interruptions from the synthetic call | `services/eval_service/_voice_result_collector.py` |
| Persona and TTS voice-profile configuration | `pal_agents.evals.voice.personas`, `pal_agents.evals.voice.tts_engine` |
| Tests | `tests/services/eval_service/test_synthetic_caller.py`, `tests/services/eval_service/test_voice_eval_runner.py`, `tests/services/eval_service/test_interruption_evaluator.py`, `tests/services/eval_service/test_audio_quality_evaluator.py` |

## What did NOT ship (follow-ups)

Tracked separately in `docs/plans/conversation-eval/phase2-followups-plan.md`:

1. `audio_quality` evaluator wiring (~15 lines in `services/eval_service/_evaluators.py`).
2. `DUAL_CHANNEL_AGENT` stereo recording mode — not explicitly configured in `pal-livekit-agent-cloud/session/handlers.py`; recordings currently use whatever LiveKit defaults to.
3. `DirectDriver` — `services/eval_service/_driver_factory.py:58` still raises `NotImplementedError`. Orthogonal to Phase 2; explicitly deferred.

## Related records

- `docs/records/2026-04-28-eval-platform-phase1-completion.md` — Phase 1 task graduation
- `docs/records/2026-03-28-eval-platform-schema.md` — eval DB schema + Wave 3 runner
- `docs/records/2026-04-08-eval-ai-driven-turns.md` — user simulator for AI-driven turns
- `docs/records/2026-04-23-eval-scenarios-table.md` — scenarios DB migration

## Notes

- Full Phase 2 proposal text (including the EVA / Hamming / Coval comparison, SyntheticCaller turn-taking design, build-vs-buy assessment) is preserved in git history. The plan file is removed from `docs/plans/` now that Phase 2 has shipped.
- Fragile zones from this work: none specific to Phase 2, but note the existing rule from `docs/memory/short-term.md` that the `@observe` decorator structure in `agent/agent.py` must not be restructured.
