# ADR-010: Pinecone + LlamaIndex for RAG

> **Status:** Accepted
> **Date:** 2024-01-01
> **Decision makers:** Kelvin

## Context

Restaurant clients need to query menus, FAQs, and integration-specific knowledge. Vector search is essential for semantic matching, and the platform needs production-grade RAG at scale.

## Decision

The platform uses Pinecone (vector database) and LlamaIndex (RAG framework) for knowledge retrieval. Pinecone handles vector storage and search, while LlamaIndex provides the RAG pipeline infrastructure.

## Alternatives Considered

- **pgvector only** — Sufficient for simple similarity search but lacks LlamaIndex's query engine capabilities for complex RAG
- **Weaviate / Qdrant** — Self-hosted vector DBs add operational burden; Pinecone is managed
- **Elasticsearch with vector search** — Heavier infrastructure; Pinecone + LlamaIndex is purpose-built for RAG

## Consequences

- **Easier:** Purpose-built for RAG at scale; mature ecosystems for both tools
- **Harder:** External dependencies with associated costs; need to manage vector store operations

## Evidence

- `agent/knowledge/` directory contains RAG implementations
- `pyproject.toml` dependencies include pinecone, llama-index
