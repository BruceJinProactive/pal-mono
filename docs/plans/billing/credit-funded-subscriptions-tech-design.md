# Part 2: Technical Design


|               |                                                         |
| ------------- | ------------------------------------------------------- |
| **PRD**       | `docs/plans/billing/credit-funded-subscriptions-prd.md` |
| **Author**    | @Myroslav Vozniak                                       |
| **Reviewers** |                                                         |


## Overview

We introduce a new "activate without payment method" flow that calls `stripe.Subscription.create()` directly (bypassing Stripe Checkout) with `collection_method="send_invoice"`. This creates an active Stripe subscription that generates invoices the client pays on their own terms. For credit-funded clients, Stripe auto-applies the customer balance to each invoice. For unpaid invoices, we add the outstanding amount as a line item on the next cycle's invoice, consolidating accrued debt. No new tables are required — we leverage existing models (`AccountSubscription`, `ProjectSubscription`) and Stripe-native invoicing.

## Architecture

**Services touched:** `pal-mono` (API, Services, Webhooks), `pal-manage-app` (admin UI), `pal-admin-console` (client UI)

**Data flow — Activation:**

1. Admin calls `POST /admin/accounts/{account_name}/subscriptions/{external_id}/activate`
2. Service validates account has a Stripe customer (creates one if missing)
3. For credit-funded clients, admin has already granted credits via existing `POST .../credit/grant`
4. Service calls `stripe.Subscription.create()` with `collection_method="send_invoice"`, `days_until_due=30`, project line items, and no `default_payment_method`
5. Stripe creates subscription → fires `customer.subscription.created` webhook
6. Service updates `AccountSubscription` status to `active`, stores `stripe_subscription_id`

**Data flow — End-of-cycle invoicing:**

1. At cycle end, Stripe auto-generates an invoice for the subscription (`invoice.created` event)
2. Webhook handler checks for accrued unpaid amount on the account and adds it as a line item via `stripe.InvoiceItem.create()` (attached to the draft invoice)
3. Stripe auto-applies any customer credit balance, reducing amount due
4. Invoice is finalized and sent to client (`invoice.finalized`, `invoice.sent` events)
5. If credits fully cover the invoice, Stripe marks it paid — invoice record still exists for accounting

**Data flow — Accrual:**

1. When an invoice passes its due date without payment, Stripe fires `invoice.payment_failed` or invoice remains `open`
2. On the next cycle's `invoice.created` webhook, we query Stripe for the customer's open (unpaid) invoices
3. We sum the unpaid amounts, add a "Prior balance" line item to the new draft invoice, then void the old unpaid invoices to prevent double-billing
4. The consolidated invoice now includes current charges + accrued prior debt

## API & Interfaces

### New endpoint: Activate subscription without payment method

```
POST /v1/admin/accounts/{account_name}/subscriptions/{external_id}/activate

Request:
{
  "grant_credit_amount_cents": 50000,   // optional — grant credits at activation time
  "currency": "usd"                     // optional — defaults to "usd"
}

Response (200):
{
  "external_id": "uuid",
  "status": "active",
  "stripe_subscription_id": "sub_xxx",
  "collection_method": "send_invoice",
  "message": "Subscription activated successfully"
}
```

**Auth:** Admin-only (`require_account_permission("account.billing.manage", authenticate_user)`)

**Behavior:**

- Validates subscription exists and is in `pending` status
- Validates account has a `stripe_customer_id` (or creates one)
- If `grant_credit_amount_cents` is provided, grants credit to Stripe customer balance before subscription creation
- Collects line items from all associated `ProjectSubscription` entries (base, call, order prices)
- Calls `stripe.Subscription.create()` with:
  - `customer`: account's `stripe_customer_id`
  - `items`: project price line items
  - `collection_method`: `"send_invoice"`
  - `days_until_due`: `30`
  - `payment_settings.payment_method_types`: `["card", "us_bank_account"]`
  - `metadata`: `{ subscription_external_id, account_id }`
