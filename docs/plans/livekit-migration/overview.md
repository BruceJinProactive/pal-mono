# Vapi to LiveKit Migration Plan

## Overview

Migrate the voice AI platform from Vapi (managed webhook-driven service) to LiveKit (open-source infrastructure with self-hosted agent process).

**The core architectural shift:** Vapi is a managed service that owns the call pipeline and communicates with us via webhooks. LiveKit is infrastructure — we run a long-lived **agent worker process** that joins calls, manages the STT → LLM → TTS pipeline in-process, and writes results to our DB directly. There are no conversation-level webhooks. LiveKit only emits infrastructure events (room started, participant joined/left).

**Agent framework:** We use `pal-agents` (`PalAgent` with `Spec` and `RuntimeContext`). Agno is being fully dropped.

---

## How LiveKit Actually Works (vs Vapi)

Understanding this section is critical — the rest of the plan follows from these differences.

| Concern | Vapi (current) | LiveKit (actual) |
|---------|---------------|------------------|
| **Architecture** | Managed platform, webhook-driven | You run an agent worker process that connects to LiveKit server |
| **Call start** | Vapi sends `assistant-request` webhook, you return config JSON | Your agent process receives a `JobContext` when a SIP participant joins a room. Agent code reads config from your DB. |
| **LLM integration** | Vapi calls your `/v1/chat/completions` endpoint (custom-llm provider) | **Two options:** (A) Use LiveKit OpenAI plugin with `base_url` pointing to your API, or (B) run PalAgent in-process. Option B is faster (no network hop) but more work. |
| **Tool calling** | Vapi sends `tool-calls` webhook → you execute → return result | Tools defined with `@function_tool` decorator, execute in-process in agent worker |
| **Call transfer** | POST to Vapi control URL with transfer payload | SIP REFER (cold) or warm transfer via LiveKit SIP API, called from within agent code |
| **Transcript** | Vapi sends `end-of-call-report` webhook with full transcript | No webhook. Your agent accumulates transcript from STT events during the call. You write it to your DB on call end. |
| **Call metrics** | Vapi includes latency breakdown in `end-of-call-report` | No webhook. You instrument your own pipeline (STT, LLM, TTS latencies). |
| **Webhooks** | `assistant-request`, `status-update`, `end-of-call-report`, `function-call`, `tool-calls` | LiveKit webhooks are infrastructure-level only: `room_started`, `room_finished`, `participant_joined`, `participant_left`. No conversation semantics. |
| **Phone numbers** | Import Twilio numbers into Vapi via SDK (`phone_numbers.create`) | Keep numbers in Twilio. Configure SIP trunk to route calls to LiveKit. LiveKit also offers LiveKit Phone Numbers for US numbers. |
| **Multi-language** | Squads with triage assistant that detects language and transfers to language-specific assistant | In-agent language detection. Hot-swap STT/TTS config mid-call. No squad concept. |
| **Telephony** | Built-in (Twilio under the hood) | You bring your own SIP trunk (Twilio, Telnyx, etc.) or use LiveKit Phone Numbers |
| **STT** | Configured declaratively in assistant JSON (Deepgram) | Configured in agent code: `stt="deepgram/nova-3"` |
| **TTS** | Configured declaratively in assistant JSON (Cartesia) | Configured in agent code: `tts="cartesia/sonic-3:<voice_id>"` |

### Key Implication

The 1,917-line Vapi webhook handler (`api/routes/integrations/vapi/_implementation.py`) does not get "ported" to a new webhook handler. It gets **replaced by agent worker code** that runs as a long-lived process. The logic moves from "respond to webhooks" to "run inside the call."

---

## LLM Integration Decision: Option A vs Option B

This is the most important architectural decision for the migration.

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
**Cons:** Network round-trip per LLM turn (same latency as Vapi). Tool calls still go through your API.

### Option B: In-Process PalAgent (better latency)

Run `PalAgent` directly inside the LiveKit agent worker. LLM calls, tool execution, and DB access all happen in-process.

