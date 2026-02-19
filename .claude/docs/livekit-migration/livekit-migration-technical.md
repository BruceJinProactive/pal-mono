# LiveKit Migration — Technical Plan

## Architecture: How LiveKit Works vs Vapi

**The core shift:** Vapi is a managed service that owns the call pipeline and communicates via webhooks. LiveKit is infrastructure — we run a long-lived **agent worker process** that joins calls, manages the STT → LLM → TTS pipeline in-process, and writes results to our DB directly. There are no conversation-level webhooks.

**Agent framework:** We use `pal-agents` (`PalAgent` with `Spec` and `RuntimeContext`). Agno is being fully dropped.

| Concern | Vapi (current) | LiveKit (target) |
|---------|---------------|------------------|
| **Architecture** | Managed platform, webhook-driven | You run an agent worker process that connects to LiveKit server |
| **Call start** | Vapi sends `assistant-request` webhook, you return config JSON | Agent process receives a `JobContext` when a SIP participant joins a room. Agent reads config from DB. |
| **LLM integration** | Vapi calls your `/v1/chat/completions` endpoint (custom-llm provider) | **Option A:** LiveKit OpenAI plugin with `base_url` → your API. **Option B:** Run PalAgent in-process. |
| **Tool calling** | Vapi sends `tool-calls` webhook → you execute → return result | **Option A:** Tools execute via existing API (through chat completions). **Option B:** `@function_tool` decorator, in-process. |
| **Call transfer** | POST to Vapi control URL with transfer payload | SIP REFER (cold) or warm transfer via LiveKit SIP API |
| **Transcript** | Vapi sends `end-of-call-report` with full transcript | Agent accumulates transcript from STT events. Writes to DB on call end. |
| **Call metrics** | Vapi includes latency breakdown in `end-of-call-report` | Self-instrumented pipeline (STT, LLM, TTS latencies). |
| **Webhooks** | `assistant-request`, `status-update`, `end-of-call-report`, `function-call`, `tool-calls` | Infrastructure-only: `room_started`, `room_finished`, `participant_joined`, `participant_left`. |
| **Phone numbers** | Import Twilio numbers into Vapi via SDK | Keep numbers in Twilio. SIP trunk routes to LiveKit. |
| **Multi-language** | Squads with triage assistant for language detection | Not needed — Sonic-3 accent localization + Deepgram nova-3 multilingual handles natively. |
| **Telephony** | Built-in (Twilio under the hood) | Bring your own SIP trunk (Twilio, Telnyx, etc.) |
| **STT** | Configured declaratively in assistant JSON (Deepgram) | Configured in agent code: `stt="deepgram/nova-3"` |
| **TTS** | Configured declaratively in assistant JSON (Cartesia) | Configured in agent code: `tts="cartesia/sonic-3:<voice_id>"` |

### Key Implication

The 1,917-line Vapi webhook handler (`api/routes/integrations/vapi/_implementation.py`) does **not** get ported to a new webhook handler. It gets **replaced by agent worker code** that runs as a long-lived process. The logic moves from "respond to webhooks" to "run inside the call."

---

## LLM Integration Decision: Option A vs Option B

This is the most important architectural decision.

### Option A: External LLM Endpoint (simpler migration)

LiveKit's OpenAI plugin supports `base_url` — point it at your existing `/v1/chat/completions` endpoint.

```python
session = AgentSession(
    stt="deepgram/nova-3",
    llm=openai.LLM(
        model="project_456:agent_789",
        base_url="https://pal-api.example.com/v1",
        api_key="<token>",
    ),
    tts="cartesia/sonic-3:<voice_id>",
)
```

**Pros:** Minimal refactoring. Keep existing API, message service, and tool execution as-is.
**Cons:** Network round-trip per LLM turn (same latency as Vapi). Tool calls still go through API.

### Option B: In-Process PalAgent (better latency)

Run `PalAgent` directly inside the LiveKit agent worker.

