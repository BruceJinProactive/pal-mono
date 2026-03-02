# ADR-014: Dual Vector Storage

> **Status:** Accepted
> **Date:** 2024-01-01
> **Decision makers:** Kelvin

## Context

The platform has different vector storage needs: local/simple operations (embedded pgvector in PostgreSQL) and production-scale RAG knowledge bases (Pinecone). Different use cases call for different tools.

## Decision

The platform uses both PostgreSQL with pgvector (for local/simple vector operations) and Pinecone (for production-scale RAG knowledge bases). Each is used for the appropriate use case.

## Alternatives Considered

- **pgvector only** — Simpler but lacks Pinecone's managed scaling and LlamaIndex integration depth
- **Pinecone only** — Would require Pinecone for all vector ops including simple ones better suited to pgvector
- **Single managed vector DB (Pinecone for everything)** — Cost overhead for operations that don't need Pinecone's scale

## Consequences

- **Easier:** Right tool for each job; pgvector for simple use cases, Pinecone for scale
- **Harder:** Two vector stores to maintain and understand; data migration between them if needed