```python
@server.rtc_session(agent_name="palona-agent")
async def entrypoint(ctx: JobContext):
    spec = await construct_agent_spec(session, agent_id, ...)
    pal_agent = PalAgent(spec=spec)
    # Wire PalAgent into LiveKit pipeline as the LLM
    session = AgentSession(
        stt="deepgram/nova-3",
        llm=PalAgentLLMAdapter(pal_agent),
        tts="cartesia/sonic-3:<voice_id>",
    )
```

**Pros:** No network hop for LLM or tool calls. Lower turn latency.
**Cons:** Agent worker needs DB sessions, HTTP clients, AWS Secrets Manager access. Must build `PalAgentLLMAdapter` that bridges PalAgent's interface to LiveKit's LLM interface.

### Recommendation

Start with **Option A** for faster time-to-production. Migrate to **Option B** later as a latency optimization. Option A lets you validate the full pipeline (SIP, STT, TTS, transfer) without touching the agent framework.

---

## Current Vapi Integration Footprint

### Tightly Coupled (must be rewritten)

| Area | File | ~Lines | What it does |
|------|------|--------|-------------|
| Webhook handler | `api/routes/integrations/vapi/_implementation.py` | 1,917 | Handles all Vapi events: assistant-request, status-update, tool-calls, end-of-call-report |
| Vapi tool | `tools/vapi_tool/_implementation.py` | 494 | Call transfer via Vapi control URL |
| Vapi provider | `services/voice_service/providers/vapi/_implementation.py` | ~150 | Builds Vapi assistant/squad configs, voice settings |
| Assistant creation | `api/routes/integrations/vapi/__init__.py` | 145 | Routes + schemas for assistant/squad creation |
| Message utils | `services/message_service/_utils.py` | ~200 | `transform_vapi_conversation_data()`, `transform_vapi_call_data()` — parses Vapi payloads |

### Moderately Coupled (needs adaptation)

| Area | File | What changes |
|------|------|-------------|
| Conversation model | `db/tables/conversations.py` | `vapi_control_url` and `call_id` fields are Vapi-specific |
| PhoneCall model | `db/tables/phonecalls.py` | Latency metrics match Vapi's schema (turn, model, voice, transcriber, endpointing) |
| VoiceConfig model | `db/tables/voice_configs.py` | `raw_config` is a Vapi assistant config blob; `voice_model` is Cartesia-specific ("sonic-2/3") |
| Agent raw config | `services/agent_service/_raw_config.py` | `_populate_vapi_tool_args()`, `VOICE_ONLY_TOOLS` filtering |
| Voice service | `services/voice_service/_implementation.py` | Orchestrates VAPIProvider — needs new LiveKit provider |
| Tool registry | `tools/registry.py` | `vapi_tool` registration |

### Loosely Coupled (minimal or no changes)

| Area | Notes |
|------|-------|
| pal-agents (`PalAgent`, `Spec`, `RuntimeContext`) | Agent framework is provider-agnostic |
| Business tools (Adora, Toast, Square, etc.) | Independent of voice platform |
| DB enums (Channel, CallEndedReason, CallPurpose) | Generic enough to reuse |
| Project/Contact models | Transfer destinations are phone numbers, not Vapi-specific |

---

## Implementation Phases

### Phase 0: Foundation (no dependencies, do first)

#### 0A. LiveKit server infrastructure
- Provision LiveKit Cloud account **or** self-host LiveKit server
- Get API key and secret
- Add `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` to config/secrets

#### 0B. SIP trunk provisioning
- Keep phone numbers in Twilio — do not "import" into LiveKit
- Configure Twilio SIP trunk with origination URI pointing to LiveKit's SIP endpoint
- Create one LiveKit inbound trunk (shared across all numbers)
- Create one shared **callee dispatch rule** — routes calls to rooms named by the dialed number automatically (no per-number dispatch rules needed)
- Test: raw call comes in, a LiveKit room is created, agent process receives `JobContext`
- **Note:** SIP REFER (cold transfer) is not supported over SIP-over-TLS. If using TLS, plan for warm transfer (bridge) approach.

#### 0C. Add Python dependencies
- Add `livekit-agents`, `livekit-api`, `livekit-plugins-deepgram`, `livekit-plugins-cartesia`, `livekit-plugins-silero` (VAD) to `pyproject.toml`
- Keep `vapi-server-sdk` for now (parallel running)

> 0A and 0B can happen in parallel. 0C is independent.

---

