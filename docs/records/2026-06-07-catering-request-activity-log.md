# Catering Request Activity Log

Date: 2026-06-07

## Summary

Added the database foundation for per-request catering activity timelines.
`catering_request_activities` is an append-only table keyed by
`catering_request_id` and `project_id`, with enum columns for activity type,
actor type, and source, plus a JSONB `metadata` column for event-specific
payloads.

## Implementation Notes

- Added SQLAlchemy table model and Alembic migration `20cb36ab46c9`.
- Exported the table model from `db/tables/__init__.py` so Alembic metadata
  discovery includes it.
- Added typed activity, actor, and source enum columns, actor identifiers,
  `occurred_at` and `created_at` timestamps, JSONB metadata, and lookup indexes
  for request/project timeline reads.
- Deferred repository, service, API, and automatic activity-writing logic to a
  follow-up non-schema PR so this PR stays within the schema-only validation
  gate.

## Constraints

The table intentionally does not use foreign-key constraints or ORM
relationships, matching ADR-004 and ADR-017. The activity log is the
product-facing timeline; the existing generic `change_log` table remains the
admin-oriented field-diff audit log. Product intent is for activity entries to
be embedded in the catering request workflow page payload rather than exposed
through a dedicated activity-log URL; the runtime wiring is not part of this
schema-only PR.
