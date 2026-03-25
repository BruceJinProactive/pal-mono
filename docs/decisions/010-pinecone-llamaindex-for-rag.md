# ADR-010: Pinecone + LlamaIndex for RAG

> **Status:** Accepted
> **Date:** 2024-01-01
> **Decision makers:** Kelvin, Jeff C, Shuo

## Context

The platform needed a practical retrieval layer for menus and other knowledge without overloading the model context window with full menu data. This was especially important for the Agno v2 ordering flow, where tools needed to find likely item matches and recover the full menu information and item IDs behind them.

Pinecone and LlamaIndex were chosen as an easy external datastore and retrieval stack. The goal was to give ordering and knowledge flows a queryable menu/knowledge layer without forcing the model to carry the entire menu in-context on every run.

## Decision

The platform uses Pinecone and LlamaIndex as the retrieval stack for menu and knowledge lookup.

Pinecone is the managed vector datastore, and LlamaIndex is the query/retrieval layer used to support RAG-style access to menus and related knowledge, including item lookup for legacy ordering flows.

## Alternatives Considered

- **Put the full menu into the model context** — Rejected because large menus would consume too much context and still not provide a clean lookup mechanism for item IDs and full item records.
- **Use a different vector database or retrieval stack** — Rejected because Pinecone and LlamaIndex were a practical managed/default choice for getting menu and knowledge retrieval working quickly.

## Consequences

- **Easier:** Ordering and knowledge flows can query menu and knowledge data without carrying the full dataset in the prompt, and legacy ordering tools can recover full item information and IDs through retrieval.
- **Harder:** The platform takes on extra dependencies and another failure point in the ordering/knowledge path.

## Evidence

- `agent/knowledge/` contains the legacy LlamaIndex + Pinecone retrieval path.
- `agent/tool/internal/query_knowledge_tool/` shows the tool-facing query surface used with that knowledge layer.
- `services/knowledge_service/` contains the indexing paths that populate Pinecone-backed knowledge stores.
