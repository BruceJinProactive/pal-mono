# Order Idempotent Writes

Date: 2026-05-31

## Summary

Order persistence now has schema support for canonical idempotency keys based on
external order identity: `(vendor, store_id, order_id)`.

The `orders` table has a nullable `idempotency_key` column and a unique partial
index for non-null keys. Application write logic lands in the follow-up PR.

## Rationale

Agent order details can be emitted through more than one path, and callers may
retry after timeouts. Without source-level idempotency, those repeated logical
events create duplicate `orders` rows and inflate business metrics.

## Rollout Notes

The migration adds nullable `orders.idempotency_key`, backfills only the newest
canonical row for each historical external order identity, and leaves older
duplicates with `NULL`. The unique partial index applies only to non-null keys,
so production can deploy before a separate cleanup of historical duplicate rows.

Orders without a complete external identity keep the previous insert behavior.
Fallback keys for missing external IDs are intentionally left for a later task.
