# Billing Architecture Design

## Overview

This document describes Stripe's billing concepts and how Palona can support flexible billing configurations including:
- **Account-level billing**: One Stripe Customer/subscription/invoice for all stores
- **Project-level billing**: Separate Stripe Customer per store (complete isolation)
- **Payment method flexibility**: Autopay (card) or Invoice per billing entity
- **Per-store configuration**: Different emails, payment terms, billing cycles
- **Complete isolation**: Each store manages their own payment methods independently

---

## Stripe Core Concepts

### Entity Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STRIPE ENTITY MODEL                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Customer                                                                   │
│  ├── id: cus_xxxxx                                                          │
│  ├── email, name, metadata                                                  │
│  ├── balance (credit/debit balance applied to invoices)                     │
│  ├── default_payment_method                                                 │
│  │                                                                          │
│  ├── PaymentMethods[] ─────────────────────────────────────────┐            │
│  │   ├── pm_card_xxxxx (Visa ending 4242)                      │            │
│  │   └── pm_card_yyyyy (Amex ending 1234)                      │            │
│  │                                                             │            │
│  ├── Subscriptions[] ──────────────────────────────────────────┼──┐         │
│  │   └── Subscription                                          │  │         │
│  │       ├── id: sub_xxxxx                                     │  │         │
│  │       ├── status: active|past_due|canceled|trialing         │  │         │
│  │       ├── collection_method: charge_automatically|send_invoice │         │
│  │       ├── current_period_start, current_period_end          │  │         │
│  │       ├── trial_end                                         │  │         │
│  │       │                                                     │  │         │
│  │       └── SubscriptionItems[] ──────────────────────────────┼──┼──┐      │
│  │           ├── si_xxxxx → Price (flat fee)                   │  │  │      │
│  │           ├── si_yyyyy → Price (metered calls)              │  │  │      │
│  │           └── si_zzzzz → Price (metered orders)             │  │  │      │
│  │                                                             │  │  │      │
│  └── Invoices[] ───────────────────────────────────────────────┘  │  │      │
│      └── Invoice                                                  │  │      │
│          ├── id: in_xxxxx                                         │  │      │
│          ├── status: draft|open|paid|void|uncollectible           │  │      │
│          ├── collection_method: charge_automatically|send_invoice │  │      │
│          ├── amount_due, amount_paid                              │  │      │
│          ├── customer_email (can override Customer.email)         │  │      │
│          ├── hosted_invoice_url (payment link)                    │  │      │
│          └── subscription: sub_xxxxx (if from subscription)       │  │      │
│                                                                   │  │      │
├───────────────────────────────────────────────────────────────────┼──┼──────┤
│                                                                   │  │      │
│  Product ◄────────────────────────────────────────────────────────┘  │      │
│  ├── id: prod_xxxxx                                                  │      │
│  ├── name: "Growth Plan - San Pedro Store"                           │      │
│  ├── metadata: {project_id, account_id}                              │      │
│  │                                                                   │      │
│  └── Prices[] ◄──────────────────────────────────────────────────────┘      │
│      ├── price_flat (recurring, $99/month)                                  │
│      ├── price_calls (metered, tiered, linked to Meter)                     │
│      └── price_orders (metered, tiered, linked to Meter)                    │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Billing Meter                                                              │
│  ├── id: meter_xxxxx                                                        │
│  ├── event_name: "calls_project_uuid"                                       │
│  ├── display_name: "San Pedro Calls"                                        │
│  └── aggregation: count                                                     │
│                                                                             │
│  MeterEvent (usage records)                                                 │
│  ├── event_name: "calls_project_uuid"                                       │
│  ├── payload: {stripe_customer_id, value: "1"}                              │
│  └── timestamp                                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Stripe Entity Definitions

### Customer

The billable entity. One Customer = one billing identity.