```python
@server.rtc_session(agent_name="palona-agent")
async def entrypoint(ctx: JobContext):
    spec = await construct_agent_spec(session, agent_id, ...)
    pal_agent = PalAgent(spec=spec)
    session = AgentSession(
        stt="deepgram/nova-3",
        llm=PalAgentLLMAdapter(pal_agent),
        tts="cartesia/sonic-3:<voice_id>",
    )
```

**Pros:** No network hop for LLM or tool calls. Lower turn latency.
**Cons:** Agent worker needs DB sessions, HTTP clients, AWS Secrets Manager access. Must build `PalAgentLLMAdapter`.

### Recommendation

Start with **Option A** for faster time-to-production. Migrate to **Option B** later as a latency optimization.

---

## Current Vapi Integration Footprint

### Tightly Coupled (must be rewritten)

| Area | File | ~Lines | What it does |
|------|------|--------|-------------|
| Webhook handler | `api/routes/integrations/vapi/_implementation.py` | 1,917 | Handles all Vapi events: assistant-request, status-update, tool-calls, end-of-call-report |
| Vapi tool | `tools/vapi_tool/_implementation.py` | 494 | Call transfer via Vapi control URL |
| Vapi provider | `services/voice_service/providers/vapi/_implementation.py` | ~150 | Builds Vapi assistant/squad configs, voice settings |
| Assistant creation | `api/routes/integrations/vapi/__init__.py` | 145 | Routes + schemas for assistant/squad creation |
| Message utils | `services/message_service/_utils.py` | ~200 | `transform_vapi_conversation_data()`, `transform_vapi_call_data()` |

### Moderately Coupled (needs adaptation)

| Area | File | What changes |
|------|------|-------------|
| Conversation model | `db/tables/conversations.py` | `vapi_control_url` and `call_id` fields are Vapi-specific |
| PhoneCall model | `db/tables/phonecalls.py` | Latency metrics match Vapi's schema |
| VoiceConfig model | `db/tables/voice_configs.py` | `raw_config` stores Vapi assistant JSON blob |
| Agent raw config | `services/agent_service/_raw_config.py` | `_populate_vapi_tool_args()`, `VOICE_ONLY_TOOLS` filtering |
| Voice service | `services/voice_service/_implementation.py` | Orchestrates VAPIProvider — needs new LiveKit provider |
| Tool registry | `tools/registry.py` | `vapi_tool` registration |

### Loosely Coupled (minimal or no changes)

| Area | Notes |
|------|-------|
| pal-agents (`PalAgent`, `Spec`, `RuntimeContext`) | Provider-agnostic |
| Business tools (Adora, Toast, Square, etc.) | Independent of voice platform |
| DB enums (Channel, CallEndedReason, CallPurpose) | Generic enough to reuse |
| Project/Contact models | Transfer destinations are phone numbers, not Vapi-specific |

---

## Implementation Phases

### Phase 0: Foundation (no dependencies)

#### 0A. LiveKit server infrastructure
- Provision LiveKit Cloud or self-host
- Get API key and secret
- Add `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` to config/secrets

#### 0B. SIP trunk provisioning
- Keep phone numbers in Twilio
- Configure Twilio SIP trunk to route calls to LiveKit server
- Create LiveKit inbound trunk + dispatch rules (phone numbers → rooms → agent)
- Test: raw call comes in, LiveKit room created, agent process receives `JobContext`
- **Note:** SIP REFER cold transfers work over SIP-over-TLS. For Twilio trunks, enable "Enable PSTN Transfer" and use TLS via port 5061 / `SIP_TRANSPORT_TLS`.

#### 0C. Add Python dependencies
- Add `livekit-agents`, `livekit-api`, `livekit-plugins-deepgram`, `livekit-plugins-cartesia`, `livekit-plugins-silero` (VAD)
- Keep `vapi-server-sdk` for now (parallel running)

> 0A and 0B can run in parallel. 0C is independent.

---

### Phase 1: Agent Pipeline (depends on 0A, 0C)

