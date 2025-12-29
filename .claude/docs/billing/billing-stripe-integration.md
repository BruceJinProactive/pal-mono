# Billing System & Stripe Integration

## Overview

Palona uses a hybrid billing architecture that supports **account-level subscriptions** with **project-level usage tracking**. This allows a single business account (e.g., a restaurant chain) to subscribe once while tracking and billing usage per project (store/location).

## Architecture

### High-Level Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PALONA DATABASE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Account                                                                    │
│  ├── stripe_customer_id ────────────────────────────┐                       │
│  └── current_subscription_id                        │                       │
│           │                                         │                       │
│           ▼                                         │                       │
│  AccountSubscription                                │                       │
│  ├── external_id (public-facing ID)                 │                       │
│  ├── subscription_plan_id ──► SubscriptionPlan      │                       │
│  ├── stripe_subscription_id ────────────────────────┼──┐                    │
│  ├── status (pending/active/cancelled/expired)      │  │                    │
│  └── trial_start_date, start_date, end_date         │  │                    │
│           │                                         │  │                    │
│           │ 1:N                                     │  │                    │
│           ▼                                         │  │                    │
│  ProjectSubscription (per store)                    │  │                    │
│  ├── project_id                                     │  │                    │
│  ├── subscription_id (→ external_id)                │  │                    │
│  ├── stripe_product_id ─────────────────────────────┼──┼──┐                 │
│  ├── base_price_id ─────────────────────────────────┼──┼──┼──┐              │
│  ├── call_price_id ─────────────────────────────────┼──┼──┼──┼──┐           │
│  └── order_price_id ────────────────────────────────┼──┼──┼──┼──┼──┐        │
│                                                     │  │  │  │  │  │        │
└─────────────────────────────────────────────────────┼──┼──┼──┼──┼──┼────────┘
                                                      │  │  │  │  │  │
┌─────────────────────────────────────────────────────┼──┼──┼──┼──┼──┼──────┐
│                              STRIPE                 │  │  │  │  │  │      │
├─────────────────────────────────────────────────────┼──┼──┼──┼──┼──┼──────┤
│                                                     │  │  │  │  │  │      │
│  Customer ◄─────────────────────────────────────────┘  │  │  │  │  │      │
│  └── balance (credit balance)                          │  │  │  │  │      │
│                                                        │  │  │  │  │      │
│  Subscription ◄────────────────────────────────────────┘  │  │  │  │      │
│  └── items[] (multiple line items)                        │  │  │  │      │
│       ├── SubscriptionItem (base fee) ◄───────────────────┘  │  │  │      │
│       ├── SubscriptionItem (call usage) ◄────────────────────┘  │  │      │
│       └── SubscriptionItem (order usage) ◄──────────────────────┘  │      │
│                                                                    │      │
│  Product ◄─────────────────────────────────────────────────────────┘      │
│  └── metadata: {project_id, account_id, project_name}                     │
│                                                                           │
│  Billing Meters                                                           │
│  ├── calls_{project_id} → aggregates MeterEvents                          │
│  └── orders_{project_id} → aggregates MeterEvents                         │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

## Database Tables

### SubscriptionPlan

Defines the pricing tiers and quotas available to customers.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `name` | string | Display name ("Starter", "Growth", "Enterprise") |
| `tier` | TargetTier | Tier level (t1, t2, t3, enterprise) |
| `call_quota` | int | Included calls per month (e.g., 500) |
| `order_quota` | int | Included orders per month |
| `call_overage_charge` | int | Per-call charge after quota in cents (e.g., 50 = $0.50) |
| `order_overage_charge` | int | Per-order charge after quota in cents |
| `monthly_fee` | int | Base monthly fee in cents (e.g., 9900 = $99.00) |
| `credit_amount` | int | Credit granted on activation in cents |
| `free_trial_days` | int | Trial period length |
| `features_included` | list[str] | Features included in plan |
| `features_excluded` | list[str] | Features not included |
| `active` | bool | Can new customers select this plan? |
| `hidden` | bool | Show on pricing page? |

**Location**: `db/tables/subscriptions.py`

### AccountSubscription

Links an account to a subscription plan with billing lifecycle.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Internal primary key |
| `external_id` | UUID | Public-facing ID (used in APIs) |
| `version` | int | For optimistic locking/history tracking |
| `account_id` | UUID | FK → accounts.id |
| `subscription_plan_id` | UUID | FK → subscription_plans.id |
| `stripe_subscription_id` | string | Stripe subscription ID |
| `payment_method` | PaymentMethod | autopay, invoice, contract |
| `status` | SubscriptionStatus | pending, active, cancelled, expired, deleted |
| `trial_start_date` | datetime | When trial began |
| `start_date` | datetime | When billing starts (trial end) |
| `end_date` | datetime | Subscription end (None = ongoing) |

**Location**: `db/tables/subscriptions.py`

### ProjectSubscription