| Field | Purpose |
|-------|---------|
| `id` | Unique identifier (cus_xxxxx) |
| `email` | Default email for invoices |
| `balance` | Credit balance (negative = credit available, positive = owes money) |
| `default_payment_method` | Card charged for autopay subscriptions |
| `invoice_settings.default_payment_method` | Override payment method for invoices |
| `metadata` | Custom key-value data |

### Subscription

Recurring billing configuration. Generates invoices at each billing cycle.

| Field | Purpose |
|-------|---------|
| `id` | Unique identifier (sub_xxxxx) |
| `status` | `active`, `past_due`, `canceled`, `trialing`, `incomplete` |
| `collection_method` | `charge_automatically` (autopay) or `send_invoice` (manual payment) |
| `items[]` | Line items, each linked to a Price |
| `billing_cycle_anchor` | Timestamp determining billing day of month |
| `trial_end` | When trial ends and billing starts |
| `days_until_due` | For invoice method, days customer has to pay |
| `default_payment_method` | Card for THIS subscription (overrides Customer default) |
| `metadata` | Custom key-value data |

**Key insight**: One Subscription = one Invoice per billing cycle

### Product & Price

| Entity | Purpose |
|--------|---------|
| **Product** | What you're selling (logical grouping, e.g., "Growth Plan - Store Name") |
| **Price** | How much and how often (attached to Product) |

**Price types:**

| Type | Description | Example |
|------|-------------|---------|
| Flat/Licensed | Fixed amount per interval | $99/month base fee |
| Metered | Usage-based, linked to Billing Meter | $0.50/call after quota |
| Tiered | Different rates at different volumes | First 100 calls free, then $0.50 |

### Billing Meter & MeterEvent

| Entity | Purpose |
|--------|---------|
| **Meter** | Defines how to aggregate usage events |
| **MeterEvent** | Individual usage record sent via API |

Meters count or sum MeterEvents and report the total to Stripe at billing time.

| Meter Field | Purpose |
|-------------|---------|
| `event_name` | Identifier for matching events (e.g., `calls_{project_id}`) |
| `display_name` | Human-readable name |
| `default_aggregation` | `count` (count events) or `sum` (sum values) |
| `customer_mapping` | How to associate events with customers |

### Invoice

Generated automatically by subscriptions or manually via API.

| Field | Purpose |
|-------|---------|
| `id` | Unique identifier (in_xxxxx) |
| `status` | `draft`, `open`, `paid`, `void`, `uncollectible` |
| `collection_method` | `charge_automatically` or `send_invoice` |
| `customer_email` | Recipient email (can override Customer.email) |
| `amount_due` | Total amount owed |
| `hosted_invoice_url` | Payment link for manual payment |
| `days_until_due` | Payment deadline (for send_invoice method) |

---

## Collection Method Comparison

| Aspect | `charge_automatically` (Autopay) | `send_invoice` (Invoice) |
|--------|----------------------------------|--------------------------|
| Payment timing | Immediate when invoice created | Customer pays within `days_until_due` |
| Card required | Yes, upfront at checkout | No, can add later |
| Retry on failure | Stripe auto-retries (configurable) | No auto-retry |
| Customer action | None required | Must click payment link in email |
| Failed payment | Subscription goes `past_due` | Invoice stays `open` until paid/voided |
| Use case | Self-serve, consumer | Enterprise, B2B, contracts |

---

## Billing Level Architectures

### Option A: Account-Level Billing (Current Implementation)

All stores under an account share one Stripe Customer and Subscription, receiving one consolidated invoice.

```
Palona Account: "Haidilao"
  │
  └── Stripe Customer (cus_haidilao) ← ONE for entire account
        ├── PaymentMethods[]
        │   └── pm_corporate_card
        │
        └── Subscription (1 per account)
              └── Items:
                  ├── Store 1 base fee
                  ├── Store 1 call usage
                  ├── Store 2 base fee
                  ├── Store 2 call usage
                  └── Store 3 base fee, calls...
                    ↓
              ONE invoice with all stores aggregated
```

