# LiveKit Migration — Business Overview

## Why We're Migrating

We're moving from Vapi (a managed voice AI platform) to LiveKit (open-source voice infrastructure). The key motivations:

- **Control:** Vapi owns the entire call pipeline as a black box. LiveKit gives us full control over the agent process, STT, LLM, and TTS pipeline.
- **Cost:** Vapi charges an all-in per-minute rate on top of underlying provider costs. With LiveKit, we pay only for compute + Deepgram + Cartesia + Twilio SIP directly.
- **Flexibility:** LiveKit lets us customize every part of the call experience — endpointing, interruption handling, mid-call voice switching — without waiting on Vapi feature requests.
- **Latency:** With LiveKit, we can run the LLM in-process (no network round-trip), reducing turn latency.

---

## What Changes for Customers

### Nothing changes externally

- **Same phone numbers** — numbers stay in Twilio, only internal routing changes
- **Same voice quality** — same STT (Deepgram) and TTS (Cartesia) providers
- **Same AI behavior** — same agent framework (pal-agents), same business tools (Adora, Toast, Square, etc.)
- **Same transfer experience** — call transfer to human contacts works the same way
- **Same multi-language support** — language detection and voice switching preserved

### What changes internally

- **Call routing:** Twilio → LiveKit (instead of Twilio → Vapi)
- **Agent execution:** Long-lived agent process (instead of webhook round-trips)
- **Call transfer:** LiveKit SIP API (instead of Vapi control URL)
- **Metrics collection:** Self-instrumented (instead of Vapi's end-of-call report)

---

## Migration Strategy

### Phase A: Spike & Validate

Before committing to the full migration:

1. Get a basic call flowing through LiveKit with a hardcoded greeting
2. Validate SIP call transfer works with our Twilio trunk
3. Confirm feature parity: endpointing tuning, background denoising, text replacements
4. Cost modeling: compare Vapi all-in rate vs LiveKit compute + provider costs
5. **Go/no-go decision**

### Phase B: Dual-Stack for New Projects

1. Add a `voice_provider` feature flag per project (`"vapi"` or `"livekit"`)
2. Build the full LiveKit pipeline while Vapi continues running for existing projects
3. Internal dogfooding on test accounts for 2+ weeks
4. Parity dashboard comparing: call success rate, P95 turn latency, transfer success rate
5. First external new project onboarded to LiveKit

### Phase C: Gradual Migration of Existing Customers

1. **Canary:** 1 low-risk account — flip `voice_provider` + update SIP routing
2. Monitor for 1 week
3. **Expand:** 3 → 10 → all accounts
4. **Per-account rollback:** flip `voice_provider` back to `"vapi"` + revert SIP routing (5-minute operation)
5. **Decommission Vapi** after zero accounts remain + 2 weeks buffer

---

## Risk Assessment

### High Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Caller ID on transfers** | Transfer recipients may not see the expected caller ID. LiveKit SIP REFER doesn't support per-transfer caller ID like Vapi did. | Use warm transfer (outbound SIP call) where caller ID is set on the trunk. Validate in spike phase. |
| **PSTN-to-SIP transfers** | Customers with SIP URI transfer destinations may have broken transfers. SIP REFER doesn't work for PSTN-to-SIP (same issue we already fixed in Vapi). | Use warm transfer for SIP destinations — bridge an outbound SIP call into the room. |
| **SIP-over-TLS** | If our Twilio SIP trunk uses TLS, cold transfer (SIP REFER) won't work at all. | Check trunk config. If TLS required, use warm transfer for everything. |

### Medium Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Metrics gap** | Vapi provides latency breakdown in end-of-call report. LiveKit doesn't — we must self-instrument. | Build instrumentation into the agent pipeline. Validate against Vapi baselines before migration. |
| **Multi-language** | Vapi uses "squads" for language routing. LiveKit has no squad concept. | Implement in-agent language detection with mid-call STT/TTS switching. Simpler architecture but needs validation. |

### Low Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Business tools** | 14 business tools (Adora, Toast, Square, etc.) are channel-agnostic. | Zero code changes needed. Verify metadata format matches. |
| **Phone numbers** | Numbers stay in Twilio. | Only routing changes — no number porting. |

---

## What's Preserved

| Component | Status |
|-----------|--------|
| Agent framework (pal-agents) | No change — provider-agnostic |
| All business tools (14 tools) | No change — channel-agnostic |
| Database schema | Largely intact — minor column renames |
| Voice configs (per-language) | Same concept, same providers |
| Transfer destinations (contacts table) | Same data, same lookup logic |
| STT provider (Deepgram) | Same provider, different integration |
| TTS provider (Cartesia) | Same provider, different integration |
| Phone numbers (Twilio) | Same numbers, only routing changes |

---

## Success Criteria

| Metric | Target |
|--------|--------|
| End-to-end turn latency | < 1000ms (P95) |
| First-response latency | < 1500ms |
| Transfer initiation | < 2000ms |
| Call completion rate | ≥ 98% |
| Uptime SLA | ≥ 99.9% |

### Capacity Targets

| Metric | Target |
|--------|--------|
| Concurrent calls | 50–100 initially, 500+ within 6 months |
| Daily call volume | 1,000–2,000 initially |
| Peak load | 3x average (lunch/dinner hours) |

---

## Rollback Plan

At every stage of the migration, rollback is a 5-minute operation:

1. Flip project's `voice_provider` flag back to `"vapi"`
2. Revert Twilio SIP trunk routing to point back to Vapi
3. No data migration needed — both systems share the same DB

Vapi infrastructure stays running until 100% of accounts are migrated + 2 weeks buffer.