#### 1A. Minimal LiveKit agent entrypoint
- `@server.rtc_session(agent_name="palona-agent")` entrypoint
- On SIP participant join: start `AgentSession` with VAD (Silero), STT (Deepgram), TTS (Cartesia), LLM (OpenAI plugin with `base_url`)
- Play first greeting via `session.generate_reply()`
- Test: call yourself, hear greeting, agent responds

#### 1B. Wire PalAgent as LLM backend
- **Option A:** Point `base_url` at existing chat completions endpoint. Minimal changes.
- **Option B (later):** Build `PalAgentLLMAdapter` implementing LiveKit's LLM interface. Worker needs DB sessions, HTTP clients, Secrets Manager.

#### 1C. Wire up tools
- **Option A:** Tools execute via existing message service (through chat completions). No changes.
- **Option B:** Register as `@function_tool`, execute in-process. Requires tool runtime context in worker.

> Option A: 1A → 1B straightforward. Option B: 1A → 1B → 1C sequential, 1B is hardest.

---

### Phase 2: Voice Config & Project Resolution (depends on 1A)

#### 2A. New LiveKit provider
- `services/voice_service/providers/livekit/_implementation.py`
- Reads `VoiceConfig` from DB → returns STT config, TTS config, first_message, background_sound
- Agent entrypoint uses this to configure `AgentSession` per call

#### 2B. Room metadata for project resolution
- SIP dispatch rules pass caller metadata (dialed number, caller number) as participant attributes
- Agent reads `ctx.room` attributes to resolve project, user, agent config
- Replaces `handle_assistant_request()` webhook logic
- Creates conversation record

#### 2C. Adapt VoiceConfig model
- `raw_config` stores Vapi assistant JSON — repurpose or add `livekit_config` field
- `voice_model` ("sonic-2"/"sonic-3") maps directly to Cartesia
- `transcriber` dict maps directly to Deepgram
- Speech rate mappings carry over
- Voice provider determined at runtime via LiveKit SIP API (no DB column needed initially)

> 2A and 2B in parallel. 2C independent.

---

### Phase 3: Call Transfer (depends on 1A, 0B)

See also: [Call Transfer Analysis](./livekit-call-transfer-analysis.md)

#### 3A. Replace VapiTool with LiveKitTransferTool
- New tool: `tools/livekit_transfer_tool/`
- **Cold transfer:** SIP REFER via `transfer_sip_participant` (works over TLS; Twilio trunks need "Enable PSTN Transfer")
- **Warm transfer:** Outbound SIP call bridged into room
- Same interface: `call_transfer(purpose="general")`
- Destination lookup unchanged — contacts table → phone numbers
- **Caller ID:** On outbound SIP trunk, not in transfer payload
- **Pre-transfer message:** `session.generate_reply()` before transfer

#### 3B. Update agent service raw config
- `VOICE_ONLY_TOOLS`: `"vapi_tool"` → `"livekit_transfer_tool"`
- `_populate_vapi_tool_args()` → `_populate_transfer_tool_args()` (rename, same logic)
- `if tool_name == "vapi_tool"` → `"livekit_transfer_tool"`

> 3A → 3B sequential.

---

### Phase 4: Call Lifecycle Events (depends on 1A, 2B)

#### 4A. Call status tracking
- Hook room events: `participant_connected`, `participant_disconnected`, `track_subscribed`
- Update conversation status
- Store `room_id` / `sip_call_id` instead of `vapi_control_url`

#### 4B. End-of-call processing
- **No webhook — agent code does this.** On participant disconnect / agent shutdown:
  - Close conversation (CLOSING → CLOSED)
  - Compute call duration from room timestamps
  - Save transcript (accumulated from STT events)
  - Create `PhoneCall` record
  - Fire post-hangup webhook
  - Track usage to Stripe

#### 4C. Latency instrumentation
- Measure: turn latency, STT latency, LLM latency, TTS latency
- Send to Datadog
- Update `PhoneCall` columns if metric names change