| Pros | Cons |
|------|------|
| Simple billing relationship | Cannot bill stores independently |
| One invoice per customer | Cannot have different payment methods per store |
| Easy credit management | Cannot send invoices to different emails per store |
| Single payment method | Stores cannot manage their own billing |

### Option B: Project-Level Billing with Complete Isolation (Recommended)

Each store gets its own Stripe Customer, providing complete isolation of payment methods, invoices, and credit balances.

```
Palona Account: "Haidilao"
  │
  ├── Downtown Store
  │     └── Stripe Customer (cus_downtown) ← Own Customer
  │           ├── email: accounting@downtown.haidilao.com
  │           ├── PaymentMethods[]
  │           │   └── pm_downtown_visa (ONLY this store's cards)
  │           ├── balance: -$50.00 (store's own credits)
  │           │
  │           └── Subscription (sub_downtown)
  │                 ├── collection_method: charge_automatically
  │                 └── Items: [base fee, call usage]
  │                       ↓
  │                 Invoice for Downtown only
  │
  ├── Airport Store
  │     └── Stripe Customer (cus_airport) ← Own Customer
  │           ├── email: ap@airport.haidilao.com
  │           ├── PaymentMethods[]
  │           │   └── pm_airport_amex (ONLY this store's cards)
  │           ├── balance: $0.00
  │           │
  │           └── Subscription (sub_airport)
  │                 ├── collection_method: send_invoice
  │                 ├── days_until_due: 45
  │                 └── Items: [base fee, call usage]
  │                       ↓
  │                 Invoice emailed to Airport accounting
  │
  └── Mall Store
        └── Stripe Customer (cus_mall) ← Own Customer
              ├── email: billing@mall.haidilao.com
              ├── PaymentMethods[]
              │   └── pm_mall_mastercard
              ├── balance: -$100.00 (store's own credits)
              │
              └── Subscription (sub_mall)
                    ├── collection_method: charge_automatically
                    └── Items: [base fee, call usage]
                          ↓
                    Invoice for Mall only
```

| Pros | Cons |
|------|------|
| Complete billing isolation per store | More Stripe Customers to manage |
| Each store manages their own payment methods | No shared credit balance across stores |
| Each store has their own credit balance | Cannot consolidate invoices |
| Different billing emails per store | Each store needs separate checkout |
| Different payment terms per store | |
| Different billing cycles per store | |
| Store accounting can't see other stores | |

### Option C: Hybrid (Configurable per Account)

Account chooses billing level; some accounts use account-level, others use project-level with complete isolation.

```
Account A (billing_level: "account")
  └── Stripe Customer (cus_account_a)
        └── Subscription (all stores)

Account B (billing_level: "project")
  ├── Store 1 → Stripe Customer (cus_store_1) → Subscription
  ├── Store 2 → Stripe Customer (cus_store_2) → Subscription
  └── Store 3 → Stripe Customer (cus_store_3) → Subscription
```

---

## Complete Isolation Architecture

### Why Complete Isolation?

For enterprise customers like Haidilao where each store has its own accounting department:

| Requirement | Shared Customer | Complete Isolation |
|-------------|-----------------|-------------------|
| Each store adds their own card | ⚠️ Cards visible to all | ✅ Cards only visible to that store |
| Each store manages their own billing | ⚠️ Needs app-level filtering | ✅ Native Stripe isolation |
| Store A can't see Store B's cards | ⚠️ Requires access control | ✅ Different Customers |
| Per-store credit balance | ❌ Shared at Customer level | ✅ Each store has own balance |
| Per-store invoice history | ⚠️ Filter by subscription | ✅ Each Customer has own invoices |
| Store-level Stripe dashboard access | ❌ Not possible | ✅ Can use Stripe Connect (future) |