- Updates `AccountSubscription`: `status=active`, `stripe_subscription_id=sub_xxx`, `payment_method=invoice`
- Updates all linked `ProjectSubscription` entries with `stripe_subscription_id`
- Sends `BillingEventType.SUBSCRIPTION_ACTIVATED` notification

### Existing endpoints — no changes needed


| Endpoint                                      | Notes                                             |
| --------------------------------------------- | ------------------------------------------------- |
| `POST .../credit/grant`                       | Already grants credits to Stripe customer balance |
| `GET .../credit`                              | Already returns credit balance                    |
| `GET .../billing/invoices`                    | Already lists Stripe invoices                     |
| `PATCH .../billing/payment-method`            | Already switches autopay/invoice                  |
| `POST .../subscriptions/{external_id}/cancel` | Works as-is for send_invoice subs                 |


## Data Model

### No new tables required

The existing schema supports this feature:


| Model                 | Field                    | Change                                                    |
| --------------------- | ------------------------ | --------------------------------------------------------- |
| `AccountSubscription` | `payment_method`         | Already has `PaymentMethod.invoice` enum value            |
| `AccountSubscription` | `stripe_subscription_id` | Set during activation (currently only set after Checkout) |
| `AccountSubscription` | `status`                 | Transitions `pending` → `active` at activation            |
| `ProjectSubscription` | `stripe_subscription_id` | Set during activation                                     |


### Stripe configuration (no DB changes)

The Stripe subscription object carries the billing configuration:

- `collection_method = "send_invoice"` — Stripe sends invoice instead of auto-charging
- `days_until_due = 30` — client has 30 days to pay
- `payment_settings.payment_method_types = ["card", "us_bank_account"]` — enables card and ACH on the hosted invoice page

## Implementation Details

### 1. New service function: `activate_subscription_without_payment_method()`

**File:** `services/subscription_service/_subscription.py`

```python
def activate_subscription_without_payment_method(
    session: Session,
    context: UserContext,
    account_id: uuid.UUID,
    external_id: uuid.UUID,
    grant_credit_amount_cents: int | None = None,
    currency: str = "usd",
) -> db.AccountSubscription:
    """
    Activate a pending subscription by creating a Stripe subscription
    directly (no Checkout), with collection_method="send_invoice".
    """
```

Steps:

1. Retrieve `AccountSubscription` by `external_id`, validate status is `pending`
2. Retrieve `Account`, validate `stripe_customer_id` exists
3. If `grant_credit_amount_cents`, call `grant_credit_to_account()`
4. Collect line items from linked `ProjectSubscription` entries
5. Call `stripe.Subscription.create()` (new function in `_stripe_subscription.py`)
6. Update `AccountSubscription`: status → `active`, set `stripe_subscription_id`, `payment_method` → `invoice`
7. Update each `ProjectSubscription` with `stripe_subscription_id`
8. Send activation notification
9. Return updated subscription

### 2. New Stripe function: `create_subscription_direct()`

**File:** `services/subscription_service/_stripe_subscription.py`

```python
def create_subscription_direct(
    stripe_customer_id: str,
    line_items: list[dict[str, Any]],
    metadata: dict[str, str],
    days_until_due: int = 30,
    coupon_id: str | None = None,
    trial_end: int | None = None,
) -> stripe.Subscription:
    """
    Create a Stripe subscription directly via API (no Checkout).
    Uses send_invoice collection method — no payment method required.
    """
```

Calls `stripe.Subscription.create()` with:

- `customer`, `items`, `collection_method="send_invoice"`, `days_until_due`
- `payment_settings={"payment_method_types": ["card", "us_bank_account"]}`
- `metadata` (includes `subscription_external_id`)
- Optional `coupon`, `trial_end`

### 3. Webhook enhancement: Accrued balance on `invoice.created`

**File:** `api/routes/integrations/stripe/_implementation.py`

Add handler for `invoice.created` event (currently unhandled):

