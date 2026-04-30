# Vision Entity Type API

**Date**: 2026-04-29
**Author**: Bruce Jin
**Status**: Implemented

## Context

The `vision_entity_type` table was added on 2026-04-28. This change adds the full CRUD API, service layer, repository, and tests so entity types can be managed via REST.

## What Shipped

### API Endpoints

Base path: `POST/GET/PATCH/DELETE /v1/operation/accounts/{account_id}/entity-types`

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| POST | `/` | 201 | Create entity type |
| GET | `/` | 200 | List (optional `?is_active=true`) |
| GET | `/{entity_type_id}` | 200 | Get by ID |
| PATCH | `/{entity_type_id}` | 200 | Update |
| DELETE | `/{entity_type_id}` | 204 | Delete |

All require `authenticate_user`.

### Layers Added

- **Repository**: `db/repositories/vision_entity_type_repository.py` — async CRUD with `[Vision Entity] DB error ...` logging
- **Service**: `services/vision_entity_service/_implementation.py` — business logic (unique name validation, account scoping)
- **API routes**: `api/routes/operation/_vision_entities.py` — thin handlers with `@traced()` OTel spans
- **Schemas**: `api/schemas/operations/vision_entity.py` — Pydantic V2 request/response models

### Observability

- OTel traces: `vision_entity.{create,get,list,update,delete}_entity_type` → Tempo
- Structured logs: `[Vision Entity]` prefix at INFO (mutations) and ERROR (failures) → Loki
- All error logs include `exc_info=True` and structured `extra` fields

### Tests

16 unit tests in `tests/services/vision_entity_service/test_entity_type.py`.

## Related

- `docs/records/2026-04-28-vision-entity-type-table.md` — table definition
- `services/vision_entity_service/README.md` — full API + observability reference