### Complete Isolation Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HAIDILAO (Palona Account)                                 │
│                    billing_level: "project"                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ DOWNTOWN STORE                                                       │   │
│  │ ┌─────────────────────────────────────────────────────────────────┐ │   │
│  │ │ Stripe Customer: cus_downtown_xxxxx                             │ │   │
│  │ │ ├── email: accounting@downtown.haidilao.com                     │ │   │
│  │ │ ├── name: "Haidilao - Downtown"                                 │ │   │
│  │ │ ├── metadata: {account_id, project_id}                          │ │   │
│  │ │ │                                                               │ │   │
│  │ │ ├── PaymentMethods[] ← ISOLATED                                 │ │   │
│  │ │ │   └── pm_downtown_visa_4242                                   │ │   │
│  │ │ │                                                               │ │   │
│  │ │ ├── balance: -$50.00 (credit) ← ISOLATED                        │ │   │
│  │ │ │                                                               │ │   │
│  │ │ └── Subscription: sub_downtown                                  │ │   │
│  │ │     ├── status: active                                          │ │   │
│  │ │     ├── collection_method: charge_automatically                 │ │   │
│  │ │     └── Items: [base_price, call_price, order_price]            │ │   │
│  │ └─────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                      │   │
│  │ Downtown Manager can:                                                │   │
│  │ ✓ Add/update their card    ✓ View their invoices                    │   │
│  │ ✓ View their credit balance ✓ Cannot see other stores               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ AIRPORT STORE                                                        │   │
│  │ ┌─────────────────────────────────────────────────────────────────┐ │   │
│  │ │ Stripe Customer: cus_airport_yyyyy                              │ │   │
│  │ │ ├── email: ap@airport.haidilao.com                              │ │   │
│  │ │ ├── name: "Haidilao - Airport"                                  │ │   │
│  │ │ │                                                               │ │   │
│  │ │ ├── PaymentMethods[] ← ISOLATED (empty for invoice customers)   │ │   │
│  │ │ │                                                               │ │   │
│  │ │ ├── balance: $0.00 ← ISOLATED                                   │ │   │
│  │ │ │                                                               │ │   │
│  │ │ └── Subscription: sub_airport                                   │ │   │
│  │ │     ├── status: active                                          │ │   │
│  │ │     ├── collection_method: send_invoice                         │ │   │
│  │ │     ├── days_until_due: 45                                      │ │   │
│  │ │     └── Items: [base_price, call_price, order_price]            │ │   │
│  │ └─────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                      │   │
│  │ Airport Accounting can:                                              │   │
│  │ ✓ Receive invoices by email ✓ Pay via payment link                  │   │
│  │ ✓ View their invoice history ✓ Cannot see other stores              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ MALL STORE                                                           │   │
│  │ ┌─────────────────────────────────────────────────────────────────┐ │   │
│  │ │ Stripe Customer: cus_mall_zzzzz                                 │ │   │
│  │ │ ├── email: billing@mall.haidilao.com                            │ │   │
│  │ │ ├── PaymentMethods[]: pm_mall_mastercard_5555                   │ │   │
│  │ │ ├── balance: -$100.00 (credit)                                  │ │   │
│  │ │ └── Subscription: sub_mall (charge_automatically)               │ │   │
│  │ └─────────────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Per-Store Configuration Options

When using project-level billing, each store can have independent configuration:

### Stripe Subscription-Level Settings

| Configuration | Stripe Field | Description |
|---------------|--------------|-------------|
| Payment method type | `collection_method` | `charge_automatically` or `send_invoice` |
| Specific card | `default_payment_method` | Which card to charge (for autopay) |
| Payment terms | `days_until_due` | Days to pay (for invoice method) |
| Billing day | `billing_cycle_anchor` | Day of month billing occurs |
| Custom data | `metadata` | Store project_id, billing_email, etc. |

### Invoice-Level Overrides

