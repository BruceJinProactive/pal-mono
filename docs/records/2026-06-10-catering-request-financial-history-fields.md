# Catering Request Financial History Fields

Date: 2026-06-10

## Summary

Added customer-history snapshot and monetary planning fields to catering
requests so catering operations can quickly tell whether a requester has prior
Palona activity and track estimated/confirmed order and deposit amounts.

## Implementation Notes

- The schema slice added `prior_catering_request_count`, `prior_order_count`,
  `last_catering_request_at`, and `last_order_at` to `catering_requests`.
- The schema slice added `estimated_order_value`, `confirmed_order_value`,
  `deposit_requirement_value`, and `deposit_received_value` as nullable
  `Numeric(12, 2)` columns.
- Added repository summary queries for prior same-account catering requests by
  requester phone or requester email.
- The order-history snapshot is matched across the same account by requester
  phone.
- Populated history fields once when a new async catering request is created.
  Existing idempotent requests keep their original snapshots.
- Exposed monetary fields in catering create/update schemas and normal
  catering request responses.
- Added focused repository and service coverage for field mapping, snapshot
  population, and order/catering history summaries.

## Migration

Alembic revision: `b7f43f8aac6e`.

## Constraints

Phone matching currently uses digits-only comparisons against stored request
and order phone strings. This matches existing behavior, but higher-volume
usage should move toward normalized/indexed phone columns.
