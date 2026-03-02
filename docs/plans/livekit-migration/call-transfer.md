# LiveKit Call Transfer Analysis

## Overview

Call transfer is a core feature: the AI agent escalates a call to a human by transferring to a customer-provided phone number or SIP URI. Transfer destinations are arbitrary numbers configured per project in the contacts table.

---

## Current Transfer Flow (Vapi)

```
Customer says "transfer me to a manager"
  │
  ├── 1. LLM decides to call transfer tool
  │     Agent calls: call_transfer(purpose="complaint")
  │
  ├── 2. Look up destination from contacts table
  │     contacts table → role="complaint" → phone_number="+15559876543"
  │     Fallback: purpose not found → try "general" → project.transfer_phone_number (deprecated)
  │
  ├── 3. Get Vapi control URL
  │     conversation.vapi_control_url  (stored from status-update webhook)
  │     OR fallback: GET https://api.vapi.ai/call/{call_id} → monitor.controlUrl
  │
  ├── 4. Detect destination type
  │     Phone number: "+15559876543"
  │     SIP URI: "sip:+15559876543@provider.com"
  │
  ├── 5. Build caller ID
  │     show_agent_caller_id=True  → callerId = store_phone (business number)
  │     show_agent_caller_id=False → callerId = customer_phone (default)
  │
  ├── 6. POST to Vapi control URL
  │     Phone: {"type":"transfer","destination":{"type":"number","number":"+1...","callerId":"+1..."}}
  │     SIP:   {"type":"transfer","destination":{"type":"sip","sipUri":"sip:...","transferPlan":{"sipVerb":"dial"}}}
  │     Also includes: "content": "I'll transfer you to our team..."  (Vapi plays this via TTS)
  │
  └── 7. Vapi/Twilio executes the SIP transfer
```

### Key Files

| File | What it does |
|------|-------------|
| `tools/vapi_tool/_implementation.py` | 494 lines. `call_transfer()` method — channel validation, destination lookup, control URL fetch, payload build, HTTP POST |
| `services/agent_service/_raw_config.py` | `_populate_vapi_tool_args()` — builds `transfer_destinations` dict from contacts table |
| `db/tables/conversations.py` | `vapi_control_url` field — stored during Vapi `status-update` webhook |

### Destination Lookup Logic (reusable)

From `_raw_config.py:218-292`:

```python
# Primary: contacts table (per-project, customer-configured)
contacts = await contact_repo.batch_list_contacts(contact_ids)
transfer_destinations = {contact.role: contact.phone_number for contact in contacts}
# Result: {"general": "+15551234567", "complaint": "+15559876543", "catering": "+15550001111"}

# Secondary: deprecated project.transfer_phone_number fallback
```

From `VapiTool._get_destination_for_purpose()`:

```python
destination = transfer_destinations.get(purpose)        # Try exact match
if not destination:
    destination = transfer_destinations.get("general")  # Fallback to "general"
```

### Destination Types

Customers provide two types of destinations:

1. **Phone numbers** (E.164): `"+15559876543"` — caller transferred to PSTN number
2. **SIP URIs**: `"sip:+15559876543@sip.provider.com"` — caller transferred to SIP endpoint

The SIP case has a known gotcha (documented in code, lines 169-172):
> `<Refer>` only works when caller is on SIP leg, but our customers call from PSTN phones.
> `<Dial>` keeps Twilio in the call path and bridges PSTN caller to SIP endpoint.

### Caller ID Behavior

Controlled by `show_agent_caller_id` (per-project setting):

| Setting | What the human sees as caller ID | Use case |
|---------|----------------------------------|----------|
| `False` (default) | Customer's phone number | Human knows who's calling |
| `True` | Store/agent's phone number | Human knows it's from the AI system |

For SIP transfers, caller ID is **not set per-transfer** — it must be configured at the SIP trunk level. This was a Vapi-specific lesson: adding `callerId` to SIP destinations caused Vapi to ignore `transferPlan.sipVerb` and fall back to `<Refer>`, which breaks PSTN callers.

---

## LiveKit Transfer Flow

