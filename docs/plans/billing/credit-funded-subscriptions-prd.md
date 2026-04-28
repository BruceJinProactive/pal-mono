# Part 1: PRD


|                   |                   |
| ----------------- | ----------------- |
| **Author**        | @Myroslav Vozniak |
| **Status**        | Draft             |
| **Approver**      |                   |
| **Approval Date** |                   |


## Problem

Two issues with the current billing flow:

1. **No payment-method-free activation path.** Subscriptions can only become active through Stripe Checkout, which requires a payment method. Select clients — particularly credit-funded ones — should be able to have fully active subscriptions without providing a card or bank account upfront. The credit infrastructure exists (Stripe customer balance, `grant_credit_balance()`, `CreditGrant` model, recurring credits) but there is no activation path that bypasses the payment method requirement.
2. **No end-of-cycle invoice model.** The current flow is autopay-first — we charge the card on file automatically at the start of each cycle. We need every active subscription to generate an invoice at the end of each billing cycle that the client can pay via their chosen method (credit card, ACH, or credits). For credit-funded clients, the invoice must still be created for accounting purposes even though it's auto-covered by the credit balance. For unpaid accounts, the owed amount should accrue and carry forward to the next billing cycle's invoice.

**Who's affected:**

- **Sales/Account Management** — cannot onboard clients without requiring a payment method upfront
- **Credit-funded clients** — blocked from using the platform until they add a card they don't need
- **Finance/Accounting** — missing invoice records for credit-funded usage; no end-of-cycle invoice trail for accounting
- **All clients** — no option to receive an invoice and pay via their preferred method

## Goal

1. Enable select clients to have fully active subscriptions without requiring a payment method at activation.
2. Every active subscription should generate an invoice at the end of each billing cycle — the client then pays via their chosen method (credit card, ACH, or credits).
3. For credit-funded clients, the invoice is automatically covered by their credit balance, but the invoice still needs to exist for accounting purposes.
4. For accounts that are unpaid, the owed amount should accrue and the accrued amount will be billed to the customer in the next billing cycle.

## Requirements

**Must have:**

*Activation without payment method:*

- Admin can activate a subscription directly (bypassing Stripe Checkout) without requiring a payment method on file
- For credit-funded clients, credits are granted to the Stripe customer balance before or at the time of activation
- Stripe subscription is created via API (`stripe.Subscription.create()`) without requiring a payment method
- Subscription transitions to `active` in both Stripe and our database upon creation

*End-of-cycle invoicing:*

- Every active subscription generates an invoice at the end of each billing cycle showing line items, any credits applied, and the amount due
- Invoices are sent to the client (via Stripe hosted invoice page and/or email) so they can pay via their chosen method
- Clients can pay via credit card or ACH
- Clients can save their preferred payment method for future invoices (stored on the Stripe customer)
- If a client has credit balance, Stripe auto-applies it to the invoice before any remaining amount is due
- For credit-funded clients, the invoice must still be generated even when fully covered by credits — this is required for accounting purposes

*Accrual of unpaid amounts:*

- Service is never suspended or cancelled due to nonpayment
- If an invoice goes unpaid, the owed amount accrues on the account
- The accrued amount is included in the next billing cycle's invoice, consolidating prior unpaid amounts with the current cycle's charges

*Webhook compatibility:*

- Existing webhook handlers correctly process subscription lifecycle events (no special-casing needed if Stripe sends standard events)

**Nice to have:**

- Warning/notification when a credit-funded account's balance is running low (won't cover the next invoice)
- Admin visibility into credit-funded vs card-funded subscriptions (flag or filter)
- Admin dashboard showing outstanding unpaid invoices and accrued balances across accounts
- Audit log entry when a subscription is activated without a payment method

## User Flow

**Activation (no payment method required):**

1. Admin creates a subscription for an account via the existing admin endpoint (selecting a plan)
2. For credit-funded clients, admin grants credits to the account's Stripe customer balance (via existing credit grant functionality)
3. Admin triggers the new "activate without payment method" action on the pending subscription
4. System calls `stripe.Subscription.create()` directly with the account's Stripe customer and configured products/prices — no payment method required
5. Subscription becomes `active` immediately
6. Webhook fires `customer.subscription.updated` with status `active`; our handler updates the DB subscription to `active`

**End-of-cycle invoicing (all subscriptions):**

1. At the end of each billing cycle, Stripe generates an invoice with all line items (base fee, usage charges, etc.)
2. If the account has any accrued unpaid amount from prior cycles, it is included in this invoice
3. If the account has credit balance, Stripe auto-applies it to reduce the amount due
4. Invoice is sent to the client via Stripe hosted invoice page / email with a pay button
5. Client pays the remaining amount via credit card or ACH
6. Client can choose to save their payment method during payment for future invoices
7. If credits fully cover the invoice, it is marked paid with $0 due — no action needed from client, but the invoice record exists for accounting

**Unpaid invoices and accrual:**

1. If a client does not pay an invoice, the subscription remains active — no suspension or cancellation
2. The unpaid amount accrues on the account
3. Next billing cycle, the accrued amount is rolled into the new invoice alongside the current cycle's charges
4. Admin can view outstanding invoices and accrued balances, and follow up manually

## Out of Scope

- Building a self-service portal for clients to manage their own credits
- Changes to the coupon/promotion system
- Usage-based billing changes (metering continues to work as-is)

## Success Metrics

- **100% of select subscriptions activate without a payment method** — no manual Stripe dashboard workarounds needed
- **Invoice generated for every active subscription** at the end of each billing cycle — including credit-funded accounts (for accounting purposes)
- **Accrued unpaid amounts correctly roll into the next cycle's invoice** — no lost or orphaned charges
- **Zero service disruptions** due to nonpayment — no subscriptions suspended or cancelled for unpaid invoices
- **Zero regression** in the existing Checkout-based activation flow (still available for clients who prefer it)

