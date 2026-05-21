# Catering Request Plan Statuses

Last updated: 2026-05-21

## Summary

Added the missing catering request plan status values to the application enum and
PostgreSQL enum:

- `LEAD`
- `PROPOSAL`
- `LOCKED`
- `IN_PREPARATION`
- `CLOSED`

This is intentionally a schema-only change. Existing catering request defaults
and business logic remain unchanged so a follow-up commit can adopt the new
lifecycle behavior separately.

## Migration

The Alembic migration appends the new values to the existing `requeststatus`
PostgreSQL enum with `ADD VALUE IF NOT EXISTS`.

Downgrade maps rows using the new statuses back to `INQUIRY` for older app code,
but PostgreSQL enum values are not removed.
