# Toast Checkout Session Schema

## Summary

Added `toast_checkout_sessions` to store Toast hosted-checkout session payloads behind opaque UUID tokens. This replaces URL-carried encrypted payment payloads for the new direct checkout-request flow.

## Table Shape

- `id`: internal UUID primary key.
- `token`: unique UUID used by `/checkout/toast?t=<token>` lookups.
- `conversation_id`: conversation that produced the checkout request.
- `external_reference_id`: unique Toast payment-intent external reference for idempotency.
- `order_external_id`: Toast order external ID for lookup/debugging.
- `request_payload`: original checkout request JSON emitted by `pal-agents`.
- `session_payload`: payment-page JSON returned after mono creates the Toast payment intent and iframe token.
- `checkout_url`: shortened public checkout URL.
- `status`: processing state such as `processing`, `ready`, `failed`, or `delivery_failed`.
- `expires_at`, `created_at`, `updated_at`: lifecycle timestamps.

## Notes

The schema intentionally keeps payment-page payload storage in `pal-mono` while exposing only the opaque `token` in customer-facing URLs. Runtime processing and route wiring ship separately from this schema-only change.
