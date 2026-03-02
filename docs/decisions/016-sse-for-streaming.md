# ADR-016: SSE for Streaming

> **Status:** Accepted
> **Date:** 2024-01-01
> **Decision makers:** Kelvin

## Context

The chat interface needs to stream agent responses to clients. WebSockets provide bidirectional communication but add complexity. For unidirectional streaming (server to client), SSE is simpler and has better proxy/CDN compatibility.

## Decision

The platform uses Server-Sent Events (SSE) for chat streaming instead of WebSockets.

## Alternatives Considered

- **WebSocket** — Bidirectional communication not needed for chat streaming; more complex infrastructure (load balancer config, connection management)
- **Long polling** — Higher latency, more server load than SSE
- **gRPC streaming** — Client compatibility issues; SSE works natively in browsers

## Consequences

- **Easier:** Simpler infrastructure; easier client implementation; better proxy/CDN compatibility
- **Harder:** No bidirectional communication (not needed for this use case)
