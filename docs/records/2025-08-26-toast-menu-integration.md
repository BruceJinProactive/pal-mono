# Toast Menu Integration (Webhook + Knowledge Pipeline)

> **Date:** 2025-08-26

## Summary

Implemented Toast POS integration with webhook-driven menu updates and a knowledge base indexing pipeline. When Toast fires menu_updated webhooks, the system fetches the latest menu, processes it, and indexes it into Pinecone so AI agents have current menu knowledge.

## What Was Built

### Webhook Integration

- `api/routes/integrations/toast/_implementation.py` — Toast webhook handlers (menu_updated, ordering_schedule)
- `api/routes/integrations/toast/schema.py` — Toast webhook payload schemas

### Menu Processing Pipeline

- `services/knowledge_service/toast/_implementation.py` — `ToastMenuProcessor` orchestrator
- `services/knowledge_service/toast/_client.py` — Toast API client
- `services/knowledge_service/toast/_utils.py` — Menu parsing utilities (modifier groups, dining options)
- `services/knowledge_service/toast/_indexer.py` — Pinecone indexing for menu items

### Key Features

- Accepts `menu_last_updated` parameter to skip processing if menu hasn't changed
- Filters out third-party delivery menus (#2430)
- Supports dining options upload (#2413)
- Handles nested modifier structures (#2549)

### Migration Timeline

1. **April 8-22, 2025**: Toast API tools and menu parser (#933-998)
2. **Aug 18-19, 2025**: Webhook handlers for menu_updated and ordering_schedule (#2022, #2029)
3. **Aug 26, 2025**: Toast menu updater pipeline (#2096, #2105)
4. **Oct 3-24, 2025**: Dining options, delivery menu filtering, modifier fixes (#2413, #2430, #2549)

## Key Files

| Component | File |
|-----------|------|
| Webhooks | `api/routes/integrations/toast/_implementation.py`, `schema.py` |
| Knowledge pipeline | `services/knowledge_service/toast/` (4 modules) |
| State doc | `docs/state/business-updater/toast-menu-updater.md` |

## Origin

Plan: `.claude/docs/business_updater/TOAST_MENU_UPDATER.md` (now archived)
