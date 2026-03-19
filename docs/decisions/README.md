# Architecture Decision Records

ADRs in this directory are prescriptive. They define architectural rules and direction the codebase is expected to follow. They are not historical write-ups of whatever the code happens to do today.

For authoring rules and a template, see [USERGUIDE.md](USERGUIDE.md).

**Status values:** `Accepted` | `Superseded` | `Deprecated`

When a decision changes, don't delete the old ADR. Mark the old ADR `Superseded by ADR-{NNN}` and create a new one.

## Index

| ADR | Decision | Status | Date |
| ----- | ---------- | -------- | ------ |
| [001](001-monolith-over-microservices.md) | Monolith with event-driven components | Accepted | 2024-01-01 |
| [002](002-layered-architecture.md) | Layered architecture (API → Service → DB) | Accepted | 2024-01-01 |
| [003](003-repository-pattern.md) | Repository pattern for all data access | Accepted | 2024-01-01 |
| [004](004-no-foreign-key-constraints.md) | No foreign key constraints | Accepted | 2024-01-01 |
| [005](005-tools-bypass-service-layer.md) | Tools bypass service layer | Accepted | 2024-01-01 |
| [007](007-agno-to-pal-agents-migration.md) | Agno → pal-agents migration | Accepted | 2026-02-01 |
| [008](008-multi-provider-llm.md) | Multi-provider LLM support | Accepted | 2025-07-01 |
| [009](009-mem0-for-memory.md) | mem0ai for conversational memory | Accepted | 2024-01-01 |
| [010](010-pinecone-llamaindex-for-rag.md) | Pinecone + LlamaIndex for RAG | Accepted | 2024-01-01 |
| [011](011-bedrock-guardrails.md) | Bedrock guardrails for content safety | Deprecated | 2024-01-01 |
| [012](012-uv-package-manager.md) | uv as package manager | Accepted | 2024-06-01 |
| [013](013-datadog-observability.md) | Datadog for all observability | Accepted | 2024-01-01 |
| [014](014-dual-vector-storage.md) | PostgreSQL pgvector AND Pinecone | Accepted | 2024-01-01 |
| [015](015-cognito-plus-custom-rbac.md) | Cognito + custom RBAC | Accepted | 2025-11-01 |
| [016](016-sse-for-streaming.md) | SSE for streaming (not WebSocket) | Accepted | 2024-01-01 |
| [017](017-no-orm-relationships.md) | No ORM relationships | Accepted | 2024-01-01 |
| [018](018-vapi-to-livekit-migration.md) | Migrate from VAPI to LiveKit | Accepted | 2026-02-18 |
| [019](019-streaming-session-ownership.md) | Streaming endpoints must own their DB session | Accepted | 2026-03-18 |

## Notes

- Numbering is append-only. Gaps are allowed if an ADR was abandoned before merge.
- ADRs should be short, directive, and testable against future changes.
- Detailed postmortems and implementation history belong in `docs/records/`, not here.
