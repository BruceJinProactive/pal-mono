# Vision Entity Table

**Date**: 2026-04-28
**Author**: Bruce Jin
**Status**: Implemented

## Context

The vision system needs concrete entity instances at a location (e.g., "Table 1", "John", "Tray A") that tie an entity type to a project and track its current state. These are the runtime objects that cameras observe and state transitions apply to.

## Decision

Add a new `vision_entity` table for per-project entity instances.

### New Table: `vision_entity`

SQLAlchemy model for vision entity instances:
- `id` (UUID) — primary key
- `project_id` (UUID, indexed) — owning project/location
- `entity_type_id` (UUID, indexed) — references `vision_entity_type`
- `name` (VARCHAR 255) — instance name (e.g. `"Table 1"`, `"John"`)
- `current_state_id` (UUID, nullable, indexed) — references `vision_entity_state_definition`
- `current_state_since` (TIMESTAMPTZ, nullable) — when current state started
- `entity_metadata` (JSONB, default `{}`) — Python attr name; maps to `metadata` DB column (renamed to avoid SQLAlchemy `DeclarativeBase.metadata` clash)
- `is_active` (BOOLEAN, default true) — soft-delete flag
- `created_at` (TIMESTAMPTZ, server default now())
- `updated_at` (TIMESTAMPTZ, server default now(), on update now())

### Constraints

- Unique constraint on `(project_id, entity_type_id, name)` — one entity per name per type per project

## Consequences

### Benefits
- Project-scoped entities allow per-location tracking
- Current state pointer enables efficient state queries without scanning history
- JSONB metadata allows flexible per-entity attributes

### Tradeoffs
- No foreign keys to `projects`, `vision_entity_type`, or `vision_entity_state_definition` (follows project convention of indexed columns without FK constraints)

## Related
- `db/tables/vision_entities.py` — SQLAlchemy model
- `db/migrations/versions/2026-04-28_5302550f9bc6_add_vision_entity_table.py` — Alembic migration
- `docs/records/2026-04-28-vision-entity-type-table.md` — entity type table
- `docs/records/2026-04-28-vision-entity-state-definition-table.md` — state definition table
