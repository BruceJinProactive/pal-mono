# ADR-018: Migrate from VAPI to LiveKit

> **Status:** Accepted
> **Date:** 2026-02-18
> **Decision makers:** Jacob Wang

## Context

The platform started with VAPI as the managed voice solution (webhook-driven). As the product matured, several limitations became clear:

- **Latency**: VAPI uses WebSockets for bi-directional audio transport (~300ms reported latency), which is adequate for simple two-party calls but suboptimal for real-time conversational AI where every millisecond matters. LiveKit's WebRTC SFU transport provides significantly lower and more consistent latency, critical for natural turn-taking in restaurant ordering scenarios.
- **Observability**: VAPI is a closed-source black box — when calls degrade or fail, there is no way to inspect the internal voice pipeline (VAD decisions, STT/TTS timing, transport metrics). Debugging production issues requires opening support tickets rather than inspecting logs and metrics directly. LiveKit exposes the full pipeline with built-in telemetry and metrics, enabling self-service debugging and proactive monitoring.
- **Reliability**: As a managed platform, VAPI is a single point of failure with no self-hosting fallback. Outages or degradation on VAPI's infrastructure directly impact all voice calls with no mitigation path. LiveKit's worker-based model allows self-hosted deployment, redundancy, and direct control over uptime and failover.
- **Cost** (secondary): VAPI charges $0.05/min platform fee on top of provider costs (STT, TTS, LLM, telephony), bringing total per-minute costs to $0.13-$0.35/min. At scale this adds up, though cost alone would not justify migration.
- **Control**: The voice pipeline (VAD, turn-taking, STT/TTS routing) cannot be customized beyond VAPI's configuration surface. Custom logic for interruption handling, barge-in behavior, or dynamic provider switching is limited.

LiveKit addresses all of these concerns as an open-source (Apache 2.0) voice/video framework with a worker-based agent model, WebRTC SFU transport, full pipeline observability, and self-hosted deployment options.

## Decision

The platform will fully migrate from VAPI to LiveKit. VAPI will be deprecated and removed once migration is complete.

## Alternatives Considered

- **VAPI only (stay on managed platform)** — Simpler to operate, but higher cost at scale ($0.13-$0.35/min vs $0.03-$0.15/min with LiveKit), closed-source with limited customization, WebSocket transport with higher latency than WebRTC, no self-hosting path, and no video support.
- **Pipecat (open-source framework)** — Similar open-source philosophy to LiveKit with composable pipelines, but smaller ecosystem and community. LiveKit has 17.3K GitHub stars (server) + 9.5K (agents) and a $100M Series C, providing stronger long-term viability.
- **Build custom voice infrastructure** — Maximum control but massive engineering investment. LiveKit provides the primitives (rooms, participants, tracks, SFU transport) that would take months to build from scratch.
- **Retell AI** — More transparent pricing than VAPI ($0.07/min + providers), but still a closed-source managed platform with the same vendor lock-in and customization limitations.

## Consequences

- **Easier:** Lower latency via WebRTC SFU transport for more natural conversations; full pipeline observability (metrics, logs, tracing) for self-service debugging; self-hosted deployment for reliability and failover control; full control over voice pipeline (VAD, turn-taking, STT/TTS provider selection); lower cost at scale as a secondary benefit; open-source framework with no vendor lock-in
- **Harder:** LiveKit requires more engineering effort to set up and maintain (it's a framework, not a turnkey product); telephony integration requires external SIP trunk provider (Twilio/Telnyx) rather than VAPI's built-in phone numbers; no built-in visual workflow editor or call analysis features — these must be built in-house; two voice codepaths to maintain during the migration period

## Research

Key sources consulted (February 2025):

| Dimension | VAPI | LiveKit |
| --- | --- | --- |
| **Architecture** | Managed/webhook-driven, closed-source | Open-source framework, worker-based agents |
| **Transport** | WebSockets | WebRTC via Selective Forwarding Units (SFUs) |
| **Platform cost** | $0.05/min | $0.004/min audio (Cloud) |
| **Total cost at 10K min** | $1,500-$3,500 | $300-$1,500 |
| **Self-hosting** | No | Yes (agents); Cloud required for SFU transport |
| **Video support** | No (audio-only codecs) | Yes (H.264, VP9) |
| **Turn-taking** | Smart endpointing (limited config) | Full VAD framework, configurable interruption handling |
| **Telephony** | Built-in phone numbers | SIP trunks via external provider (Twilio, Telnyx) |
| **Provider flexibility** | BYOK for STT/TTS/LLM | Direct integration, any provider |
| **Community** | Closed-source, proprietary | 17.3K + 9.5K GitHub stars, $100M Series C |