```python
async def _handle_invoice_created(
    event_data: dict[str, Any], async_session: AsyncSession
) -> None:
    """
    When Stripe creates a new subscription invoice (draft), check for
    unpaid prior invoices and roll their amounts into this invoice.
    """
```

Steps:

1. Extract `customer`, `subscription`, `id` from the invoice object
2. Skip if not a subscription invoice (i.e., `subscription` is null)
3. Query Stripe for open invoices on this customer: `stripe.Invoice.list(customer=X, status="open")`
4. Filter to invoices from the same subscription that are past due
5. Sum unpaid amounts
6. If accrued amount > 0:
  - Call `stripe.InvoiceItem.create()` with description "Prior unpaid balance" and the accrued amount, attached to the new draft invoice
  - Void the old unpaid invoices to prevent double-billing
7. Log the accrual for audit

### 4. Disable dunning/auto-cancellation

**Stripe Dashboard configuration** (not code):

- Set Smart Retries to disabled for `send_invoice` subscriptions
- Set subscription status after all retries fail to: **leave as-is** (do not cancel)

**Code:** No changes needed — `should_block_calls_async()` already does NOT block on `past_due` or `unpaid` statuses.

## Frontend Changes

### pal-manage-app (Admin Portal)

**1. Activate subscription dialog** — `SubscriptionsTab.tsx` + new `ActivateSubscriptionDialog.tsx`

- "Activate" button on pending subscriptions (replaces current "Create Checkout" as primary action)
- Dialog shows: current credit balance, optional field to grant credits at activation, plan name/fee
- Calls `POST .../subscriptions/{externalId}/activate`
- Add `activateSubscription()` to `api.ts`

**2. Invoice list section** — new `InvoiceListSection.tsx` on subscriptions tab

- Table of recent invoices: number, status badge (paid/open/void), amount, due date, hosted URL link
- Open/unpaid invoices highlighted with warning styling
- Add `getAccountInvoices(accountName, status?)` to `api.ts`

**3. Unpaid balance summary** — `SubscriptionsTab.tsx`

- Warning card showing total outstanding across open invoices: "Unpaid balance: $X.XX across N invoices"
- Derived from invoice list data (sum `amount_due` where `status === 'open'`)

**4. Subscription card badge** — `SubscriptionCard.tsx`

- Show "Invoice" or "Credit-funded" badge based on `payment_method` and credit balance
- Distinguishes autopay vs send_invoice subscriptions at a glance

### pal-admin-console (Client Portal)

**1. Remove "Add Credit Card" for invoice subscriptions** — `CurrentSubscriptionDisplay.tsx`

- When `payment_method === 'invoice'` and `stripe_subscription_id` is set, hide the "Add Credit Card" CTA
- Show instead: "Invoices will be sent at the end of each billing cycle"

**2. "Pay Now" on open invoices** — `InvoiceListCard.tsx`

- Add "Pay Now" button on invoices with `status === 'open'` — links to `hosted_invoice_url`
- Stripe's hosted page handles card/ACH payment and saving payment methods
- For paid invoices covered by credits ($0 due), show "Paid via credits" label

**3. Outstanding balance banner** — `CurrentSubscriptionDisplay.tsx`

- When open invoices exist, show: "You have an outstanding balance of $X.XX. This will be included in your next invoice."
- Fetch via existing invoice data or new `fetchInvoices(accountName, 'open')` in `actions.ts`

**4. Billing cycle wording** — `BillingCycleCard.tsx`

- When `payment_method === 'invoice'`: "Next invoice date" instead of "Next billing date"
- Add note: "Payment due within 30 days of invoice"

## Error Handling


