# Phase 2: Audio-Native Evaluation — Implementation Proposal
### Addendum to Voice AI Evaluation Platform | March 2026

---

## The Surprise: We Don't Need to Solve Most of This

Our initial assumption was that audio evaluation requires downloading recordings from S3, running speaker diarization, training overlap detectors, and doing heavy signal processing. It doesn't. LiveKit already provides most of the data during the call — we're just not capturing it.

### What LiveKit Already Gives Us (That We're Not Using)

| LiveKit Capability | What It Provides | Currently Captured? |
|---|---|---|
| **`DUAL_CHANNEL_AGENT` recording mode** | Stereo OGG: agent audio → left channel, caller audio → right channel. No diarization needed. | ❌ We use default mixed mono. |
| **`overlapping_speech` event** | Fires with `is_interruption: bool` + `detected_at` timestamp when caller and agent speak simultaneously | ❌ Event fires in pal-agents worker but isn't sent to pal-mono |
| **`user_state_changed` event** | Caller state transitions: speaking → listening → away, with timestamps | ❌ Not captured |
| **`agent_state_changed` event** | Agent state transitions: listening → thinking → speaking, with timestamps | ❌ Not captured |
| **`RecorderIO`** | Built-in stereo recorder: user input → left channel, agent output → right channel. OGG Opus, 48kHz. | ❌ Not used — recording is done separately |
| **VAD metrics** (`VADMetrics`) | Idle time, per-frame speech probability | ❌ Not captured |
| **STT metrics** (`STTMetrics`) | Audio duration per STT inference | ❌ Not captured |
| **EOU metrics** (`EOUMetrics`) | End-of-utterance delay, last speaking timestamp | ❌ Not captured |
| **`MetricsCollectedEvent`** | Unified event for all pipeline metrics | ❌ Not subscribed to |

**The gap is not signal processing — it's instrumentation.** The pal-agents voice worker runs in a LiveKit session that fires all these events. We just need to:
1. Subscribe to them during the call
2. Accumulate them into a structured metrics report
3. Send the report back with the end-call request
4. Switch to dual-channel recording

---

## Two-Track Approach

### Track A: Instrument the Live Pipeline (Primary — Accurate, Real-Time Data)

Modify the pal-agents voice worker to capture LiveKit events during the call and send them to pal-mono. This gives us precise, timestamped data for every call going forward.

**Changes in pal-agents**:
- Subscribe to `overlapping_speech`, `user_state_changed`, `agent_state_changed`, `metrics_collected` events
- Accumulate per-turn metrics: turn start/end timestamps, response latency (user stops → agent starts), interruption events
- Switch to `DUAL_CHANNEL_AGENT` or `RecorderIO` for stereo recording
- Include the accumulated metrics report in the end-call HTTP request to pal-mono

**Changes in pal-mono**:
- Extend `VoiceEndCallRequest` to accept the new metrics payload
- Store metrics on the `PhoneCall` record or in a new `call_metrics` table
- Include metrics in `ConversationEvaluationRequested` event

### Track B: Post-Hoc Analysis of Recordings (Fallback — For Historical Data)

