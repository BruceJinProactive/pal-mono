# Trial End Extension via Update Subscription Endpoint

**Date:** 2026-05-20

## Problem

FDEs frequently need to extend a subscription's trial period because we don't want to charge a client before they actually go live. The typical scenario: we start a subscription for a new account, but the client isn't ready to launch yet (onboarding delays, menu changes, hardware setup, etc.). The subscription should stay in a trialing state without charge until we're actually ready to bill them.

Previously, extending a trial required manually calculating and updating both `trial_start_date` and `start_date` — error-prone and unintuitive.

## Solution

Added a `trial_end` field to the PATCH `/accounts/{account_name}/subscriptions/{external_id}` endpoint, following the Stripe pattern:

- Pass an absolute `trial_end` datetime — the date you want the trial to end
- `start_date` (paid billing start) is automatically set to match
- If the subscription has no `trial_start_date`, one is set to now
- If the subscription is `active`, status flips to `trialing`
- The change is synced to Stripe via `stripe.Subscription.modify(trial_end=...)`

## Usage

```json
PATCH /accounts/{account_name}/subscriptions/{external_id}

{
  "trial_end": "2026-07-01T00:00:00Z"
}
```

This keeps the subscription trialing (no charge) until July 1, at which point billing begins automatically.

## Files Changed

- `api/schemas/admin/subscription.py` — `trial_end` field + conflict validator
- `services/subscription_service/_subscription.py` — trial_end logic + Stripe sync
- `tests/services/subscription_service/test_update_account_subscription_trial_end.py`