| Failure                                                               | Behavior                                                                           |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Account has no `stripe_customer_id`                                   | Return 400 with message to create Stripe customer first                            |
| No `ProjectSubscription` entries (no line items)                      | Return 400 — subscription needs at least one project with pricing                  |
| `stripe.Subscription.create()` fails                                  | Return 500 with Stripe error; subscription stays `pending` — safe to retry         |
| Credit grant fails                                                    | Return 500; do not proceed with activation (credits must land first)               |
| `invoice.created` webhook — Stripe API error adding accrued line item | Log error, allow invoice to proceed without accrual (manual follow-up)             |
| `invoice.created` webhook — void of old invoice fails                 | Log error, skip void (accrued item still added; admin resolves duplicate manually) |
| Subscription already `active`                                         | Return 409 Conflict — idempotency guard                                            |


## Testing

- **Unit: `activate_subscription_without_payment_method()`**
  - Pending subscription → creates Stripe sub → status becomes `active`
  - With `grant_credit_amount_cents` → credits granted before Stripe sub creation
  - Subscription not in `pending` status → raises error
  - Account missing `stripe_customer_id` → raises error
  - No project subscriptions / line items → raises error
- **Unit: `create_subscription_direct()`**
  - Correct params passed to `stripe.Subscription.create()` (mock Stripe)
  - `collection_method="send_invoice"`, `days_until_due=30` always set
  - Coupon and trial_end passed through when provided
- **Unit: `_handle_invoice_created()` webhook**
  - No prior unpaid invoices → no accrual line item added
  - Prior unpaid invoices exist → accrued amount added, old invoices voided
  - Non-subscription invoice → skipped
- **Unit: Existing webhook handlers**
  - `customer.subscription.created` still correctly maps status for `send_invoice` subscriptions
  - `invoice.payment_succeeded` works for credit-funded invoices ($0 remaining)
  - `invoice.payment_failed` logs but does not suspend service
- **STG validation:**
  1. Create account + Stripe customer
  2. Grant $500 credit to account
  3. Create subscription (pending)
  4. Call activate endpoint
  5. Verify: subscription is `active`, Stripe subscription exists with `collection_method="send_invoice"`
  6. Verify: first invoice created, credits applied, invoice marked paid
  7. Wait for next cycle (or simulate) → new invoice generated
  8. Verify: credit-funded invoice exists with $0 due (accounting record)
  9. Test unpaid flow: create subscription without credits, let invoice go unpaid
  10. Verify: next cycle invoice includes "Prior unpaid balance" line item
- **Existing flows:**
  - Stripe Checkout activation still works (no regression)
  - Autopay subscriptions unaffected
  - Credit grant endpoint still works independently
  - Cancel subscription works for `send_invoice` subscriptions

## Rollout

**Deploy order:**

1. **pal-mono: Service layer** — add `create_subscription_direct()` and `activate_subscription_without_payment_method()` (no external impact until endpoint is wired)
2. **pal-mono: Webhook handler** — add `invoice.created` handler with accrual logic (safe — currently unhandled, no existing behavior changes)
3. **pal-mono: API endpoint** — wire up `POST .../activate` admin endpoint
4. **Stripe Dashboard** — configure dunning settings to not auto-cancel `send_invoice` subscriptions
5. **pal-manage-app** — activate dialog, invoice list, unpaid balance summary (separate PR)
6. **pal-admin-console** — remove card CTA for invoice subs, "Pay Now" button, outstanding balance banner, billing cycle wording (separate PR)

**Monitoring:**

- Alert on `stripe.Subscription.create()` failures (new error path)
- Dashboard: count of `send_invoice` vs `charge_automatically` subscriptions
- Dashboard: open/unpaid invoices by age
- Log: accrual events (how often prior balance is rolled into new invoices)
- Existing: `BillingEventType.SUBSCRIPTION_ACTIVATED` notifications still fire

**Rollback:**

- **API endpoint**: disable route — subscriptions already activated remain active in Stripe, no harm
- **Webhook handler**: remove `invoice.created` accrual logic — invoices generate normally without accrual consolidation; unpaid invoices stay open separately (admin handles manually)
- **Stripe subscriptions**: can be cancelled individually via existing admin cancel endpoint if needed
- No database migrations to roll back