| Configuration | Stripe Field | Description |
|---------------|--------------|-------------|
| Recipient email | `customer_email` | Override Customer.email for this invoice |
| Custom fields | `custom_fields` | Add store name, PO number, etc. to invoice |
| Footer | `footer` | Custom text at bottom of invoice |
| Description | `description` | Invoice description/memo |

### Example Multi-Store Configuration

```text
Account: "Big Restaurant Chain"
├── stripe_customer_id: cus_xxxxx
├── billing_level: "project"
├── email: cfo@bigchain.com (account-level contact)
│
├── Store: "Downtown Location"
│   ├── stripe_subscription_id: sub_aaa
│   ├── payment_method: autopay
│   ├── billing_email: downtown-manager@bigchain.com
│   ├── default_card: pm_visa_1234
│   └── billing_cycle_day: 1
│
├── Store: "Airport Location"
│   ├── stripe_subscription_id: sub_bbb
│   ├── payment_method: invoice
│   ├── billing_email: airport-accounting@bigchain.com
│   ├── days_until_due: 45
│   └── billing_cycle_day: 15
│
└── Store: "Mall Location"
    ├── stripe_subscription_id: sub_ccc
    ├── payment_method: invoice
    ├── billing_email: mall-ap@bigchain.com
    ├── days_until_due: 30
    └── billing_cycle_day: 1
```

---

## Data Model Changes

### Current State

```text
Account
├── stripe_customer_id  ← ONE Customer for entire account
└── current_subscription_id → AccountSubscription.external_id

AccountSubscription
├── stripe_subscription_id  ← ONE subscription for entire account
├── payment_method: autopay | invoice
└── (other fields)

ProjectSubscription
├── subscription_id → AccountSubscription.external_id
├── stripe_product_id
├── base_price_id, call_price_id, order_price_id
└── (no per-project stripe_customer_id or stripe_subscription_id)
```

### Proposed State (Complete Isolation)

```text
Account
├── stripe_customer_id: str | None  ← For account-level billing only
├── billing_level: "account" | "project"  ← NEW
├── default_payment_method: "autopay" | "invoice"  ← NEW (default for new stores)
└── current_subscription_id (for account-level billing only)

AccountSubscription (used for account-level billing only)
├── stripe_subscription_id
├── payment_method
└── (other fields, unchanged)

ProjectSubscription (enhanced for project-level billing with complete isolation)
├── subscription_id → AccountSubscription.external_id
│
│   ─── NEW: Per-Store Stripe Customer ───
├── stripe_customer_id: str | None  ← NEW: Own Stripe Customer per store
├── stripe_customer_email: str | None  ← NEW: Customer email (for invoices)
├── stripe_customer_name: str | None  ← NEW: Customer display name
│
│   ─── NEW: Per-Store Subscription ───
├── stripe_subscription_id: str | None  ← NEW: Own subscription per store
├── payment_method: "autopay" | "invoice"  ← NEW
├── days_until_due: int | None  ← NEW (default 30, for invoice method)
├── billing_cycle_day: int | None  ← NEW (1-28)
├── billing_status: "pending" | "active" | "past_due" | "canceled"  ← NEW
│
│   ─── NEW: Billing Contact ───
├── billing_email: str | None  ← NEW: Where to send invoices
├── billing_contact_name: str | None  ← NEW
├── billing_phone: str | None  ← NEW
│
│   ─── NEW: Payment Method Cache (for display) ───
├── payment_method_last4: str | None  ← NEW: "4242"
├── payment_method_brand: str | None  ← NEW: "visa"
├── payment_method_exp_month: int | None  ← NEW: 12
├── payment_method_exp_year: int | None  ← NEW: 2026
│
│   ─── NEW: Credit Balance Cache ───
├── credit_balance_cents: int | None  ← NEW: Store's credit balance
├── credit_balance_currency: str | None  ← NEW: "usd"
│
│   ─── Existing Fields ───
├── stripe_product_id
├── base_price_id, call_price_id, order_price_id
└── deleted
```

### Key Changes Summary

