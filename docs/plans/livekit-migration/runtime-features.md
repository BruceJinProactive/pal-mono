# LiveKit Runtime Features — Implementation Reference

Companion to [livekit-migration-technical.md](./livekit-migration-technical.md). Covers how Vapi runtime features map to LiveKit equivalents.

---

## Post-Call Analysis

### Current (Vapi)

Vapi runs an LLM analysis via `structuredDataPlan` at end of call. The prompt is in `services/voice_service/providers/vapi/_utils.py:7-63` (`CALL_ANALYSIS_PROMPT`). It extracts:

- `call_purpose` — array of `CallPurpose` enums → stored on `PhoneCall.call_purpose` + `Conversation.purpose`
- `language_spoken` — `CallLanguage` enum → stored on `PhoneCall.language` + `Conversation.language`
- `user_satisfaction` — positive/neutral/negative → stored on `PhoneCall.user_satisfaction`
- `explanation` — free text

Processing happens in `services/message_service/_utils.py`:
- `_extract_conversation_purpose()` (lines 407-429)
- `_extract_structured_data()` (lines 565-580)
- `_CALL_PURPOSE_MAPPING` (lines 635-651)

### LiveKit Equivalent

No built-in structured data extraction. Agent code runs it directly via `on_session_end` callback.

```python
async def on_session_end(ctx: JobContext) -> None:
    report = ctx.make_session_report()

    # report provides:
    #   chat_history  — full conversation transcript (ChatContext)
    #   duration      — call duration in seconds
    #   started_at    — start timestamp
    #   events        — all session events
    #   room_id       — LiveKit room ID
    #   job_id        — LiveKit job ID

    # Run same CALL_ANALYSIS_PROMPT against transcript via LLM
    transcript = format_chat_history(report.chat_history)
    analysis = await run_call_analysis(transcript, ended_reason)

    # Save to DB (same fields as today)
    await save_phone_call_record(
        call_purpose=analysis["call_purpose"],
        language=analysis["language_spoken"],
        user_satisfaction=analysis["user_satisfaction"],
        duration=report.duration,
        # ... latency metrics from report.events
    )

@server.rtc_session(on_session_end=on_session_end)
async def entrypoint(ctx: JobContext):
    session = AgentSession(...)
    await session.start(room=ctx.room, agent=agent)
```

**Execution order on call end:**
1. `session.on("close")` event fires (with `CloseReason`)
2. `session.aclose()` completes (drains speech, commits transcripts)
3. `on_session_end(ctx)` runs — **this is where post-call analysis goes**
4. Room disconnect
5. Process cleanup

### SessionReport Structure

```python
@dataclass
class SessionReport:
    job_id: str
    room_id: str
    room: rtc.Room
    events: list[AgentEvent]        # All session events
    chat_history: ChatContext        # Full conversation transcript
    started_at: float
    duration: float
    audio_recording_path: Path | None
```

---

## Disconnect Reason Mapping

### LiveKit DisconnectReason Enum

| Value | Code | Description |
|-------|------|-------------|
| `CLIENT_INITIATED` | 1 | Participant voluntarily disconnected (customer hung up) |
| `DUPLICATE_IDENTITY` | 2 | Another participant joined with same identity |
| `SERVER_SHUTDOWN` | 3 | Server shutting down |
| `PARTICIPANT_REMOVED` | 4 | Removed via RoomService API |
| `ROOM_DELETED` | 5 | Room explicitly deleted |
| `ROOM_CLOSED` | 10 | Room closed (empty_timeout / departure_timeout expired) |
| `USER_UNAVAILABLE` | 11 | Callee didn't answer (SIP) |
| `USER_REJECTED` | 12 | Callee rejected / busy (SIP) |
| `SIP_TRUNK_FAILURE` | 13 | SIP protocol failure |
| `CONNECTION_TIMEOUT` | 14 | Connection timed out |
| `MEDIA_FAILURE` | 15 | Media stream failure |

### AgentSession CloseReason Enum

| Value | Description |
|-------|-------------|
| `PARTICIPANT_DISCONNECTED` | Remote participant left (customer hung up) |
| `USER_INITIATED` | Agent code called `session.shutdown()` |
| `JOB_SHUTDOWN` | Job process shutting down |
| `ERROR` | Session crashed |
| `TASK_COMPLETED` | Task finished naturally |

### Mapping to Existing CallEndedReason

| CallEndedReason (DB) | Vapi Value | LiveKit Source |
|---|---|---|
| `customer_ended` | `customer-ended-call` | `DisconnectReason.CLIENT_INITIATED` |
| `assistant_forwarded` | `assistant-forwarded-call` | `CloseReason.USER_INITIATED` after SIP REFER transfer |
| `silence_timeout` | `silence-timed-out` | Custom: agent monitors `user_state_changed` → `"away"` + timer → `session.shutdown()` |
| `max_duration_exceeded` | `exceeded-max-duration` | Custom: agent-side timer → `session.shutdown()` |
| `misdialed` | `twilio-reported-customer-misdialed` | `DisconnectReason.SIP_TRUNK_FAILURE` or SIP status code |
| `other` | `other` | Any other reason |