#### 4D. Billing / usage tracking
- Compute duration on call end, send Stripe meter event
- Same filtering: skip test numbers, short calls, no-speech calls

> 4A, 4B depend on 2B. 4C depends on 1A. 4D depends on 4B.

---

### ~~Phase 5: Multi-Language~~ (DROPPED)

> Not needed. Sonic-3 with accent localization + Deepgram nova-3 multilingual handles language adaptation at the model level. The Vapi triage squad is deleted as part of cleanup. No separate language detection or mid-call switching required.

---

### Phase 5: Error Handling & Fallbacks

#### 5A. LLM backend unavailable
- Play fallback message, initiate automatic transfer to default human contact

#### 5B. STT/TTS provider failure
- Configure fallback providers (backup Deepgram model, system TTS)

#### 5C. Call quality monitoring
- Monitor jitter, packet loss via LiveKit room stats

---

### Phase 6: Phone Number Management (depends on 0B)

#### 6A. SIP trunk routing for existing numbers
- For each number to migrate: update Twilio SIP trunk to point to LiveKit
- Create matching LiveKit inbound trunk rule + dispatch rule

#### 6B. Number provisioning automation
- New numbers: configure LiveKit dispatch rules instead of importing into Vapi
- Released numbers: query `ListSIPDispatchRule` by phone number to find the dispatch rule ID, then delete it
- Replace Vapi SDK calls with LiveKit SIP API calls

#### 6C. Per-number routing during migration
- Determine voice provider per number by querying LiveKit SIP API at runtime:
  - Call `ListSIPDispatchRule` and match by phone number (dispatch rules are named `inbound-{number}`)
  - If a matching dispatch rule exists → number is routed to LiveKit
  - If no dispatch rule found → number is routed to Vapi (default)
- No local `phone_number_configs` database table needed initially — LiveKit is the source of truth for its own dispatch rules
- Per-number routing enables canary migration (test individual numbers on LiveKit while others stay on Vapi)
- Provisioning branches by provider: Vapi SDK import vs. Twilio SIP trunk assignment + LiveKit dispatch rule creation
- **Future optimization:** If API lookups become a latency bottleneck (e.g., high call volume or frequent admin page loads), consider adding a local `phone_number_configs` table as a cache of LiveKit provisioning state

---

### Phase 7: DB Migration & Cleanup (depends on phases 1–6)

#### 7A. Schema migration
- Rename `vapi_control_url` → `call_control_id` on conversations
- Adjust `PhoneCall` latency columns if needed
- Migration script

#### 7B. Remove Vapi code
- Delete `api/routes/integrations/vapi/` (entire directory)
- Delete `tools/vapi_tool/`
- Delete `services/voice_service/providers/vapi/`
- Remove from `tools/registry.py`, router includes
- Remove `vapi-server-sdk` from `pyproject.toml`
- Remove Vapi env vars
- Remove `agno` from `pyproject.toml`

#### 7C. Remove assistant creation API
- Delete `POST /v1/integrations/vapi/assistants` — LiveKit agents are dynamic

> 7A anytime after new code works. 7B only after zero projects on Vapi.

---

## Dependency Graph

```
0A (LiveKit server) ──┐
0B (SIP trunk) ───────┤
0C (Dependencies) ────┘
         │
         v
      1A (Agent entrypoint)
         │
    ┌────┼──────────────┐
    v    v              v
  1B   2A,2B          4C (Latency)
(LLM   (Provider,
 wire) Project)
    │    │
    v    │
  1C     │
(Tools)  │
    │    │
    ├────┘
    v
  3A (Transfer tool) ──> 3B (Agent config)
    │
    v
  4A,4B (Call lifecycle) ──> 4D (Billing)
    │
    ├──> 5A,5B,5C (Error handling)
    v
  6A,6B,6C (Phone number management)
    │
    v
  7A,7B,7C (Migration & cleanup)
```

## Critical Path

