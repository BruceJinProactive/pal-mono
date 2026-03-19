# Billing Notifications V1 (POC)

> **Date:** 2025-12-04

## Summary

Implemented V1 proof-of-concept for billing email notifications. The system sends the right email to the right account for key subscription and payment events via Postmark, proving the end-to-end flow works.

## What Changed

### Database

- **`accounts` table extended** with:
  - `notification_preferences` (JSONB, default `{"email_enabled": true}`)
  - `notification_email` (nullable string, overrides primary account email)
- Migration: `2025-12-04_8f3a74ca9c57_add_notification_preferences_to_accounts.py`

### Notification Service

- **`services/notification_service/`** — new service module:
  - `schema.py`: `BillingEventType` enum (SUBSCRIPTION_ACTIVATED, SUBSCRIPTION_CANCELLED, SUBSCRIPTION_TRIAL_WILL_END, PAYMENT_FAILED, PAYMENT_SUCCEEDED, INVOICE_SENT, INVOICE_UPCOMING, INVOICE_PAYMENT_DUE_SOON, INVOICE_OVERDUE) and `BillingEvent` model
  - `_implementation.py`: Postmark template ID mappings, `handle_billing_event()` handler
  - `__init__.py`: V1 sends email synchronously; notes V2 will publish to EventBridge

### Email Types (6+ in practice, 4 originally planned)

| Event | Postmark Template ID |
|-------|---------------------|
| SubscriptionActivated | 42419409 |
| SubscriptionCancelled | 42419436 |
| SubscriptionTrialWillEnd | 43276310 |
| PaymentFailed | 42419416 |
| PaymentSucceeded | 42419437 |
| InvoiceUpcoming | 43276324 |

### Flow

```
Source → BillingEvent → handle_billing_event() → sendBillingEmail() → Postmark
```

- Stripe webhooks and subscription service both construct `BillingEvent` objects
- Synchronous email sending (no EventBridge, no retries, no throttling)
- Respects `notification_preferences.email_enabled` and `notification_email` override

## What Was Deferred to V2

- EventBridge-based event routing
- `notifications` audit table
- Throttling and deduplication
- SMS (Twilio)
- Scheduled jobs (trial ending, quota warnings, card expiry)
- Retry logic

## Origin

Plans: `docs/plans/notifications/v1-architecture.md`, `docs/plans/notifications/v1-requirements.md` (now archived)