### Phase 1: Agent Pipeline (depends on 0A, 0C)

Core phase — a LiveKit agent worker that replaces what Vapi did as a managed service.

#### 1A. Minimal LiveKit agent entrypoint
- Create agent worker with `@server.rtc_session(agent_name="palona-agent")` entrypoint
- When a SIP participant joins a room, the agent joins and starts an `AgentSession` with:
  - **VAD**: Silero
  - **STT**: Deepgram (`deepgram/nova-3`)
  - **TTS**: Cartesia (`cartesia/sonic-3:<voice_id>`)
  - **LLM**: OpenAI plugin with `base_url` pointing to your existing `/v1/chat/completions` (Option A)
- Call `session.generate_reply()` to play the first greeting
- Test: call yourself, hear a hardcoded greeting, agent responds

#### 1B. Wire PalAgent as the LLM backend
- **If Option A:** Point LiveKit's OpenAI plugin `base_url` at your existing chat completions endpoint. PalAgent already handles requests there via the message service. Minimal changes.
- **If Option B (later optimization):** Build a `PalAgentLLMAdapter` that implements LiveKit's `LLM` interface, constructs `Spec` + `RuntimeContext`, and delegates to `PalAgent.run()`. Agent worker needs its own DB sessions, HTTP clients, and AWS Secrets Manager access.

#### 1C. Wire up tools
- **If Option A:** Tools continue executing via the existing message service (called through `/v1/chat/completions`). No changes.
- **If Option B:** Tools execute in-process. Register them as `@function_tool` decorators in the LiveKit agent or bridge pal-agents' tool system. Requires tool runtime context (DB, HTTP, secrets) in the worker.

> With Option A: 1A → 1B is straightforward. With Option B: 1A → 1B → 1C is sequential and 1B is the hardest part.

---

### Phase 2: Voice Config & Project Resolution (depends on 1A)

#### 2A. New LiveKit provider
- Create `services/voice_service/providers/livekit/_implementation.py`
- Replace `VAPIProvider` — instead of building a Vapi assistant JSON blob, this provider:
  - Reads `VoiceConfig` from DB (same table)
  - Returns STT config (Deepgram model, language) and TTS config (Cartesia voice_id, speed, model)
  - Returns first_message, background_sound settings
- Agent entrypoint calls this provider to configure the `AgentSession` dynamically per call

#### 2B. Room metadata for project resolution
- Configure SIP dispatch rules to pass caller metadata (dialed number, caller number) as SIP participant attributes
- Agent entrypoint reads `ctx.room` participant attributes to resolve project, user, and agent config
- Replaces the `handle_assistant_request()` webhook logic
- Creates conversation record with `channel=VOICE`

#### 2C. Adapt VoiceConfig model
- `raw_config` field currently stores Vapi assistant JSON — repurpose or add a `livekit_config` field
- `voice_model` ("sonic-2"/"sonic-3") maps directly to Cartesia (same provider)
- `transcriber` dict maps directly to Deepgram config
- Speech rate mappings carry over (already Cartesia values)
- DB migration: add `provider` column or just reinterpret existing fields

> 2A and 2B can happen in parallel once 1A exists. 2C is independent.

---

### Phase 3: Call Transfer (depends on 1A, 0B)

#### 3A. Replace VapiTool with LiveKitTransferTool
- New tool in `tools/livekit_transfer_tool/`
- Instead of POSTing to a Vapi control URL, use LiveKit's SIP transfer:
  - **Cold transfer:** SIP REFER via `transfer_sip_participant` (requires non-TLS SIP trunk)
  - **Warm transfer:** Create outbound SIP call and bridge into the room
- Same interface: `call_transfer(purpose="general")` looks up contact, initiates transfer
- Destination lookup logic stays the same — contacts table → phone numbers
- **Caller ID:** Configured on the outbound SIP trunk or per-call in the transfer API, not in the transfer payload
- **Pre-transfer message:** Use `session.generate_reply("I'll transfer you now")` before initiating transfer

#### 3B. Update agent service raw config
- `services/agent_service/_raw_config.py`: Replace `vapi_tool` references with new tool name
- `VOICE_ONLY_TOOLS` set: swap `"vapi_tool"` → `"livekit_transfer_tool"`
- `_populate_vapi_tool_args()` → `_populate_transfer_tool_args()` (rename, same logic)

