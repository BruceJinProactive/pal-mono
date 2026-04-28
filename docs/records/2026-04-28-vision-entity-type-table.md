# Vision Entity Type Table

**Date**: 2026-04-28
**Author**: Bruce Jin
**Status**: Implemented

## Context

The vision system needs a way to define per-account entity types (e.g., table, employee, food_tray) that cameras and monitoring can detect and classify. These types are account-scoped so each business can customize which entities matter to them.

## Decision

Add a new `vision_entity_type` table for per-account entity type definitions.

### New Table: `vision_entity_type`

SQLAlchemy model for vision entity type definitions:
- `id` (UUID) — primary key
- `account_id` (UUID, indexed) — owning account
- `name` (VARCHAR 100) — machine name (e.g. `"table"`, `"employee"`, `"food_tray"`)
- `display_name` (VARCHAR 255) — human-readable label (e.g. `"Food Tray"`)
- `description` (TEXT, nullable) — optional description
- `icon` (VARCHAR 10, nullable) — emoji for UI display
- `is_active` (BOOLEAN, default true) — soft-delete flag
- `created_at` (TIMESTAMPTZ, server default now())
- `updated_at` (TIMESTAMPTZ, server default now(), on update now())

### Constraints

- Unique constraint on `(account_id, name)` — one entity type per name per account

## Consequences

### Benefits
- Account-scoped entity types allow per-business customization
- Soft-delete via `is_active` avoids breaking references
- `icon` field enables lightweight UI representation

### Tradeoffs
- No foreign key to `accounts` table (follows project convention of indexed columns without FK constraints)

## Related
- `db/tables/vision_entity_types.py` — SQLAlchemy model
- `db/migrations/versions/2026-04-28_ac9152faa1d3_add_vision_entity_type_table.py` — Alembic migration