Per-project billing configuration linking a project to an account subscription.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `project_id` | UUID | The store/location |
| `subscription_id` | UUID | → AccountSubscription.external_id |
| `stripe_product_id` | string | Unique Stripe product for this project |
| `base_price_id` | string | Monthly flat fee price ID |
| `call_price_id` | string | Metered call usage price ID |
| `order_price_id` | string | Metered order usage price ID |
| `deleted` | bool | Soft delete flag |

Has a unique constraint ensuring one active subscription per project.

**Location**: `db/tables/subscriptions.py`

---

## Stripe Integration Modules

| Module | Location | Purpose |
|--------|----------|---------|
| `_subscription.py` | `services/subscription_service/` | Main subscription business logic |
| `_stripe_subscription.py` | `services/subscription_service/` | Stripe Subscription API operations |
| `_stripe_product.py` | `services/subscription_service/` | Stripe Product/Price/Meter creation |
| `_stripe_customer.py` | `services/subscription_service/` | Stripe Customer & credit operations |
| `_billing_details.py` | `services/subscription_service/` | Usage metrics & invoice retrieval |
| `stripe_usage_billing.py` | `services/subscription_service/` | Meter event sending |

---

## Stripe Object Mapping

| Palona Entity | Stripe Object | Purpose |
|---------------|---------------|---------|
| Account | Customer | Billing identity, stores credit balance |
| AccountSubscription | Subscription | Monthly billing cycle, contains line items |
| ProjectSubscription | Product | Per-project product for tracking |
| ProjectSubscription.base_price_id | Price (flat) | Monthly base fee |
| ProjectSubscription.call_price_id | Price (metered) | Usage-based call charges |
| ProjectSubscription.order_price_id | Price (metered) | Usage-based order charges |
| Call event | MeterEvent | Usage tracking for billing |

---

## Key Flows

### 1. Subscription Creation Flow

**Path**: `services/subscription_service/_subscription.py:create_account_subscription()`

1. Validate subscription plan exists and is active
2. Check for date overlaps with existing subscriptions
3. Create `AccountSubscription` record with `status=pending`
4. Update `account.current_subscription_id`
5. For each project, call `add_project_to_subscription()`
6. Send activation notification

**add_project_to_subscription()** creates per-project Stripe artifacts:
1. Create Stripe Product for the project with metadata linking to account/project
2. Create `ProjectSubscription` database record
3. Create base fee price (if plan has `monthly_fee > 0`)
4. Create Billing Meter for calls with event name `calls_{project_id}`
5. Create metered price with tiered pricing (quota free, overage charged)
6. Repeat for orders if `order_overage_charge` is configured
7. If Stripe subscription already exists, add the new prices as subscription items

### 2. Stripe Checkout Flow

**Path**: `services/subscription_service/_subscription.py:create_stripe_checkout_url()`

1. Retrieve all `ProjectSubscription` records for the subscription
2. Build `line_items` array from all project prices:
   - Base fee prices: quantity=1
   - Metered prices: no quantity (usage-based)
3. Create Stripe Checkout Session with:
   - `mode="subscription"` for recurring billing
   - `subscription_data.trial_end` for trial period
   - `subscription_data.metadata` linking to our `external_id`
   - `client_reference_id` set to our `account_id`
   - Referral code for Rewardful tracking (if provided)
4. Return checkout URL for redirect

### 3. Checkout Success Handling

**Webhook Path**: `api/routes/admin/_subscription.py` handles POST from admin endpoint

1. Retrieve checkout session from Stripe using `session_id`
2. Extract Stripe subscription ID and customer ID from response
3. Update `AccountSubscription` with:
   - `stripe_subscription_id`
   - `status = active`
4. Grant plan activation credit if `plan.credit_amount` exists
5. Update `account.stripe_customer_id` if not already set

### 4. Usage Metering Flow

**Trigger**: After VAPI call completion in `api/routes/integrations/vapi/_implementation.py`

1. Get the project's meter event name: `calls_{project_id}`
2. Look up the account's `stripe_customer_id`
3. Send MeterEvent to Stripe with:
   - `event_name`: the meter identifier
   - `payload.stripe_customer_id`: for customer mapping
   - `payload.value`: "1" for one call
   - `timestamp`: when the call occurred

**Stripe processing**:
- Meter Events are aggregated by the Billing Meter
- At billing cycle end, Stripe calculates total usage per meter
- Applies tiered pricing (quota calls free, overage charged per-call)
- Generates invoice with line items showing usage breakdown per project

### 5. Plan Switching Flow

**Path**: `services/subscription_service/_subscription.py:switch_subscription_plan()`

1. Validate current subscription is active
2. Validate new plan exists and is active
3. For each project subscription:
   - Create new Stripe product with new plan name
   - Create new prices with new plan's quotas/overage rates
   - **Swap** existing subscription items to new prices (in-place update)
   - Update `ProjectSubscription` with new price IDs
4. Create new `AccountSubscription` version with new `subscription_plan_id`
5. Proration handled by Stripe (`proration_behavior="create_prorations"`)

