# Catering Request Financial History Schema

Date: 2026-06-10

## Summary

Added database columns to `catering_requests` for customer-history snapshots and
financial planning values. This schema slice intentionally contains only the
table model and Alembic migration; runtime population and API/service exposure
ship separately.

## Schema

- `prior_catering_request_count`
- `prior_order_count`
- `last_catering_request_at`
- `last_order_at`
- `estimated_order_value`
- `confirmed_order_value`
- `deposit_requirement_value`
- `deposit_received_value`

`prior_catering_request_count` and `prior_order_count` are non-null integers
with server default `0`. The timestamp and value columns are nullable, and the
value columns use `Numeric(12, 2)`.

## Migration

Alembic revision: `b7f43f8aac6e`.
