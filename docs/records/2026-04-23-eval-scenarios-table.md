# Eval Scenarios Table — Migrate YAML Scenarios to DB

**Date**: 2026-04-23
**Author**: System
**Status**: Implemented

## Context

Eval scenarios were stored as YAML files on the filesystem under `services/eval_service/scenarios/`, with a `project_map.json` mapping project UUIDs to file paths. This approach had several limitations:

- No API for managing scenarios — required code changes to add/update scenarios
- File-based storage not queryable or filterable
- No clear ownership model tying scenarios to projects
- Deployment required shipping YAML files alongside application code

## Decision

Add a new `eval_scenarios` table to store scenario YAML content directly in the database, managed via API endpoints.

### New Table: `eval_scenarios`

SQLAlchemy model storing raw YAML scenario files:
- `id` (UUID) — primary key
- `project_id` (UUID, nullable, indexed) — `NULL` = generic scenarios that run for all projects; set = project-specific scenarios
- `scenario_type` (VARCHAR 50, indexed) — category: `"generic"`, `"ordering"`, or future types
- `name` (VARCHAR 255) — human-readable identifier (e.g. `"address_inquiry"`, `"calibbq"`)
- `raw_yaml` (TEXT) — the raw YAML file content, stored as-is
- `created_at` (TIMESTAMP WITH TIMEZONE, server default now())
- `updated_at` (TIMESTAMP WITH TIMEZONE, server default now(), on update now())
- `updated_by` (VARCHAR 255, nullable) — who last updated the scenario

### Constraints

- Unique constraint `uq_eval_scenarios_project_name` on `(project_id, name)` — one scenario per name per project; `NULL` project_id is its own namespace for generic scenarios

### Scenario Loading

When an eval run starts for a given `project_id`:
1. Query scenarios where `project_id` matches — project-specific
2. Query scenarios where `project_id IS NULL` — generic
3. Combine both, parse `raw_yaml` through existing `EvalScenario` pydantic model

This replaces both `_scenario_loader.py` filesystem reads and `project_map.json` lookups.

## Consequences

### Benefits
- Scenarios manageable via CRUD API — no code deploys needed
- Scenarios queryable by project, type, or name
- Clear ownership: `project_id` column directly ties scenarios to projects
- Generic scenarios (NULL project_id) automatically included for all projects

### Tradeoffs
- Raw YAML stored as text — not normalized, but preserves flexibility of the YAML format
- No versioning — scenarios are overwritten in place

## Related
- `db/tables/eval_scenarios.py` — SQLAlchemy model
- `db/migrations/versions/2026-04-23_ba3efdb08672_add_eval_scenarios_table.py` — Alembic migration
- `docs/plans/eval-scenarios-db-migration.md` — full migration plan