**Why in-place swapping?** Prevents double-counting usage during plan changes by updating the existing subscription item rather than removing and adding.

### 6. Credit Balance Flow

**Path**: `services/subscription_service/_stripe_customer.py:grant_credit_balance()`

Credits are stored as negative balance on Stripe Customer and automatically applied to the next invoice.

**Credit sources**:
- Plan activation (`plan.credit_amount` granted on checkout success)
- Admin manual grant via API
- Referral rewards
- Service credits for issues

**Getting balance**: `get_credit_balance()` returns current credit in cents and currency.

**History**: `get_credit_grants_history()` returns all balance transactions with metadata.

---

## Stripe Webhook Handling

**Endpoint**: `POST /v1/integrations/stripe/webhook`

**Path**: `api/routes/integrations/stripe/_implementation.py`

### Handled Events

| Stripe Event | Action |
|--------------|--------|
| `invoice.payment_failed` | Send payment failed notification to account |
| `invoice.payment_succeeded` | Send payment receipt notification |
| `invoice.finalized` | Send invoice notification |

### Webhook Processing

1. Verify signature using `stripe.Webhook.construct_event()` with `STRIPE_WEBHOOK_SECRET`
2. Route by `event.type` to appropriate handler
3. Map `stripe_customer_id` → `account_id` via database lookup
4. Create `BillingEvent` and send notification through notification service
5. Return 200 success to Stripe

---

## Tiered Pricing Structure

### How Tiers Work

Example for a plan with `call_quota=100` and `call_overage_charge=50` (cents):

| Tier | Range | Price |
|------|-------|-------|
| Tier 1 | Calls 1-100 | $0.00/call (included in base fee) |
| Tier 2 | Calls 101+ | $0.50/call (overage) |

Stripe's `tiers_mode="graduated"` means each tier is priced independently (not volume pricing where all units get the highest tier price).

### Meter Event Naming Convention

- Calls: `calls_{project_id}` (e.g., `calls_a95a1d1b-c37d-4a6f-97af-3b864883a457`)
- Orders: `orders_{project_id}`

This allows per-project usage tracking while aggregating to a single account invoice.

---

## Subscription Lifecycle States

```
                    ┌──────────────┐
                    │   PENDING    │ ← Created, awaiting payment
                    └──────┬───────┘
                           │ Checkout complete
                           ▼
                    ┌──────────────┐
         ┌──────────│    ACTIVE    │◄──────────┐
         │          └──────┬───────┘           │
         │                 │                   │
         │ Cancel          │ Payment failed    │ Payment succeeds
         │                 ▼                   │
         │          ┌──────────────┐           │
         │          │   EXPIRED    │───────────┘
         │          └──────┬───────┘
         │                 │ Grace period ends
         ▼                 ▼
  ┌──────────────┐  ┌──────────────┐
  │  CANCELLED   │  │   DELETED    │ ← Hard delete after retention period
  └──────────────┘  └──────────────┘
```

---

## API Endpoints

### Subscription Management

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/accounts/{name}/subscriptions` | POST | Create subscription |
| `/admin/accounts/{name}/subscriptions` | GET | List account subscriptions |
| `/admin/subscriptions/{external_id}/checkout` | POST | Get Stripe checkout URL |
| `/admin/subscriptions/{external_id}/checkout/success` | POST | Handle checkout callback |
| `/admin/subscriptions/{external_id}` | PATCH | Update subscription |
| `/admin/subscriptions/{external_id}` | DELETE | Cancel subscription |
| `/admin/subscriptions/{external_id}/switch-plan` | POST | Change plan |

### Project Subscription Management

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/subscriptions/{external_id}/projects` | GET | List project subscriptions |
| `/admin/subscriptions/{external_id}/projects` | POST | Add project to subscription |
| `/admin/subscriptions/{external_id}/projects/{project_id}` | DELETE | Remove project |

### Credit Management

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/accounts/{name}/credit` | GET | Get credit balance |
| `/admin/accounts/{name}/credit` | POST | Grant credit |
| `/admin/accounts/{name}/credit/history` | GET | Credit transaction history |

---

## Environment Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `STRIPE_API_KEY` | Yes | Server-side API key (sk_live_xxx or sk_test_xxx) |
| `STRIPE_WEBHOOK_SECRET` | Yes | Webhook signature verification (whsec_xxx) |

---

## Testing

### Test Mode
- Use `STRIPE_API_KEY=sk_test_xxx` for test mode
- Test cards: `4242424242424242` (success), `4000000000000002` (decline)
- Test webhooks with Stripe CLI: `stripe listen --forward-to localhost:8000/v1/integrations/stripe/webhook`

### Webhook Testing
```bash
# Trigger test event
stripe trigger invoice.payment_succeeded

# Forward to local
stripe listen --forward-to localhost:8000/v1/integrations/stripe/webhook
```

---

## Related Documentation

- [Billing Notifications](./billing-notifications.md) - Automated billing event notifications
- [Architecture Overview](./architecture.md) - System architecture