| Field | Location Change | Purpose |
|-------|-----------------|---------|
| `stripe_customer_id` | Account → ProjectSubscription | Each store gets own Stripe Customer |
| `stripe_subscription_id` | AccountSubscription → ProjectSubscription | Each store gets own subscription |
| `billing_email` | NEW on ProjectSubscription | Per-store invoice recipient |
| `credit_balance_cents` | NEW on ProjectSubscription | Cache of per-store credit balance |
| `payment_method_*` | NEW on ProjectSubscription | Cache card details for display |

### Migration Path

For existing accounts with `billing_level: "account"`:
- Keep `stripe_customer_id` on Account
- Keep using AccountSubscription flow
- No changes required

For new accounts with `billing_level: "project"`:
- `Account.stripe_customer_id` = NULL
- Each `ProjectSubscription.stripe_customer_id` has its own value
- Each store is completely independent

---

## Feature Matrix

| Feature | Account-Level | Project-Level (Complete Isolation) |
|---------|---------------|-----------------------------------|
| Single invoice for all stores | Yes | No |
| Separate invoice per store | No | Yes |
| Consolidated usage view | Yes | Per-store |
| Different payment method per store | No | Yes |
| Different billing email per store | No | Yes |
| Different payment terms per store | No | Yes |
| Different billing cycle per store | No | Yes |
| Consolidated credit balance | Yes | No (per-store credit) |
| Single Stripe Customer | Yes | No (one per store) |
| Store manages own payment methods | No | Yes |
| Store can't see other stores' billing | No | Yes |
| Per-store invoice history | No | Yes |

---

## Implementation Phases

### Phase 1: Invoice Payment Method (Account-Level)

Complete the existing invoice payment method support for account-level billing:

| Task | Description |
|------|-------------|
| Modify checkout flow | If `payment_method=invoice`, skip card collection |
| Create subscription correctly | Set `collection_method=send_invoice` and `days_until_due` |
| Handle webhooks | Process `invoice.finalized`, `invoice.paid`, `invoice.payment_failed` |
| Manual invoice generation | Support generating invoices on-demand via API |

### Phase 2: Project-Level Billing with Complete Isolation

| Task | Description |
|------|-------------|
| Add `billing_level` to Account | Enum: "account" (default) or "project" |
| Add Stripe Customer fields to ProjectSubscription | `stripe_customer_id`, `stripe_customer_email`, `stripe_customer_name` |
| Add billing fields to ProjectSubscription | `stripe_subscription_id`, `payment_method`, `billing_email`, `days_until_due`, etc. |
| Create Stripe Customer per project | When `billing_level=project`, create new Customer for each store |
| Create Subscription per project | Each store gets own subscription under its own Customer |
| Per-project checkout flow | Generate checkout URL per project with project's Customer |
| Per-project usage metering | Send MeterEvents with project's `stripe_customer_id` |
| Update billing details endpoints | Return per-project billing info |

### Phase 3: Per-Store Payment Method Management

| Task | Description |
|------|-------------|
| Add payment method endpoint per project | `POST /projects/{id}/payment-method/setup` returns Stripe SetupIntent URL |
| Handle SetupIntent completion webhook | Update ProjectSubscription with new payment method |
| Cache payment method details | Store last4, brand, expiry for display |
| Payment method update flow | Allow store to replace their card |
| Payment method removal | Allow store to remove card (for switching to invoice) |

### Phase 4: Per-Store Credit Management

| Task | Description |
|------|-------------|
| Grant credit to store | `POST /projects/{id}/credit` grants credit to store's Stripe Customer |
| Get store credit balance | `GET /projects/{id}/credit` returns store's balance |
| Credit history per store | `GET /projects/{id}/credit/history` returns store's credit transactions |
| Sync credit balance cache | Update `credit_balance_cents` on ProjectSubscription from webhooks |

### Phase 5: Advanced Features

