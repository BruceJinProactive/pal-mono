# Fix: Add Missing changeresourcetype Enum Values

**Date**: 2026-04-01
**Author**: Jeffrey Weisinger
**Status**: Implemented

## Context

The `ChangeResourceType` Python enum in `db/tables/change_log.py` includes `OrderIntegration`, `POSIntegration`, and `CapabilityAction`, but these values were never added to the corresponding PostgreSQL enum type via a migration.

PostgreSQL enforces a strict allowlist for native enum columns. The `change_log.resource_type` column uses `Enum(ChangeResourceType)`, which creates a native PostgreSQL ENUM — not a VARCHAR. Any INSERT or query referencing an unregistered value is rejected, causing:

1. **500 errors when saving Prompt V2 actions** — `create_change_log()` tries to insert `resource_type='CapabilityAction'`, PostgreSQL rejects it, and the transaction rollback cascades to the action save
2. **Edit history filtering broken** — querying `WHERE resource_type IN ('CapabilityAction')` fails because PostgreSQL casts the filter value against the enum

`OrderIntegration` and `POSIntegration` had the same missing migration, though they were not actively causing errors.

## Decision

Add an Alembic migration to register the missing enum values in PostgreSQL using `ALTER TYPE ... ADD VALUE IF NOT EXISTS`, following the same pattern used for `Prompt` (2025-07-21) and `Subscription`/`SubscriptionPlan` (2025-06-19).

### Migration

```sql
ALTER TYPE changeresourcetype ADD VALUE IF NOT EXISTS 'OrderIntegration';
ALTER TYPE changeresourcetype ADD VALUE IF NOT EXISTS 'POSIntegration';
ALTER TYPE changeresourcetype ADD VALUE IF NOT EXISTS 'CapabilityAction';
```

`IF NOT EXISTS` makes the migration idempotent and safe to run on environments where some values may already exist. Downgrade is a no-op since PostgreSQL does not support removing enum values.

## Consequences

- Prompt V2 action saves and edit history filtering work correctly
- Change log entries can be created for `OrderIntegration`, `POSIntegration`, and `CapabilityAction` mutations
- No impact on existing data — additive only

## Related
- `db/migrations/versions/2026-04-01_9b3b68035ed2_add_missing_values_to_.py` — the migration
- `db/tables/change_log.py` — enum definition
- `docs/records/2026-03-26-capability-action-change-tracking.md` — original record that missed the migration