For calls already in S3 (or when live instrumentation isn't available), analyze the audio recording after the fact using open-source tools.

**Processing pipeline**:
```
S3 OGG download
  → FFmpeg decode to 16kHz mono WAV (or split stereo if dual-channel)
  → Silero VAD: speech/silence timestamps
  → Overlap detection: energy analysis on split channels (or pyannote if mono)
  → Silence gap computation: gaps between speech segments
  → librosa: SNR, clipping, DC offset
  → whisper-timestamped: speech rate (words-per-minute per turn)
  → jiwer: WER comparison (production STT vs. Whisper ground truth)
```

**Track B is the fallback, not the primary path.** It's less accurate (diarization on mixed audio has ~10-15% error rate) and much slower (60-90s per call on CPU). Track A gives us timestamped ground truth for free.

---

## What We Measure (Audio Evaluators E14–E17, Expanded)

Based on research from EVA framework (ServiceNow, March 2026), Full-Duplex-Bench, and τ-Voice:

### E14: Interruption Handling

| Sub-Metric | Source | Target | How |
|---|---|---|---|
| **Interruption detection rate** | Track A: `overlapping_speech.is_interruption` events | > 95% detected | Count events |
| **Stop latency** | Track A: `agent_state_changed` from speaking → listening after interruption | < 500ms | Timestamp diff |
| **Recovery quality** | LLM judge on transcript: did agent acknowledge interruption and respond? | > 85% appropriate | E5 Responsiveness on post-interruption turns |
| **False positive rate** | Track A: `overlapping_speech` events where `is_interruption=false` | < 10% | Background noise, coughs shouldn't trigger stops |
| **Barge-in selectivity** | Does agent ignore "uh-huh" backchannels vs. respond to real interruptions? | > 80% correct | Classify overlap events by context |

### E15: Silence & Latency

| Sub-Metric | Source | Target | How |
|---|---|---|---|
| **Response latency P50/P95** | Track A: `user_state_changed(speaking→listening)` → `agent_state_changed(listening→speaking)` | P50 < 1.0s, P95 < 2.0s | Timestamp diff per turn |
| **TTFA (Time to First Audio)** | Track A: call connect → first agent audio | < 2.0s | First `agent_state_changed(→speaking)` |
| **Silence gaps > 3s** | Track A: state change timestamps, or Track B: Silero VAD | < 2 per call | Count gaps where neither party speaks |
| **Thinking time** | Track A: `agent_state_changed(listening→thinking)` duration | < 3s for simple queries | Duration of thinking state |
| **EOU delay** | Track A: `EOUMetrics.end_of_utterance_delay` | < 800ms | Direct from LiveKit metrics |

### E16: STT Accuracy

| Sub-Metric | Source | Target | How |
|---|---|---|---|
| **Overall WER** | Track B: Whisper large-v3 vs. production Deepgram transcript | < 8% | jiwer on full transcript |
| **Menu item WER** | Track B: Compare menu item mentions specifically | < 5% | Extract named entities, compute WER on those only |
| **Named entity fidelity** | Track B: Order numbers, phone numbers, addresses | 100% critical entities | Exact match on critical entities |

### E17: Voice Quality

| Sub-Metric | Source | Target | How |
|---|---|---|---|
| **Speech rate** | Track B: whisper-timestamped word-per-minute per turn | 120–180 WPM | Flag turns outside range |
| **SNR** | Track B: librosa energy analysis | > 15 dB | Signal vs. noise floor estimation |
| **Clipping** | Track B: amplitude analysis | < 0.1% samples | Count samples at max amplitude |
| **TTS naturalness** | Track B or LALM: UTMOSv2 or GPT-4o audio | MOS > 3.5 | Automated MOS prediction |

### E18: Conversation Flow (NEW — from EVA research)

| Sub-Metric | Source | Target | How |
|---|---|---|---|
| **Speech fidelity** | LALM-as-Judge on audio: Did TTS correctly speak order confirmation, prices, phone numbers? | 100% for order details | GPT-4o or Gemini audio input — compare spoken words vs. intended text |
| **Conciseness** | LLM judge: Is agent response length appropriate for voice? | < 30 words per turn average | Same as E7 Voice Appropriate |
| **Disfluency naturalness** | Track B: filled pause rate, repetition rate | Natural range (not zero, not excessive) | Lexical analysis + prosodic features |

---

## Implementation Plan

### P2-A1: Instrument pal-agents voice worker (pal-agents)
**Effort**: 3 days
**This is the highest-leverage task in the entire eval platform.**

**What changes**:
- Subscribe to LiveKit session events: `overlapping_speech`, `user_state_changed`, `agent_state_changed`, `metrics_collected`
- Accumulate events into a `CallMetricsReport` dataclass during the call:
  ```python
  @dataclass
  class CallMetricsReport:
      turn_events: list[TurnEvent]      # user/agent state transitions with timestamps
      interruptions: list[Interruption]  # overlapping_speech events
      vad_metrics: list[VADMetric]       # per-inference VAD stats
      stt_metrics: list[STTMetric]       # per-inference STT stats
      eou_metrics: list[EOUMetric]       # end-of-utterance delays
      turn_latencies_ms: list[float]     # computed: user_stop → agent_start per turn
  ```
- Switch recording to `DUAL_CHANNEL_AGENT` mode (or use `RecorderIO`) for stereo output
- Include `CallMetricsReport` as JSON in the end-call HTTP request to pal-mono

**Acceptance criteria**:
- Every voice call now produces a `CallMetricsReport` with per-turn timestamps
- Audio recording is stereo OGG (agent L, caller R)
- `turn_latencies_ms` is populated (no longer `[]`)
- Per-turn `start_time` and `end_time` in transcript are populated (no longer `0.0`)
- Interruption events captured with `is_interruption` flag and `detected_at` timestamp

### P2-A2: Extend pal-mono to receive and store audio metrics (pal-mono)
**Effort**: 1.5 days

**What changes**:
- Extend `VoiceEndCallRequest` schema with `call_metrics: CallMetricsReport | None`
- Store metrics: either extend `PhoneCall` table (populate the existing `turn_latency_avg`, `model_latency_avg`, etc. columns) or create `call_audio_metrics` table for full detail
- Extend `ConversationEvaluationRequested` event with:
  - `turn_latencies_ms` (now populated from `CallMetricsReport`)
  - `interruption_count` and `interruption_events`
  - `recording_format: "stereo_ogg"` (so evaluators know they have dual-channel)
  - Per-turn `start_time` and `end_time` (now populated)

**Acceptance criteria**:
- `ConversationEvaluationRequested` event includes real turn latencies and interruption data
- `PhoneCall` table columns for latency metrics are populated
- Transcript entries have real timestamps

### P2-B1: Build audio evaluators (pal-agents + pal-mono)
**Effort**: 3 days

**What to build — in priority order**:

| Priority | Evaluator | Approach | Effort |
|---|---|---|---|
| 1st | **E15 Response latency** | Direct from `turn_latencies_ms` in event — pure arithmetic, no audio processing | 0.25d |
| 2nd | **E14 Interruption handling** | Direct from `interruption_events` in event — count + stop latency from timestamps | 0.25d |
| 3rd | **E15 Silence gaps** | From turn timestamps — find gaps where neither party is in "speaking" state | 0.25d |
| 4th | **E16 STT accuracy (WER)** | Download audio from S3, split stereo channels, run Whisper on caller channel, compute WER vs. Deepgram transcript | 1d |
| 5th | **E17 Speech rate** | whisper-timestamped on agent channel → words-per-minute per turn | 0.5d |
| 6th | **E17 SNR/audio quality** | librosa on full recording — SNR estimation, clipping detection | 0.25d |
| 7th | **E18 Speech fidelity** | LALM-as-Judge (GPT-4o audio mode): send agent audio channel + intended confirmation text, ask "did the TTS correctly speak this?" | 0.5d |

**Key insight**: E14, E15 (interruptions, latency, silence) come from the instrumented event data — NO audio processing needed. These are free once P2-A1 ships. E16 and E17 need actual audio analysis on the S3 recording.

### P2-C1: Voice Call Simulation — Full Proposal

**Effort**: 5 days (revised from 2 — the original was underspecified)

This is the hardest piece in the entire eval platform. A synthetic caller that joins a LiveKit room, speaks via TTS, listens to the agent's audio, detects turn boundaries, and drives a multi-turn conversation — just like a real phone call, but programmatic.

#### What Exists Today (From Research)

| Source | What It Does | Usable? |
|---|---|---|
| **LiveKit Agents SDK `session.run()`** | Text-mode testing: inject text, get text response, assert with LLM judge + tool call checks. Built-in `mock_tools()`. | ✅ This IS our DirectDriver. Already built into LiveKit. |
| **LiveKit `livekit-rtc` Python SDK** | Raw audio I/O: `AudioSource.capture_frame()` to publish, `AudioStream.from_participant()` to receive. | ✅ The building blocks for our VoiceDriver. |
| **LiveKit `lk.agent.state` attribute** | The Agents framework publishes agent state (`listening`, `thinking`, `speaking`) as participant attributes. Other participants can watch for changes. | ✅ Key turn-taking signal. |
| **EVA (ServiceNow)** | Bot-to-bot audio via WebSocket. ElevenLabs as synthetic caller, Pipecat as agent. `BotToBotAudioInterface` with 600ms silence detection. MIT licensed. | ⚠️ Uses WebSocket/Pipecat, not LiveKit. Architecture pattern is the reference — not the code. |
| **voicetest** | CLI tool that imports LiveKit agents and runs LLM-driven simulations. Docker-based with local LiveKit + Whisper + Kokoro TTS. | ⚠️ Early stage (v0.34). Worth watching. |
| **Hamming / Coval** | Both offer room-level (LiveKit direct) AND SIP-level (PSTN) call simulation. | 💰 $1-3K/mo. The room-level approach is what we'd build ourselves. |
| **LiveKit `create_sip_participant`** | Places real outbound SIP calls. Used by LiveKit's own outbound calling example. | ✅ For SIP-level testing (Approach B). |

#### Two Approaches to Simulating Calls

##### Approach A: Room-Level Simulation (Primary — build this first)

The synthetic caller joins the LiveKit room directly as a WebRTC participant. No SIP, no phone numbers, no telephony costs. The production agent sees it as a regular caller.

```
┌─────────────────────────────────────────────────────────┐
│  LiveKit Room "eval-{project_id}-{run_id}"              │
│                                                         │
│  ┌─────────────────────┐    ┌──────────────────────┐   │
│  │  Synthetic Caller    │    │  Production Agent    │   │
│  │  (livekit-rtc)       │◄──►│  (pal-livekit-agent) │   │
│  │                      │    │                      │   │
│  │  agent=False in token│    │  Dispatched via      │   │
│  │  (appears as human)  │    │  AgentDispatch API   │   │
│  │                      │    │                      │   │
│  │  Publish: TTS audio  │    │  Subscribes to       │   │
│  │  via AudioSource     │    │  caller's mic track  │   │
│  │                      │    │                      │   │
│  │  Receive: agent audio│    │  Publishes agent     │   │
│  │  via AudioStream     │    │  audio track         │   │
│  └─────────────────────┘    └──────────────────────┘   │
│                                                         │
│  Recording: DUAL_CHANNEL_AGENT (agent L, caller R)      │
└─────────────────────────────────────────────────────────┘
```

**What this tests**: The entire voice pipeline — STT (does Deepgram hear "pepperoni" correctly?), LLM (does the agent call the right tool?), TTS (does Cartesia pronounce the confirmation correctly?), VAD (does Silero detect the end of the caller's sentence?), turn-taking (does the agent respond at the right time?), interruption handling.

**What this does NOT test**: SIP signaling, codec transcoding (G.711 vs Opus), PSTN network conditions (jitter, packet loss), phone number routing.

**Cost**: $0 per call (just LiveKit room infrastructure).
**Speed**: Real-time (3-minute scenario takes ~3 minutes).
**Scale**: 100+ concurrent rooms (limited only by agent worker capacity).

##### Approach B: SIP-Level Simulation (Secondary — add later)

Place a real phone call via LiveKit's `create_sip_participant` API. Tests the full telephony path including SIP trunk, codec negotiation, and PSTN conditions.

```
┌──────────────────────────────────────────────────────────┐
│  LiveKit Room                                             │
│                                                           │
│  ┌──────────────┐   SIP/RTP   ┌──────────────────────┐  │
│  │  Synthetic    │◄───────────►│  SIP Trunk (Twilio)  │  │
│  │  Caller       │             │  ↕ PSTN              │  │
│  │  (agent in    │             │  ↕ Your phone number │  │
│  │   same room)  │             │  ↕ SIP Bridge        │  │
│  └──────────────┘             │  ↕ Production Agent  │  │
│                                └──────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**Cost**: ~$0.01-0.02/min per call.
**When to use**: Pre-launch smoke test for a new restaurant. Verifies the phone number → SIP trunk → LiveKit room → agent path works end-to-end. Run a handful of calls, not hundreds.

#### The Synthetic Caller Pipeline

The core loop is the same regardless of approach (room-level or SIP):

```
┌──────────────────────────────────────────────────────────┐
│  Scenario: "Order a large pepperoni pizza"                │
│  Persona: standard_customer                               │
│                                                           │
│  Turn 1:                                                  │
│    Scenario text: "Hi, I'd like a large pepperoni pizza"  │
│         │                                                 │
│         ▼                                                 │
│    TTS (Cartesia/ElevenLabs): text → audio frames         │
│         │                                                 │
│         ▼                                                 │
│    AudioSource.capture_frame() → pushes into room         │
│                                                           │
│    ... agent processes audio, responds ...                │
│                                                           │
│    AudioStream receives agent audio frames                │
│         │                                                 │
│         ├──→ Detect turn end:                             │
│         │      Option 1: lk.agent.state → "listening"     │
│         │      Option 2: Silero VAD end-of-speech         │
│         │      Option 3: active_speakers_changed          │
│         │                                                 │
│         ├──→ Run STT on agent audio → agent transcript    │
│         │                                                 │
│         └──→ Capture latency: caller_end → agent_start    │
│                                                           │
│  Turn 2:                                                  │
│    Feed agent transcript + scenario goal to LLM persona   │
│    LLM generates next caller utterance                    │
│         │                                                 │
│         ▼                                                 │
│    TTS → audio → room → agent → audio → STT → evaluate   │
│                                                           │
│  ... repeat until scenario goal achieved or turn limit ...│
│                                                           │
│  End:                                                     │
│    Collect all TurnResults (transcript, tool_calls,       │
│    latencies, interruptions, audio quality metrics)       │
│    Run evaluators E1–E18                                  │
└──────────────────────────────────────────────────────────┘
```

#### Turn-Taking: How the Caller Knows When to Speak

This is the critical design problem. Three signals are available, ranked by reliability:

| Signal | Source | Latency | Reliability | How |
|---|---|---|---|---|
| **`lk.agent.state` attribute** | LiveKit Agents framework publishes agent state as participant attributes | ~100ms | ✅ Best | `room.on("participant_attributes_changed")` → check `lk.agent.state == "listening"` |
| **Silero VAD on agent audio** | Run VAD on received `AudioStream` frames | ~200-500ms | ✅ Good | End-of-speech detection on the agent's audio track. EVA uses 600ms silence threshold. |
| **`active_speakers_changed`** | LiveKit SFU detects audio level changes | ~200-500ms | ⚠️ Ok | Can be noisy — brief mid-sentence pauses trigger false positives |

**Recommendation**: Use `lk.agent.state` as the primary signal (it's the most reliable — the agent explicitly declares its state). Use Silero VAD as a fallback/confirmation (in case the state attribute is delayed or missing).

#### What Needs to Be Built

| Component | Description | Repo | Effort |
|---|---|---|---|
| **SyntheticCaller class** | Joins LiveKit room, publishes TTS audio, receives agent audio, detects turns, drives multi-turn conversation | pal-agents `evals/drivers/voice.py` | 2d |
| **VoiceConversationRunner** | Wraps SyntheticCaller with scenario/persona logic. LLM generates next caller utterance from transcript + goal. | pal-agents `evals/conversation/voice_runner.py` | 1d |
| **Room orchestration** | Create room, dispatch production agent, connect synthetic caller, start recording, run conversation, collect results | pal-mono `eval_service` | 1d |
| **Noise injection** | Mix background noise (restaurant, street) into synthetic caller's audio at configurable SNR | pal-agents `evals/drivers/noise.py` | 0.5d |
| **Accent simulation** | Use TTS voice variants (ElevenLabs: 20+ accent options) or voice cloning | Configuration, not code | 0.5d |

#### The SyntheticCaller Class (Core Implementation)

```python
class SyntheticCaller:
    """Joins a LiveKit room as a plain participant, speaks TTS,
    listens to agent audio, detects turn boundaries."""

    def __init__(self, room_name, livekit_url, api_key, api_secret, tts_provider):
        self.room = rtc.Room()
        self._audio_source = rtc.AudioSource(48000, 1)
        self._tts = tts_provider
        self._agent_state = "unknown"
        self._turn_complete = asyncio.Event()
        # Token with agent=False — production agent sees this as a human caller
        self._token = api.AccessToken(api_key, api_secret) \
            .with_identity("synthetic-caller") \
            .with_grants(api.VideoGrants(
                room_join=True, room=room_name,
                can_publish=True, can_subscribe=True,
                agent=False  # ← critical: agent treats caller as human
            )).to_jwt()

    async def connect(self):
        await self.room.connect(livekit_url, self._token)
        # Publish TTS audio as microphone track
        track = rtc.LocalAudioTrack.create_audio_track("caller-mic", self._audio_source)
        await self.room.local_participant.publish_track(track, ...)
        # Watch for agent state changes
        self.room.on("participant_attributes_changed", self._on_agent_state)

    def _on_agent_state(self, participant, changed):
        state = participant.attributes.get("lk.agent.state")
        if state == "listening" and self._agent_state == "speaking":
            self._turn_complete.set()  # Agent finished talking — caller's turn
        self._agent_state = state

    async def say(self, text: str) -> float:
        """Speak text via TTS. Returns duration in seconds."""
        start = time.monotonic()
        async for frame in self._tts.synthesize(text):
            await self._audio_source.capture_frame(frame)
        await self._audio_source.wait_for_playout()
        return time.monotonic() - start

    async def wait_for_agent_response(self, timeout=15.0) -> AgentResponse:
        """Wait for agent to finish speaking. Returns transcript + metrics."""
        self._turn_complete.clear()
        await asyncio.wait_for(self._turn_complete.wait(), timeout)
        # Agent audio frames were buffered during speaking — run STT on them
        transcript = await self._stt.transcribe(self._agent_audio_buffer)
        return AgentResponse(
            transcript=transcript,
            latency_ms=self._response_latency_ms,
            interruptions=self._interruption_count,
        )

    async def send_turn(self, message: str, history: list) -> TurnResult:
        """AgentDriver protocol implementation."""
        await self.say(message)
        response = await self.wait_for_agent_response()
        return TurnResult(
            response=response.transcript,
            tool_calls=response.tool_calls,
            latency_ms=response.latency_ms,
        )
```

#### Room Orchestration Flow

When `POST /v1/eval/run { driver: "voice" }` is called:

```
1. pal-mono eval_service:
   - Create LiveKit room "eval-{project_id}-{run_id}"
   - Dispatch production agent to the room via AgentDispatch API
   - Connect SyntheticCaller to the room
   - Start DUAL_CHANNEL_AGENT recording (egress to S3)

2. SyntheticCaller + VoiceConversationRunner:
   - Load scenario (YAML) + persona config
   - Turn 1: say scripted waypoint, wait for agent response
   - Turn 2-N: LLM persona generates next utterance, say it, wait
   - Capture all TurnResults (transcript, tool calls, latencies)

3. After scenario completes:
   - Stop recording
   - Download dual-channel recording from S3
   - Run audio evaluators (E14-E18) on the recording
   - Run transcript evaluators (E1-E9) on collected transcripts
   - Write all results to eval_results table
```

#### Dependencies and Prerequisites

| Prerequisite | Status | Needed For |
|---|---|---|
| LiveKit Cloud project | ✅ Already have | Room creation, agent dispatch |
| `livekit-rtc` Python SDK | ✅ In pal-mono deps | SyntheticCaller audio I/O |
| `livekit-api` Python SDK | ✅ In pal-mono deps | Room creation, egress control |
| AgentDispatch API | ✅ Available | Dispatch production agent to test room |
| Cartesia TTS API key | ✅ Already have | Synthetic caller voice |
| ElevenLabs API key | ❌ Need for accents | Optional — accent diversity. Cartesia works for standard voice. |
| Deepgram STT API key | ✅ Already have | Transcribe agent audio in the caller |
| `DUAL_CHANNEL_AGENT` recording | ❌ Need to enable (P2-A1) | Stereo recording for audio evaluators |

#### Revised Phase 2 Effort (P2-C1)

| Sub-Task | Effort | Description |
|---|---|---|
| SyntheticCaller core class | 2d | Room join, TTS publish, agent audio receive, turn detection via `lk.agent.state` + VAD fallback |
| VoiceConversationRunner | 1d | Multi-turn loop: scenario + persona + LLM-generated utterances |
| Room orchestration in eval_service | 1d | Room creation, agent dispatch, recording start/stop, result collection |
| Noise injection + accent config | 0.5d | Audio mixing for background noise; TTS voice variant config |
| Integration tests | 0.5d | End-to-end test with a simple echo agent |
| **Total** | **5d** | |

#### Open Questions (VoiceDriver-Specific)

1. **Agent dispatch timing**: When we create a room and dispatch the production agent, how long until it's ready to receive audio? Do we need to wait for `lk.agent.state == "listening"` before the caller speaks?

2. **Recording control**: Should the SyntheticCaller start/stop egress, or should pal-mono's eval_service do it via the Egress API? Recommendation: eval_service — it owns the lifecycle.

3. **STT for transcribing agent audio**: The SyntheticCaller needs to transcribe the agent's audio to feed to the LLM persona. Use the same Deepgram we use in production? Or Whisper for independence? Recommendation: Deepgram for speed (real-time streaming), Whisper as fallback ground truth.

4. **LiveKit Cloud costs**: Room-level simulation is free from a telephony perspective, but LiveKit Cloud may charge for room-minutes, egress, or bandwidth. Verify pricing for eval workloads.

5. **Concurrent eval rooms**: How many rooms can our LiveKit Cloud plan support simultaneously? This limits batch eval parallelism for voice scenarios.

6. **SIP-level testing (Approach B)**: Defer to Phase 3+ unless voice quality issues are traced to the telephony path specifically. Room-level catches 95% of issues at 0% of the cost.

---

### Reference: Industry Approaches Compared

| | Our VoiceDriver (Approach A) | Hamming | Coval | EVA (ServiceNow) |
|---|---|---|---|---|
| **Transport** | LiveKit room (direct participant) | LiveKit room OR SIP/PSTN | LiveKit room (via sandbox token) OR SIP/PSTN OR WebSocket | WebSocket (Pipecat) |
| **Synthetic caller** | `livekit-rtc` AudioSource + Cartesia TTS | Proprietary, 65+ languages, 20+ accents | Proprietary, LLM-driven personas | ElevenLabs Conversational AI |
| **Turn detection** | `lk.agent.state` attribute + Silero VAD | VAD on received audio | VAD on received audio | 600ms silence threshold |
| **Audio format** | 48kHz Opus (LiveKit native) | Codec-dependent (G.711 for PSTN, Opus for WebRTC) | Codec-dependent | 8kHz μ-law (Twilio-style) |
| **Scale** | 100+ concurrent (our agent worker capacity) | 1000+/min (their infrastructure) | Unknown (demo-gated) | Single conversation (research tool) |
| **Cost** | $0/call (room-level) | $1-3K/mo subscription | Demo-gated pricing | Free (open-source, but needs ElevenLabs API) |
| **Open source?** | ✅ Yes (our code) | ❌ No | ❌ No | ✅ Yes (MIT) |

---

## Build vs. Buy — Updated Assessment

The research dramatically shifts the build/buy calculation:

| Capability | Complexity (Original Estimate) | Complexity (Updated) | Why It Changed |
|---|---|---|---|
| Speaker diarization | High (pyannote, GPU) | **Eliminated** | `DUAL_CHANNEL_AGENT` gives us separate tracks natively |
| Interruption detection | High (audio overlap analysis) | **Near-zero** | `overlapping_speech` event fires in LiveKit with `is_interruption` flag |
| Response latency measurement | Medium (VAD + timestamp alignment) | **Near-zero** | `user_state_changed` + `agent_state_changed` events give exact timestamps |
| Silence gap detection | Medium (VAD analysis) | **Near-zero** | Derived from state change timestamps |
| STT accuracy (WER) | Medium (Whisper + jiwer) | Medium (unchanged) | Still need Whisper as ground truth — no shortcut |
| Speech rate | Medium (forced alignment) | Low | whisper-timestamped on separated channel |
| TTS speech fidelity | Unknown | Medium | LALM-as-Judge (GPT-4o audio) — new approach from EVA research |
| PSTN call simulation | High | High (unchanged) | Still hard — actual SIP calls, synthetic voices, noise injection |

**Updated recommendation**: Build all of it. The main obstacle (signal processing) is eliminated by LiveKit instrumentation. The hard remaining piece is the VoiceDriver (P2-C1) for end-to-end voice simulation — evaluate whether Hamming/Coval's PSTN infrastructure is worth $1-3K/mo for that specific capability.

---

## Revised Phase 2 Summary

| Task | Repo | Effort | Depends On |
|------|------|--------|------------|
| P2-A1 Instrument voice worker | pal-livekit-agent-cloud | 3d | — |
| P2-A2 Receive + store audio metrics | pal-mono | 1.5d | P2-A1 |
| P2-B1 Audio evaluators (E14–E18) | pal-agents + pal-mono | 3d | P2-A1, P2-A2 |
| P2-C1 Voice call simulation (SyntheticCaller + VoiceRunner + orchestration) | pal-agents + pal-mono | 5d | P2-A1 |
| **Phase 2 total** | | **12.5d** | |

Note: The DirectDriver (Phase 1) wraps LiveKit's built-in `AgentSession.run()` + `mock_tools()` + `judge()` framework. The implementation plan's `DirectDriver` class in `evals/drivers/direct.py` is a thin adapter around this LiveKit-native API, conforming to the `AgentDriver` protocol. We are not reimplementing LiveKit's testing infrastructure — we are wrapping it behind our protocol so scenarios and evaluators work identically across all drivers.

The first 3 evaluators (E14 interruptions, E15 latency/silence) ship for ~zero audio processing effort — they come directly from the instrumented LiveKit events. That's the quick win: instrument the pipeline (P2-A1), and 3 audio evaluators are free.

---

## Open Questions

1. **Dual-channel recording change**: Switching from mono mixed to `DUAL_CHANNEL_AGENT` stereo changes the audio file format for every call. Does any downstream consumer depend on mono? (S3 backup, human review, compliance?)
2. **RecorderIO vs. Egress**: Should we use LiveKit's built-in `RecorderIO` (captures at SDK level, stereo by default) or configure the Egress API for `DUAL_CHANNEL_AGENT`? RecorderIO is simpler but runs in the agent process.
3. **Whisper hosting**: STT accuracy evaluation (E16) needs Whisper large-v3 as ground truth. Self-host on GPU? Or use a hosted API (Groq Whisper, Replicate)?
4. **LALM-as-Judge for speech fidelity (E18)**: GPT-4o and Gemini both accept audio input. Which is more accurate for verifying spoken order confirmations? Need to benchmark.
5. **VoiceDriver telephony**: Does the VoiceDriver place calls via LiveKit's SIP infrastructure (internal) or via PSTN (external, more realistic but costs money)?