| Task | Description |
|------|-------------|
| Billing cycle configuration | Allow different billing days per store |
| Invoice customization | Custom fields, footer, PO numbers per store |
| Billing reports | Per-store and account-wide billing reports |
| Migration tool | Convert account-level to project-level billing |

---

## Webhook Handling for Project-Level Billing

### Required Webhooks

| Event | Handler Action |
|-------|----------------|
| `customer.created` | Log new customer creation |
| `customer.updated` | Sync email/name changes to ProjectSubscription |
| `customer.subscription.created` | Link subscription to ProjectSubscription |
| `customer.subscription.updated` | Sync status to ProjectSubscription.billing_status |
| `customer.subscription.deleted` | Mark ProjectSubscription as canceled |
| `invoice.created` | Log invoice creation |
| `invoice.finalized` | Send notification to billing contact |
| `invoice.paid` | Update ProjectSubscription.billing_status = "active" |
| `invoice.payment_failed` | Send failure notification, update status = "past_due" |
| `payment_method.attached` | Cache card details in ProjectSubscription |
| `payment_method.detached` | Clear cached card details |
| `customer.balance_transaction.created` | Sync credit balance to ProjectSubscription |

### Webhook Lookup Flow

Since each store has its own Stripe Customer, webhook handling is straightforward:

1. Webhook receives event with `customer` field (e.g., `cus_downtown_xxxxx`)
2. Look up `ProjectSubscription` by `stripe_customer_id = event.customer`
3. Process event for that specific store
4. No ambiguity about which store the event belongs to

### Customer Metadata

When creating Stripe Customer for a store, include metadata for easy lookup:

| Metadata Key | Value | Purpose |
|--------------|-------|---------|
| `account_id` | UUID | Link back to Palona Account |
| `project_id` | UUID | Link to specific Project/Store |
| `account_name` | string | Human-readable account name |
| `project_name` | string | Human-readable store name |

---

## API Endpoints (Proposed)

### Account Billing Configuration

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/accounts/{name}/billing-config` | GET | Get account billing configuration |
| `/admin/accounts/{name}/billing-config` | PATCH | Update billing_level, default_payment_method |

### Project Billing Configuration

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/projects/{id}/billing` | GET | Get project billing configuration and status |
| `/admin/projects/{id}/billing` | PATCH | Update payment_method, billing_email, days_until_due, etc. |
| `/admin/projects/{id}/billing/checkout` | POST | Get Stripe Checkout URL for this project's subscription |

### Project Payment Methods (Complete Isolation)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/projects/{id}/payment-method` | GET | Get project's current payment method (card details) |
| `/admin/projects/{id}/payment-method/setup` | POST | Get Stripe SetupIntent URL to add/update card |
| `/admin/projects/{id}/payment-method` | DELETE | Remove payment method (switch to invoice) |

### Project Credit Management (Complete Isolation)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/projects/{id}/credit` | GET | Get project's credit balance |
| `/admin/projects/{id}/credit` | POST | Grant credit to project's Stripe Customer |
| `/admin/projects/{id}/credit/history` | GET | Get project's credit transaction history |

### Project Invoices

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/projects/{id}/invoices` | GET | List invoices for this project |
| `/admin/projects/{id}/invoices/upcoming` | GET | Preview next invoice |
| `/admin/projects/{id}/invoices/{invoice_id}` | GET | Get specific invoice details |

### Account-Wide Views (Admin Only)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/accounts/{name}/billing/summary` | GET | Aggregate billing summary across all stores |
| `/admin/accounts/{name}/billing/invoices` | GET | List all invoices across all stores |
| `/admin/accounts/{name}/billing/credits` | GET | List all credit balances across all stores |

---

## Related Documentation

- [Billing & Stripe Integration](./billing-stripe-integration.md) - Current implementation details
- [Billing Notifications](./billing-notifications.md) - Notification system for billing events
- [Architecture Overview](./architecture.md) - System architecture
