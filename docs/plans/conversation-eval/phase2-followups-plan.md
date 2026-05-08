# Eval Platform Phase 2 — Follow-ups

**Status**: Open
**Created**: 2026-04-28
**Parent record**: `docs/records/2026-04-28-eval-platform-phase2-completion.md`

Three small gaps remaining after Phase 2 (audio-native evaluation) otherwise shipped. Tracked here so they don't get lost; each is independently shippable.

---

## 1. Wire the `audio_quality` evaluator into the runner

**Where**: `services/eval_service/_evaluators.py`
**Module already exists**: `services/eval_service/evaluators/audio_quality.py`
**Tests already exist**: `tests/services/eval_service/test_audio_quality_evaluator.py`
**Effort**: ~15 minutes

The E17 audio-quality evaluator (SNR, clipping, DC offset, via `librosa`) was built but never imported by the voice evaluator pipeline. Every other voice evaluator is imported and wrapped in a `_run_*_evaluator` block in `_evaluators.py`; `audio_quality` is not.

### What to do

1. Add the import alongside the other voice evaluator imports:

   ```python
   from services.eval_service.evaluators.audio_quality import evaluate_audio_quality
   ```

2. Inside the `if record.is_voice:` branch, add a task that passes the raw audio bytes (same input the evaluator's tests use — `bytes` containing a WAV payload). Pattern matches the existing `speech_fidelity` block:

   ```python
   _run_sync_evaluator(
       evaluate_audio_quality,
       record.voice_audio_wav,   # or whichever field holds the raw bytes
       name="audio_quality",
   )
   ```

3. Confirm the returned `EvalResult` has `metric_name="audio_quality"` (the existing test at `tests/services/eval_service/test_audio_quality_evaluator.py:214` verifies this).

### Acceptance

- Voice eval runs produce an `audio_quality` row in `eval_results` alongside the other audio metrics.
- Scorecard aggregation (`get_scorecard` in `_runner.py`) picks up the new metric automatically — no changes needed there.

---

## 2. Confirm / enable `DUAL_CHANNEL_AGENT` stereo recording

**Where**: `pal-livekit-agent-cloud/session/handlers.py` (and wherever the `AgentSession` / recording is configured)
**Effort**: 0.5–1 day (depends on what hook LiveKit exposes currently)

The Phase 2 proposal called for switching the recording mode to `DUAL_CHANNEL_AGENT` (agent → left channel, caller → right channel) so audio evaluators that need speaker separation (E16 STT accuracy against the caller channel, E17 speech rate on the agent channel, E18 speech fidelity) can operate on clean single-speaker streams without diarization.

Currently in `session/handlers.py` the recording path is pulled via `getattr(report, "audio_recording_path", None)` — we take whatever LiveKit produces by default. No explicit `DUAL_CHANNEL_AGENT` configuration was found in the repo.

### What to check first

- Is LiveKit actually defaulting to dual-channel for our sessions? Inspect one recording from S3 with `ffprobe` — if it's stereo with speaker-separated channels already, nothing to do.
- If mono/mixed, decide between:
  - **Egress API** `EncodingOptions` with `DUAL_CHANNEL_AGENT` audio mix — configured at egress start time.
  - **`RecorderIO`** — LiveKit's SDK-level recorder; captures stereo inside the agent process.

### Tradeoffs

- Egress-based recording is the current path (external, uploaded to S3 by LiveKit). Cleanest to stay there.
- Whichever path we pick, downstream consumers (human review, compliance, transcript generation) need to handle stereo. Check that nobody assumes mono before flipping this.

### Acceptance

- New voice calls produce stereo OGG/WAV with agent on L and caller on R.
- STT-accuracy evaluator (E16) runs Whisper on the caller channel only; WER numbers stabilize (should improve vs. mixed-channel WER).
- No regression for existing downstream consumers.

---

## 3. `DirectDriver` — wrap LiveKit's native `AgentSession.run()` + `mock_tools()`

**Where**: `services/eval_service/_driver_factory.py:58` currently raises `NotImplementedError`.
**Effort**: ~1–2 days
**Priority**: Low (orthogonal to Phase 2 — this was deferred in the original plan, not regressed)

A fourth driver mode that runs scenarios against the production agent *spec* in-process using LiveKit's built-in testing harness (`AgentSession.run()`, `mock_tools()`, `session.judge()`). Gives the fastest possible test loop — no message_service, no streaming, no LiveKit room, no synthetic caller. Good for unit-style smoke tests on agent reasoning.

### What's needed

- Construct an `AgentSpec` from a `RawConfig` without going through `message_service`. `build_with_fingerprint()` already produces `AgentConfig` — DirectDriver needs the Spec.
- Implement the `AgentDriver` protocol over `AgentSession.run(...)`, mapping scenario turns to `session.run(user_input=...)` calls and collecting tool-call records + judge output.
- Expose `driver_mode="direct"` in `_driver_factory.py` and wire through the runner.

### Acceptance

- `POST /v1/eval/run { driver: "direct" }` runs scenarios against the agent spec directly, writes results to `eval_results`, and populates `tool_call_records`.
- Latency per scenario is noticeably lower than `InProcessDriver` (no DB session, no streaming overhead).

---

## Notes

- Items 1 and 2 are genuine Phase 2 gaps and should ship before Phase 2 is declared fully done.
- Item 3 is a Phase 1/2 backlog item (it appears in the Phase 2 proposal only as a reference comparison). Defer unless we hit a use case where `InProcessDriver` is too slow.