```
Customer says "transfer me to a manager"
  │
  ├── 1. LLM decides to call transfer tool              ← SAME
  │     Agent calls: call_transfer(purpose="complaint")
  │
  ├── 2. Look up destination from contacts table         ← SAME
  │     contacts table → role="complaint" → phone_number="+15559876543"
  │
  ├── 3. Get room + participant info                     ← NEW (replaces control URL)
  │     From agent context: room_name, sip_participant_identity
  │     (available inside the agent worker — no DB lookup or API call needed)
  │
  ├── 4. Detect destination type                         ← SAME
  │     Phone number vs SIP URI
  │
  ├── 5. Play transfer message via TTS                   ← NEW
  │     session.generate_reply("I'll transfer you to our team...")
  │     (In Vapi this was in the payload "content" field; in LiveKit you play it explicitly)
  │
  ├── 6. Execute transfer via LiveKit SIP API            ← NEW (replaces POST to control URL)
  │
  │     Option 1 — SIP REFER (cold transfer):
  │       lk_api.sip.transfer_sip_participant(
  │           room_name=room_name,
  │           participant_identity=sip_participant_identity,
  │           transfer_to="tel:+15559876543",
  │       )
  │
  │     Option 2 — Warm transfer (bridge):
  │       lk_api.sip.create_sip_participant(
  │           room_name=room_name,
  │           sip_trunk_id=outbound_trunk_id,
  │           sip_call_to="tel:+15559876543",
  │           participant_identity="transfer-target",
  │       )
  │       # Then remove original agent from room
  │
  └── 7. LiveKit/Twilio executes the SIP transfer
```

---

## What Stays the Same

| Component | Code Location | Change Required |
|-----------|--------------|-----------------|
| Destination lookup by purpose | `VapiTool._get_destination_for_purpose()` | Copy as-is to new tool |
| Contacts table integration | `_raw_config.py:_populate_vapi_tool_args()` | Rename only |
| Transfer destinations dict | `{"general": "+1...", "complaint": "+1..."}` | Same data structure |
| Channel validation | `if channel != "voice": return error` | Copy as-is |
| Transfer message text | `project.transfer_message` | Same source, different playback mechanism |
| Phone number vs SIP detection | `destination.lower().startswith("sip:")` | Copy as-is |

## What Changes

| Component | Vapi | LiveKit |
|-----------|------|---------|
| Transfer target reference | `vapi_control_url` (stored in DB from webhook) | `room_name` + `participant_identity` (available in agent context) |
| Transfer API | POST to Vapi control URL | `lk_api.sip.transfer_sip_participant()` or `create_sip_participant()` |
| Transfer message playback | Part of transfer payload (`"content"` field) | Explicit TTS playback before transfer (`session.generate_reply()`) |
| Caller ID control | Per-transfer in payload (`"callerId"` field) | **Needs investigation** — may be trunk-level only |
| Error "call not active" | HTTP 400 from Vapi control URL | LiveKit API error (different exception type) |
| DB dependency for transfer | Needs `conversation.vapi_control_url` or Vapi API call | No DB lookup needed — room info available in agent context |

---

## Open Questions / Risks

### 1. Caller ID Control (HIGH RISK)

**Current behavior:** Per-transfer caller ID set in the Vapi transfer payload. Customer's phone or store's phone shown to the transfer recipient.

**LiveKit concern:** SIP REFER does not typically allow per-transfer caller ID. The outgoing caller ID is determined by:
- The SIP trunk's outbound caller ID configuration
- The original caller's number (passthrough)

**Impact:** If LiveKit can't set caller ID per-transfer, customers using `show_agent_caller_id=True` will see different behavior. Need to confirm with LiveKit whether `transfer_sip_participant` supports a caller ID parameter.

**Workaround if not supported:** Use warm transfer (outbound SIP call) where caller ID can be set on the outbound leg via the SIP trunk configuration.

### 2. PSTN-to-SIP Transfers (HIGH RISK)

**Current behavior:** When transferring a PSTN caller to a SIP URI, Vapi uses `<Dial>` (not `<Refer>`) to keep Twilio in the call path. This was a production fix — `<Refer>` doesn't work for PSTN-to-SIP.

**LiveKit concern:** `transfer_sip_participant` sends a SIP REFER. If the caller is on PSTN and the destination is a SIP URI, REFER may fail (same issue you had with Vapi).

**Impact:** Customers with SIP URI transfer destinations (not just phone numbers) may have broken transfers.

**Workaround:** Use warm transfer for SIP destinations — create an outbound SIP call to the SIP URI and bridge it into the room, then remove the agent.

### 3. SIP-over-TLS Configuration (LOW RISK)

**Correction:** SIP REFER cold transfers are supported over SIP-over-TLS. The original claim that REFER does not work over TLS was incorrect.

