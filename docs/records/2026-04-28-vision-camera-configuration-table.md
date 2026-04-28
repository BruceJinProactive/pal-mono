# Vision Camera Configuration Table

**Date**: 2026-04-28
**Author**: Bruce Jin
**Status**: Implemented

## Context

The vision system needs per-camera configuration that ties a signal source (camera) to its LLM processing settings — which prompt to send with each frame, which model/provider to use, processing frequency, and optional reference images for comparison.

## Decision

Add a new `vision_camera_configuration` table with a 1:1 relationship to `signal_sources`.

### New Table: `vision_camera_configuration`

SQLAlchemy model for camera LLM processing configuration:
- `id` (UUID) — primary key
- `signal_source_id` (UUID, indexed, unique constraint) — 1:1 with signal source/camera
- `project_id` (UUID, indexed) — owning project/location
- `name` (VARCHAR 255) — configuration name
- `llm_prompt` (TEXT) — prompt sent to LLM with each frame
- `llm_provider` (VARCHAR 20, default `'azure'`) — `'azure'` or `'google'`
- `llm_model` (VARCHAR 100, default `'gpt-4o'`) — model identifier
- `processing_interval_seconds` (INTEGER, default 15) — seconds between frame processing
- `reference_images` (JSONB, default `[]`) — list of `{url, description}` objects
- `enabled` (BOOLEAN, default true) — on/off toggle
- `created_at` (TIMESTAMPTZ, server default now())
- `updated_at` (TIMESTAMPTZ, server default now(), on update now())

### Constraints

- Unique constraint on `signal_source_id` — enforces 1:1 with camera

## Consequences

### Benefits
- Per-camera LLM configuration allows different prompts and models per camera
- Reference images enable visual comparison workflows
- Configurable processing interval balances cost vs responsiveness

### Tradeoffs
- No foreign keys to `signal_sources` or `projects` (follows project convention of indexed columns without FK constraints)

## Related
- `db/tables/vision_camera_configurations.py` — SQLAlchemy model
- `db/migrations/versions/2026-04-28_dce8e39a4f7e_add_vision_camera_configuration_table.py` — Alembic migration