> 3A → 3B is sequential.

---

### Phase 4: Call Lifecycle Events (depends on 1A, 2B)

#### 4A. Call status tracking
- LiveKit emits room events: `participant_connected`, `participant_disconnected`, `track_subscribed`
- Hook these in the agent entrypoint to update conversation status
- Replaces `handle_status_update()` webhook
- Store `room_id` or `sip_call_id` instead of `vapi_control_url` on conversation

#### 4B. End-of-call processing
- **No webhook delivers this — your agent code must do it.** On `participant_disconnected` or agent shutdown:
  - Close conversation (set status CLOSING → CLOSED)
  - Compute call duration from room timestamps
  - Save transcript (accumulated from STT events during the call)
  - Create `PhoneCall` record with duration and metrics
  - Fire post-hangup webhook (`_post_hangup_webhook()` logic carries over)
  - Track usage to Stripe for billing
- Replaces `handle_session_closure()`

#### 4C. Latency instrumentation
- Instrument the pipeline to measure:
  - Turn latency (silence end → speech start)
  - STT latency (audio chunk → transcript)
  - LLM latency (prompt → first token)
  - TTS latency (text → first audio chunk)
- Send to Datadog as before
- Update `PhoneCall` model columns if metric names change

#### 4D. Billing / usage tracking
- On call end, compute duration and send Stripe meter event
- Same filtering logic: skip test numbers, short calls, no-speech calls
- Replaces `_track_call_usage()` / `_should_track_call_usage()`

> 4A and 4B depend on 2B. 4C depends on 1A. 4D depends on 4B.

---

### Phase 5: Multi-Language (depends on 1A, 2A)

#### 5A. Language detection in agent
- Replace Vapi's triage squad with in-agent language detection
- On first customer utterance, detect language from STT transcript
- Route to appropriate voice config (switch TTS voice, adjust STT model)
- Simpler than Vapi squads — no separate assistant handoff, just swap configs mid-call

#### 5B. Mid-call voice/STT switching
- LiveKit Agents SDK supports updating STT/TTS mid-session
- When language is detected, hot-swap to the correct Deepgram model and Cartesia voice
- Play the `transfer_message` from the target language's VoiceConfig

> 5A → 5B is sequential.

---

### Phase 6: Error Handling & Fallbacks

#### 6A. LLM backend unavailable
- If PalAgent / chat completions endpoint fails, play a pre-recorded fallback message:
  "We're experiencing technical difficulties. Please hold while we connect you to a team member."
- Initiate automatic transfer to the default human contact

#### 6B. STT/TTS provider failure
- Configure fallback providers in agent code (e.g., backup Deepgram model, system TTS)
- LiveKit plugins support graceful degradation

#### 6C. Call quality monitoring
- Monitor jitter, packet loss via LiveKit room stats
- Detect poor audio quality and adjust (e.g., switch to lower-bandwidth codec)

---

### Phase 7: Phone Number Management (depends on 0B)

#### 7A. SIP trunk routing for existing numbers
- Keep all phone numbers in Twilio
- For each number to migrate: set `trunk_sid` on the Twilio number to point it at the SIP trunk connected to LiveKit
- The shared callee dispatch rule on LiveKit handles per-number routing automatically — no per-number LiveKit configuration needed
- To revert: clear `trunk_sid` on the Twilio number (calls resume going to Vapi webhook)

#### 7B. Number provisioning automation
- New LiveKit numbers: purchase on Twilio → set `trunk_sid` (done — no LiveKit API calls needed)
- New Vapi numbers: purchase on Twilio → import to Vapi (unchanged)
- Released LiveKit numbers: clear `trunk_sid` on Twilio number
- Released Vapi numbers: remove from Vapi (unchanged)
- No LiveKit SIP API calls needed in the number provisioning flow

#### 7C. Dual-routing during migration
- Voice provider per number is determined by checking Twilio's `trunk_sid`:
  - `trunk_sid` set → calls route to LiveKit via SIP
  - `trunk_sid` empty → calls route to Vapi via webhook (default)
