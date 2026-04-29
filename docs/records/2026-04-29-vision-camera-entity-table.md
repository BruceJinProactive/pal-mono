# Vision Camera Entity Table

**Date**: 2026-04-29
**Author**: Bruce Jin
**Status**: Implemented

## Context

The vision system needs a many-to-many join between camera configurations and entities so each camera knows which entities to monitor, with an optional region-of-interest hint for the LLM.

## Decision

Add a new `vision_camera_entity` join table linking `vision_camera_configuration` to `vision_entity`.

### New Table: `vision_camera_entity`

SQLAlchemy model for camera-to-entity assignments:
- `id` (UUID) — primary key
- `camera_config_id` (UUID, indexed) — references `vision_camera_configuration`
- `entity_id` (UUID, indexed) — references `vision_entity`
- `roi_hint` (JSONB, nullable) — optional region-of-interest hint for LLM frame analysis
- `created_at` (TIMESTAMPTZ, server default now())

### Constraints

- Composite unique constraint on `(camera_config_id, entity_id)` — prevents duplicate assignments

## Consequences

### Benefits
- Enables many-to-many camera-entity assignments with per-assignment ROI metadata
- Indexed columns support efficient lookups in both directions

### Tradeoffs
- No foreign keys to `vision_camera_configuration` or `vision_entity` (follows project convention of indexed columns without FK constraints)

## Related
- `db/tables/vision_camera_entities.py` — SQLAlchemy model
- `db/migrations/versions/2026-04-29_6de910391f1c_add_vision_camera_entity_table.py` — Alembic migration