### Silence Timeout Implementation

LiveKit does not have built-in silence timeout. Implement in agent code:

```python
SILENCE_TIMEOUT_SECONDS = 30

@session.on("user_state_changed")
def on_user_state_changed(event: UserStateChangedEvent):
    if event.state == "away":
        # User stopped speaking — start silence timer
        silence_timer = asyncio.get_event_loop().call_later(
            SILENCE_TIMEOUT_SECONDS,
            lambda: session.shutdown()
        )
    else:
        # User speaking again — cancel timer
        if silence_timer:
            silence_timer.cancel()
```

### Max Duration Implementation

```python
MAX_CALL_DURATION_SECONDS = 3600  # 1 hour

async def entrypoint(ctx: JobContext):
    session = AgentSession(...)
    await session.start(room=ctx.room, agent=agent)

    # Schedule max duration cutoff
    asyncio.get_event_loop().call_later(
        MAX_CALL_DURATION_SECONDS,
        lambda: session.shutdown()
    )
```

---

## Background Sound

### Current (Vapi)

`VoiceConfig.background_sound` — default `"office"`. Passed to Vapi's assistant config.

### LiveKit Equivalent

First-class `BackgroundAudioPlayer` with built-in clips:

| Built-in Clip | Description |
|---|---|
| `OFFICE_AMBIENCE` | Office chatter and background noise |
| `KEYBOARD_TYPING` | Keyboard typing sounds |
| `KEYBOARD_TYPING2` | Shorter keyboard typing |

```python
from livekit.agents import BackgroundAudioPlayer, AudioConfig, BuiltinAudioClip

background_audio = BackgroundAudioPlayer(
    ambient_sound=AudioConfig(BuiltinAudioClip.OFFICE_AMBIENCE, volume=0.8),
    thinking_sound=[
        AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.8),
        AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.7),
    ],
)
await background_audio.start(room=ctx.room, agent_session=session)
```

**Mapping:** `background_sound: "office"` → `BuiltinAudioClip.OFFICE_AMBIENCE`. Custom audio files also supported.

**Thinking sound** is a bonus — plays while agent is processing. Not available in Vapi.

---

## SIP Participant Attributes

SIP participants expose these via `participant.attributes`:

| Key | Example | Description |
|---|---|---|
| `sip.callID` | `"abc123"` | LiveKit's SIP call ID |
| `sip.callIDFull` | `"xyz789"` | Trunk provider's globally unique SIP call ID |
| `sip.callStatus` | `"active"` / `"hangup"` | Current call state |
| `sip.phoneNumber` | `"+15551234567"` | Caller's phone number |
| `sip.trunkID` | `"trunk_001"` | SIP trunk identifier |
| `sip.trunkPhoneNumber` | `"+15559876543"` | Business phone number on the trunk |
| `sip.ruleID` | `"rule_001"` | Dispatch rule ID (inbound) |

For Twilio trunks, also: `sip.twilio.accountSid`, `sip.twilio.callSid`.

These replace the metadata that Vapi passes in the `assistant-request` webhook (`customer.number`, `phoneNumber.number`).

---

## Latency Metrics

### Current (Vapi)

Vapi sends `performanceMetrics` in `end-of-call-report` with per-turn:
- `turnLatency`, `modelLatency`, `voiceLatency`, `transcriberLatency`, `endpointingLatency`

Stored as averages on `PhoneCall` (in seconds, converted from ms).

### LiveKit Equivalent

Subscribe to `metrics_collected` event on `AgentSession`:

```python
@session.on("metrics_collected")
def on_metrics(event: MetricsCollectedEvent):
    # event contains per-turn latency data
    # Accumulate and average at call end
    pass
```

Also available in `SessionReport.events` during `on_session_end`. Filter for metric events and compute averages.

Metric types available: STT latency, LLM TTFT, TTS TTFB, end-to-end turn latency.

---

## Usage Tracking / Billing Filters

### Current Logic (`_should_track_call_usage()`)

Skip tracking if:
1. Test phone number (configured via `TEST_PHONE_NUMBERS` env var)
2. Call duration < 10 seconds
3. Customer didn't speak (no `role="user"` messages in artifact)

### LiveKit Equivalent

Same logic, different data sources:
1. Test number → check `participant.attributes["sip.phoneNumber"]` against test list
2. Duration → `report.duration` from `SessionReport`
3. Customer didn't speak → check `report.chat_history` for user messages, or track via `user_input_transcribed` events

---

## Related Documents

- [Technical Migration Plan](./livekit-migration-technical.md)
- [Call Transfer Analysis](./livekit-call-transfer-analysis.md)