```
0A → 0B → 1A → 1B → parallel(2A, 2B, 4C) → parallel(3A, 4A, 4B) → 6A → 7B
```

Riskiest items:
1. **0B (SIP trunk setup)** — Validates Twilio ↔ LiveKit telephony works
2. **3A (Call transfer)** — SIP REFER works over TLS but requires Twilio "Enable PSTN Transfer"; warm transfer needed for PSTN-to-SIP destinations
3. **1B with Option B** — Bridging PalAgent interface to LiveKit's LLM interface is the most complex piece

**Recommendation:** Spike on **0B + 1A** before committing to the full build.

---

## Tool Calling Migration Impact

### How Tool Calling Changes

| Concern | Vapi (current) | LiveKit (target) |
|---------|---------------|------------------|
| **Execution model** | Vapi sends `tool-calls` webhook → handler executes → returns result | **Option A:** Same — tools execute via chat completions API. **Option B:** In-process in agent worker. |
| **Latency** | Network round-trip per tool call | **Option A:** Same. **Option B:** Zero network overhead. |
| **Runtime context** | Tools run inside FastAPI request with DB session from webhook | **Option A:** Same. **Option B:** Agent worker must set up own DB sessions, HTTP clients, Secrets Manager. |

### Tools Requiring Changes

#### 1. VapiTool → LiveKitTransferTool (REWRITE)

**File**: `tools/vapi_tool/_implementation.py` (494 lines)

| Current | Change |
|---------|--------|
| Contact destination lookup by purpose | **Same** |
| Fetches `vapi_control_url` from conversation | **Remove** — no control URL in LiveKit |
| Fallback to Vapi API | **Remove** |
| Builds Vapi transfer payload | **Replace** with LiveKit SIP transfer API |
| Sets caller ID in payload | **Rethink** — configured on SIP trunk |
| Validates `channel == VOICE` | **Same** |

#### 2. Agent Service Raw Config (ADAPT)

**File**: `services/agent_service/_raw_config.py`

| Current | Change |
|---------|--------|
| `VOICE_ONLY_TOOLS = {"vapi_tool"}` | → `{"livekit_transfer_tool"}` |
| `_populate_vapi_tool_args()` | → `_populate_transfer_tool_args()` (same logic) |
| `if tool_name == "vapi_tool"` | → `"livekit_transfer_tool"` |

#### 3. Tool Registry (SWAP)

**File**: `tools/registry.py` — `"vapi_tool": VapiTool` → `"livekit_transfer_tool": LiveKitTransferTool`

### Tools Requiring Verification (no code changes)

| Tool | Why verify |
|------|-----------|
| `store_messaging_tool` | Uses `customer_phone` from metadata — verify SIP metadata provides same format |
| `catering_tool` | Fires EventBridge event — verify event fires when call context comes from LiveKit |

### Tools Requiring Zero Changes (14 tools)

All business tools are channel-agnostic: `toast_tool`, `adora_tool`, `adora_v2_tool`, `square_tool`, `olo_tool`, `resy_tool`, `resy_tool_with_reservation`, `minitable_tool`, `opentable_tool`, `yelp_tool`, `yelp_credit_card_tool`, `yelp_no_credit_card_tool`, `menusifu_tool`

### Runtime Context: Agent Worker Setup (Option B only)

All tools receive `ToolMetadata` (customer_phone, store_phone, session_id, agent_id, channel, timezone). With Option B, the agent worker entrypoint must construct this from SIP participant attributes.

Agent worker process must also provide:
- **Async DB session factory** — for tools that persist data
- **HTTP client pools** — for tools calling external APIs
- **AWS Secrets Manager access** — for tools fetching credentials at runtime

---

## Related Documents

- [Call Transfer Analysis](./livekit-call-transfer-analysis.md) — Deep dive on transfer mechanisms, risks, and proposed tool structure
- [Runtime Features Reference](./livekit-runtime-features.md) — Post-call analysis, disconnect reason mapping, background sound, SIP attributes, latency metrics, billing filters
