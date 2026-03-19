# Square Integration (OAuth + Menu Indexing)

> **Date:** 2025-07-14

## Summary

Implemented Square POS integration with OAuth token management, menu data fetching, and knowledge base indexing. Enables AI agents to answer questions about Square-managed restaurant menus.

## What Was Built

### OAuth + Token Refresh

- `api/routes/integrations/square/_implementation.py` — OAuth flow endpoints
- `api/routes/integrations/square/_util.py` — `refresh_square_token()`, encryption helpers, client ID/secret management
- Token refresh stores refreshed tokens back to the database with encrypted storage

### Menu Knowledge Pipeline

- `services/knowledge_service/square/_implementation.py` — Square menu processing orchestrator
- `services/knowledge_service/square/_client.py` — Square API client for fetching catalog/menu data
- `services/knowledge_service/square/_indexer.py` — Indexes Square menu items into Pinecone vector store
- `tools/` — Square listing/menu tools for agent use

### Migration Timeline

1. **June 18, 2025**: Square tool architecture initialized (#1410-1414)
2. **July 9, 2025**: Square OAuth implementation (#1567)
3. **July 14, 2025**: Refresh token storage added (#1605)
4. **Nov 13, 2025**: Architecture documentation added (#2717)

## Key Files

| Component | File |
|-----------|------|
| OAuth + token refresh | `api/routes/integrations/square/_util.py`, `_implementation.py` |
| Knowledge pipeline | `services/knowledge_service/square/` (3 modules) |
| State doc | `docs/state/business-updater/square-token-refresher.md` |

## Origin

Plan: `.claude/docs/business_updater/SQUARE_TOKEN_REFRESHER.md` (now archived)