- Enables per-number canary migration (not just per-account)
- Rollback is instant: clear `trunk_sid` to revert a number to Vapi
- `voice_provider` field on API request controls whether to set trunk or import to Vapi during provisioning

---

### Phase 8: DB Migration & Cleanup (depends on phases 1-7 working)

#### 8A. Schema migration
- Rename `vapi_control_url` → `call_control_id` (or similar generic name) on conversations
- Rename `call_id` to be provider-agnostic (already generic enough)
- Adjust `PhoneCall` latency columns if metric definitions changed
- Migration script

#### 8B. Remove Vapi code
- Delete `api/routes/integrations/vapi/` (entire directory)
- Delete `tools/vapi_tool/`
- Delete `services/voice_service/providers/vapi/`
- Remove from `tools/registry.py`, router includes
- Remove `vapi-server-sdk` from `pyproject.toml`
- Remove Vapi env vars
- Remove `agno` from `pyproject.toml` (framework fully replaced by pal-agents)

#### 8C. Remove assistant creation API
- Delete `POST /v1/integrations/vapi/assistants` — LiveKit agents are dynamic, no pre-creation needed

> 8A can happen anytime after new code is working. 8B only after zero projects remain on Vapi.

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
    ├──> 6A,6B,6C (Error handling)
    v
  5A,5B (Multi-language)
    │
    v
  7A,7B,7C (Phone number management)
    │
    v
  8A,8B,8C (Migration & cleanup)
