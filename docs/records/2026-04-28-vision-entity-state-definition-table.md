# Vision Entity State Definition Table

**Date**: 2026-04-28
**Author**: Bruce Jin
**Status**: Implemented

## Context

Each vision entity type (e.g., table, employee) needs a set of possible states (e.g., empty/occupied, idle/working). States are per-entity-type so each type can have its own state vocabulary with display metadata for the UI.

## Decision

Add a new `vision_entity_state_definition` table for per-entity-type state definitions.

### New Table: `vision_entity_state_definition`

- `id` (UUID) — primary key
- `entity_type_id` (UUID, indexed) — references `vision_entity_type.id`
- `name` (VARCHAR 100) — machine name (e.g. `"dirty"`, `"occupied"`)
- `display_name` (VARCHAR 255) — human-readable label (e.g. `"Needs cleaning"`)
- `color` (VARCHAR 7, nullable) — hex color for UI badge (e.g. `"#F59E0B"`)
- `sort_order` (INT, default 0) — display ordering
- `is_default` (BOOLEAN, default false) — whether this is the default state for the type
- `created_at` (TIMESTAMPTZ, server default now())

### Constraints

- Unique constraint on `(entity_type_id, name)` — one state name per entity type

## Consequences

### Benefits
- Per-entity-type state vocabulary allows customization per entity kind
- `color` and `sort_order` enable rich UI presentation
- `is_default` flag simplifies initial state assignment

### Tradeoffs
- No foreign key to `vision_entity_type` (follows project convention of indexed columns without FK constraints)

## Related
- `db/tables/vision_entity_state_definitions.py` — SQLAlchemy model
- `db/migrations/versions/2026-04-28_278221f29de8_add_vision_entity_state_definition_table.py` — Alembic migration
- `docs/records/2026-04-28-vision-entity-type-table.md` — parent entity type table
