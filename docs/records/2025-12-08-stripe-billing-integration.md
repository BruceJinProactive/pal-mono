# Stripe Billing Integration

> **Date:** 2025-12-08

## Summary

Implemented Stripe-based subscription billing with webhook processing, usage metering, invoicing, and credit management. Replaced the earlier checkout-only payment flow with a full subscription lifecycle.

## What Was Built

### Subscription Service (`services/subscription_service/`)

| Module | Purpose |
|--------|---------|
| `billing_service.py` | Central billing orchestration |
| `_subscription.py` | Core subscription lifecycle logic |
| `_stripe_subscription.py` | Stripe Subscription API operations |
| `_stripe_customer.py` | Stripe customer creation and credit balance |
| `_stripe_product.py` | Stripe Product/Price/Meter creation |
| `stripe_invoice.py` | Invoice retrieval and processing |
| `stripe_usage_billing.py` | Metered usage event reporting |
| `_billing_details.py` | Usage metrics and billing details |

### API Endpoints

- **Subscription management**: create, list, checkout, update, cancel, switch-plan
- **Project subscriptions**: per-project subscription assignment
- **Credit management**: add credits, get balance
- **Stripe webhooks**: `api/routes/integrations/stripe/_implementation.py`

### Data Model

`SubscriptionPlan`, `AccountSubscription`, `ProjectSubscription` tables mapping to Stripe entities (Product → Plan, Subscription → AccountSubscription).

### Migration Timeline

1. **May 2025**: Initial checkout API and webhook
2. **Dec 5, 2025**: Billing types and subscription service integration (#2817)
3. **Dec 8, 2025**: Stripe webhook integration (#2826)
4. **Dec 15, 2025**: Stripe invoicing (#2883)
5. **Dec 26, 2025**: Webhook handler refactor (#3021)
6. **Dec 30, 2025**: Per-project Stripe customer ID (#3038)

## Key Files

| Component | File |
|-----------|------|
| Service | `services/subscription_service/` (8 modules) |
| Stripe webhooks | `api/routes/integrations/stripe/_implementation.py` |
| Admin endpoints | `api/routes/admin/_subscription.py`, `_billing.py` |
| State doc | `docs/state/billing.md` |

## Origin

Plan: `.claude/docs/billing/billing-stripe-integration.md` (now archived)