```

---

## Critical Path

```
0A → 0B → 1A → 1B → parallel(2A, 2B, 4C) → parallel(3A, 4A, 4B, 5A) → 7A → 8B
```

The riskiest items:
1. **0B (SIP trunk setup)** — Validates that Twilio ↔ LiveKit telephony works at all
2. **3A (Call transfer)** — SIP REFER may not work with TLS; may need warm transfer fallback
3. **1B with Option B** — If you later move to in-process PalAgent, bridging its interface to LiveKit's LLM interface is the most complex piece

Recommend spiking on **0B + 1A** (get a basic call flowing through LiveKit with a hardcoded response) before committing to the full build.

---

## Tool Calling Migration Impact

### How Tool Calling Changes

| Concern | Vapi (current) | LiveKit (target) |
|---------|---------------|------------------|
| **Execution model** | Vapi sends `tool-calls` webhook → FastAPI handler executes tool → returns result to Vapi | **Option A:** Tools still execute via your API (called through chat completions). **Option B:** Tools execute in-process inside the LiveKit agent worker. |
| **Latency** | Network round-trip per tool call (Vapi → your API → Vapi) | **Option A:** Same as Vapi. **Option B:** Zero network overhead — in-process execution. |
| **Runtime context** | Tools run inside FastAPI request handler with DB session from webhook | **Option A:** Same as today. **Option B:** Tools run inside agent worker — must set up own DB sessions, HTTP clients, AWS Secrets Manager access. |

### Tools Requiring Changes

#### 1. VapiTool → LiveKitTransferTool (REWRITE)

**File**: `tools/vapi_tool/_implementation.py` (494 lines, 1 `@tool` method: `call_transfer`)

| What it does today | What changes |
|-------------------|-------------|
| Looks up contact destination by purpose | **Stays the same** — contacts table lookup |
| Fetches `vapi_control_url` from conversation record | **Remove** — no control URL concept in LiveKit |
| Falls back to Vapi API (`_get_control_url_from_vapi()`) | **Remove** — no Vapi API dependency |
| Builds Vapi transfer payload (`transferCall`, `<Dial>` for SIP) | **Replace** with LiveKit SIP transfer API |
| Sets caller ID in transfer payload | **Rethink** — caller ID configured on SIP trunk or outbound call |
| Validates `channel == VOICE` | **Stays the same** |

#### 2. Agent Service Raw Config (ADAPT WIRING)

**File**: `services/agent_service/_raw_config.py`

| Current code | Change |
|-------------|--------|
| `VOICE_ONLY_TOOLS = {"vapi_tool"}` | Swap to `{"livekit_transfer_tool"}` |
| `_populate_vapi_tool_args()` | Rename to `_populate_transfer_tool_args()` — same logic (builds transfer destinations from contacts table) |
| `if tool_name == "vapi_tool"` check in `_get_agent_tools()` | Update to `"livekit_transfer_tool"` |

#### 3. Tool Registry (SWAP REGISTRATION)

**File**: `tools/registry.py`

| Current | Change |
|---------|--------|
| `"vapi_tool": VapiTool` | Replace with `"livekit_transfer_tool": LiveKitTransferTool` |

### Tools Requiring Verification (no code changes)

| Tool | Why verify |
|------|-----------|
| `store_messaging_tool` | Uses `customer_phone` from metadata — verify SIP metadata provides same `+1XXXXXXXXXX` format |
| `catering_tool` | Fires EventBridge event post-creation — verify event still fires when call context comes from LiveKit instead of Vapi webhook |

### Tools Requiring Zero Changes (14 tools)

All business tools are channel-agnostic and call external APIs. No voice platform dependency:

`toast_tool` (6 methods), `adora_tool` (9), `adora_v2_tool` (4), `square_tool` (1), `olo_tool` (4), `resy_tool` (2), `resy_tool_with_reservation` (3), `minitable_tool` (5), `opentable_tool` (2), `yelp_tool` (7+), `yelp_credit_card_tool` (4), `yelp_no_credit_card_tool` (4), `menusifu_tool` (1)

### Runtime Context: Agent Worker Setup (Option B only)

All tools receive `ToolMetadata` (customer_phone, store_phone, session_id, agent_id, channel, timezone). Today this is populated in the FastAPI webhook handler from the Vapi `assistant-request` payload. On LiveKit with Option B, the agent worker entrypoint must construct the same metadata from SIP room participant attributes.

Additionally, the agent worker process must provide:
- **Async DB session factory** — for tools that persist data (e.g., `catering_tool`)
- **HTTP client pools** — for tools that call external APIs (all ordering/reservation tools)
- **AWS Secrets Manager access** — for tools that fetch API credentials at runtime

No tool implementation code changes needed — it's infrastructure setup in the agent entrypoint.

---

## Migration Rollout Strategy

### Phase A: Spike & Validate (before committing)

1. Spike on **0B + 1A**: Get a basic call flowing through LiveKit with a hardcoded greeting
2. Spike on **3A**: Validate SIP transfer works with your Twilio trunk (REFER vs warm transfer)
3. Feature parity audit: confirm LiveKit supports endpointing tuning, background denoising, text replacements
4. Cost modeling: Vapi all-in per-minute vs LiveKit compute + Deepgram + Cartesia + Twilio SIP
5. **Go/no-go decision**

### Phase B: Dual-Stack for New Projects

1. Add `voice_provider` field to Project model (feature flag)
2. Build full LiveKit pipeline (Phases 0-5)
3. Keep Vapi running unchanged for existing projects
4. Internal dogfooding on test accounts for 2+ weeks
5. Parity dashboard: call success rate, P95 turn latency, transfer success rate
6. First external new project on LiveKit

### Phase C: Gradual Migration of Existing Customers

1. Canary: 1 low-risk account — flip `voice_provider` + update Twilio SIP routing
2. Monitor for 1 week
3. Expand: 3 → 10 → all accounts
4. Per-account rollback: flip `voice_provider` back to `"vapi"` + revert SIP routing (5-minute operation)
5. Decommission Vapi after zero accounts remain + 2 weeks buffer

---

## Technical Constraints

| Metric | Target |
|--------|--------|
| End-to-end turn latency | < 1000ms (P95) |
| First-response latency | < 1500ms |
| Transfer initiation | < 2000ms |
| Concurrent calls | 50-100 initially, 500+ within 6 months |
| Daily call volume | 1,000-2,000 initially |
| Peak load | 3x average (lunch/dinner hours) |
| Call completion rate | ≥ 98% |
| Uptime SLA | ≥ 99.9% |

---

## What's Preserved

- Entire agent framework and business logic (pal-agents, PalAgent, Spec, RuntimeContext)
- All business tools (Adora, Toast, Square, Yelp, Resy, etc.)
- Database schema largely intact (enums, conversation model, business tables)
- Voice config concept (per-language voice/STT settings)
- Transfer destination logic (contacts table → phone numbers)
- STT provider (Deepgram) and TTS provider (Cartesia) — same providers, different integration method
- Phone numbers stay in Twilio — only routing changes
