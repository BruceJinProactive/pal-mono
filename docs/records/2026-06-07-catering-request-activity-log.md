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
- Added frozen activity dataclass and async repository helpers for creating
  entries and listing project-scoped activity timelines.
- Added service helpers that verify request ownership before listing timeline
  entries and bound list reads to the supported page size.
- Added `include_activities` support on the project catering request list so
  the workflow page can receive embedded timeline entries without a standalone
  activity-log URL.
- Automatically records `REQUEST_CREATED` entries when the async customer/AI
  catering persistence path creates a request.
- Automatically records `REQUEST_CREATED` entries when the admin catering
  create route persists a request.
- Automatically records `REQUEST_UPDATED` or `STATUS_CHANGED` entries when the
  async catering update service changes request fields. Status-change metadata
  includes `from_status`, `to_status`, and the full changed-field snapshot.

## Constraints

The table intentionally does not use foreign-key constraints or ORM
relationships, matching ADR-004 and ADR-017. The activity log is the
product-facing timeline; the existing generic `change_log` table remains the
admin-oriented field-diff audit log. Activity entries are intended to be
embedded in the catering request workflow page payload rather than exposed
through a dedicated activity-log URL.