**Twilio requirement:** For Twilio SIP trunks, the trunk must have **"Enable PSTN Transfer"** enabled for REFER-based transfers to succeed. The trunk should use TLS via port 5061 or by setting `SIP_TRANSPORT_TLS` in the trunk configuration.

**Action:** Ensure your Twilio SIP trunk has "Enable PSTN Transfer" enabled and is configured for TLS (port 5061 / `SIP_TRANSPORT_TLS`).

### 4. Transfer Reliability

**Current behavior:** Vapi returns HTTP 400 "Not Active" if call already ended. VapiTool handles this gracefully.

**LiveKit concern:** Different error semantics. Need to identify LiveKit's equivalent error when transferring a disconnected participant and handle it the same way.

---

## Proposed LiveKitTransferTool Structure

```
tools/livekit_transfer_tool/
├── __init__.py                    # Export LiveKitTransferTool
├── _implementation.py             # Tool class
└── classes.py                     # Pydantic models (if needed)
```

### Constructor

```python
class LiveKitTransferTool(Toolkit):
    def __init__(
        self,
        tool_metadata: ToolMetadata,
        transfer_destinations: dict[str, str],     # SAME — from contacts table
        transfer_message: str | None = None,        # SAME — from project
        show_agent_caller_id: bool = False,         # SAME — per-project setting
        lk_api: LiveKitAPI = None,                  # NEW — LiveKit API client
        room_name: str = None,                      # NEW — from agent context
        participant_identity: str = None,           # NEW — SIP participant identity
        agent_session: AgentSession = None,         # NEW — for TTS playback
        outbound_trunk_id: str = None,              # NEW — for warm transfers
    ):
```

### Method: `call_transfer(purpose)`

```python
async def call_transfer(self, purpose: str = "general") -> str:
    # 1. Validate voice channel                              ← SAME
    # 2. Look up destination by purpose                      ← SAME (_get_destination_for_purpose)
    # 3. Play transfer message via agent session TTS         ← NEW
    #    await self.agent_session.generate_reply(self.transfer_message)
    # 4. Detect phone vs SIP                                 ← SAME
    # 5. Execute transfer                                    ← NEW
    #    Phone + non-TLS trunk → SIP REFER (transfer_sip_participant)
    #    Phone + TLS trunk    → Warm transfer (create_sip_participant)
    #    SIP URI              → Warm transfer (create_sip_participant)
    # 6. Handle errors                                       ← ADAPTED
```

---

## Wiring Changes in _raw_config.py

```python
# Before
VOICE_ONLY_TOOLS = {"vapi_tool"}

async def _populate_vapi_tool_args(self, tool_args, session):
    # ... contacts table lookup → transfer_destinations dict
    return updated_args

# After
VOICE_ONLY_TOOLS = {"livekit_transfer_tool"}

async def _populate_transfer_tool_args(self, tool_args, session):
    # ... SAME contacts table lookup → transfer_destinations dict
    # ... ADD: lk_api, room_name, participant_identity from agent context
    return updated_args
```

---

## Spike Checklist (Phase A)

Before building the full tool, validate these in a test call:

- [ ] **Basic phone transfer:** Transfer PSTN caller to a phone number via `transfer_sip_participant`
- [ ] **SIP URI transfer:** Transfer PSTN caller to a SIP URI — does REFER work or do you need warm transfer?
- [ ] **Caller ID on phone transfer:** Can you control what caller ID the transfer recipient sees?
- [ ] **TLS trunk compatibility:** Does REFER work with your Twilio SIP trunk's TLS setting?
- [ ] **Warm transfer fallback:** If REFER fails, does `create_sip_participant` (bridge) work for both phone and SIP destinations?
- [ ] **Error handling:** What error does LiveKit return when transferring a disconnected participant?

---

## Effort Estimate

| Component | Effort | Notes |
|-----------|--------|-------|
| Destination lookup | **Zero** | Copy `_get_destination_for_purpose()` as-is |
| Contact table wiring | **Rename** | `_populate_vapi_tool_args` → `_populate_transfer_tool_args` |
| Channel validation | **Zero** | Copy as-is |
| Transfer message playback | **Small** | One line: `session.generate_reply(msg)` |
| Phone transfer (REFER) | **Small** | One API call to LiveKit |
| SIP URI transfer (warm) | **Medium** | Create outbound call + bridge logic |
| Caller ID control | **Medium-High** | Depends on LiveKit capabilities; may need trunk config per project |
| Error handling | **Small** | Map LiveKit errors to same user-facing messages |
| Registry + raw_config wiring | **Small** | String replacements |
