# Billing System — Gap Milestone Plan

**Created:** 2026-04-17  
**Purpose:** Actionable task breakdown for closing gaps between current implementation and spec.

---

## What Already Exists

Before planning, here is what we can build on:

- Stripe integration (subscriptions, webhooks, customer management)
- `SubscriptionPlan`, `AccountSubscription`, `ProjectSubscription`, `CreditGrant` tables
- `AccountStatus` and `SubscriptionStatus` enums with suspension states
- Webhook handlers for invoice/payment/subscription events
- Admin billing endpoints (generate invoice, list invoices, finalize, void, send email)
- Postmark email integration for 6 billing event types
- Invoice email service with usage analytics
- Coupon management (assign/remove per account/project)
- `should_block_calls_async()` for call blocking on expired subscriptions
- `ChangeLog` table for audit trail
- Credit grant tracking (but no consumption ledger)

---

## Milestone 1: Dunning & Automated Enforcement

**Goal:** Failed payments trigger internal retry scheduling, escalating notifications, and automatic suspension/cancellation — not just Stripe-side dunning.

**Priority:** CRITICAL — this is the largest gap and blocks revenue protection.

### Tasks

#### M1.1 — Internal Dunning State Machine

- Create `BillingEvent` table to log all billing state transitions (payment attempts, status changes, admin overrides) as an immutable audit trail
- Create `DunningSchedule` table with configurable retry/notification timing per account (default: Day 1/3/5 retries, Day 0/3/7/10 notifications)
- Build dunning orchestrator service (`services/billing_enforcement_service/`) that:
  - Listens to `invoice.payment_failed` webhook
  - Creates a dunning schedule for the failed invoice
  - Schedules retry attempts and notification events

#### M1.2 — Store Status State Machine

- Implement `StoreStatusMachine` enforcing: Trial -> Active -> PastDue -> Suspended -> Cancelled
- On `invoice.payment_failed`: transition store to `past_due`
- On grace period expiry (default 10 days): transition to `suspended`
- On 30 days unpaid: transition to `cancelled`
- On `invoice.payment_succeeded` while past_due/suspended: transition back to `active`
- Wire state transitions to `BillingEvent` audit log

#### M1.3 — Configurable Billing Parameters

- Create `BillingConfig` table (or account-level JSONB) for admin-configurable parameters:
  - `grace_period_days` (default 10, range 7-14)
  - `retry_schedule` (default [1, 3, 5])
  - `suspension_threshold_days` (default 10, range 7-30)
  - `cancellation_threshold_days` (default 30, range 14-60)
- Admin API endpoints to read/update billing config per account
- Wire dunning orchestrator to read config per account

#### M1.4 — Dunning Notifications

- Create Postmark templates for missing notification types:
  - Past due reminder (Day 3)
  - Final warning before suspension (Day 7)
  - Suspension notice (Day 10)
  - Cancellation notice (Day 30)
  - Reactivation confirmation
- Add `BillingEventType` entries: `PAST_DUE_REMINDER`, `FINAL_WARNING`, `SUSPENSION_NOTICE`, `CANCELLATION_NOTICE`, `REACTIVATION_CONFIRMATION`
- Wire dunning orchestrator to send notifications on schedule
- Include in every dunning message: amount due, store(s) impacted, payment link, suspension/cancellation date

#### M1.5 — SMS Notifications

- Integrate Twilio (or equivalent) for SMS sending
- Add SMS channel to billing notifications per spec:
  - Payment failed: Email + SMS
  - Final warning: Email + SMS
  - Suspension notice: Email + SMS
  - Reactivation: Email + SMS
- Respect account notification preferences for SMS opt-in/out

---

## Milestone 2: Suspension Enforcement & Reactivation

**Goal:** Suspended stores are actually locked out; payment immediately restores access.

**Priority:** HIGH — without enforcement, suspension is meaningless.

### Tasks

#### M2.1 — Suspension Enforcement

- Update `should_block_calls_async()` to check `AccountStatus.suspended` and `past_due` (not just cancelled/expired)
- Add API middleware or guard that returns 403 for suspended store API calls
- Forward calls to voicemail/backup number when store is suspended (coordinate with voice/agent team)

#### M2.2 — Automatic Reactivation

- On `invoice.payment_succeeded` webhook: if store is `suspended` or `past_due`, transition to `active`
- Resume AI answering immediately
- Restore API access
- Send reactivation confirmation (Email + SMS)

#### M2.3 — Admin Override Endpoints

- `POST /admin/accounts/{id}/billing/suspend` — force-suspend a store
- `POST /admin/accounts/{id}/billing/unsuspend` — force-unsuspend with optional expiration
- `POST /admin/accounts/{id}/billing/extend-grace` — extend grace period for specific account
- `POST /admin/accounts/{id}/billing/waive-invoice/{invoice_id}` — waive invoice with audit log
- `POST /admin/accounts/{id}/billing/retry-payment/{invoice_id}` — manual payment retry
- All overrides logged to `BillingEvent` audit trail

---

## Milestone 3: Customer Self-Service Portal

**Goal:** Store owners can manage billing without contacting support.

**Priority:** HIGH — reduces support load, improves experience.

### Tasks

#### M3.1 — Payment Method Management

- `GET /billing/payment-methods` — list saved cards/bank accounts from Stripe
- `POST /billing/payment-methods` — add new card or bank account (Stripe SetupIntent flow)
- `DELETE /billing/payment-methods/{id}` — remove a payment method
- `POST /billing/payment-methods/{id}/default` — set as default
- RBAC: only store Admins can add/edit/remove payment methods

#### M3.2 — Invoice & Receipt Access

- `GET /billing/invoices` — customer-facing invoice list (current + historical)
- `GET /billing/invoices/{id}/pdf` — download invoice/receipt PDF
- `POST /billing/invoices/{id}/pay` — one-click pay outstanding balance (create Stripe PaymentIntent)

#### M3.3 — Store Status & Usage Dashboard

- `GET /billing/status` — current store status with clear next-step messaging
- `GET /billing/usage` — real-time usage (calls handled, credit balance, projected spend, overage)
- Show "Account Suspended" banner data when applicable (return in status response)

#### M3.4 — Billing RBAC

- Define billing-specific permissions: `billing:read`, `billing:write`, `billing:admin`
- Store Admins: full billing access
- Store Users: read-only (view invoices, usage)
- Enforce in billing endpoint guards

---

## Milestone 4: Credit Ledger & Usage Metering

**Goal:** Accurate credit tracking with FIFO consumption, spending caps, and usage alerts.

**Priority:** MEDIUM — builds on existing `CreditGrant` table.

### Tasks

#### M4.1 — Credit Ledger Enhancement

- Add `credit_type` to credit tracking: `plan`, `rollover`, `bonus`
- Add `expiration` field for time-limited credits
- Implement FIFO consumption logic (oldest credits consumed first)
- Track credit balance changes in ledger entries (debit/credit)

#### M4.2 — Spending Caps

- Add `spending_cap` field to account/project config (default $200 soft cap)
- Admin endpoint to configure spending cap per store
- Enforce soft cap: alert at threshold, optionally block at hard cap

#### M4.3 — Usage Threshold Alerts

- Monitor usage against plan quota in real-time
- Send notifications at 50%, 80%, 100% of quota:
  - 50% and 80%: Email only
  - 100%: Email + SMS
- Admin-configurable thresholds

---

## Milestone 5: Corporate & MSA Billing

**Goal:** Multi-store accounts with consolidated invoicing and volume discounts.

**Priority:** MEDIUM — needed for enterprise customers.

### Tasks

#### M5.1 — MSA Support

- Add `msa_enabled` flag to Account
- When MSA is active: all stores under account share the same plan
- Allow different payment methods per store even under MSA

#### M5.2 — Consolidated Invoicing

- Generate single consolidated invoice per Account (rolling up all store charges)
- Invoice shows per-store line item breakdown
- Support both consolidated and per-store invoicing modes

#### M5.3 — Multi-Location Discounts

- Implement discount tiers based on store count (per Billing Strategy doc)
- Auto-recalculate discount when stores are added/removed
- Apply discount as Stripe coupon or line item adjustment

#### M5.4 — Annual Billing

- Support annual billing cycle with upfront payment
- Monthly credit loading for annual plans
- Prorated upgrades/downgrades mid-cycle

#### M5.5 — Promo Code Engine

- Extend existing coupon system to support:
  - Credit grants (one-time bonus)
  - Percentage/fixed discounts with duration
  - Stacking rules (which promos can combine)

---

## Milestone 6: Admin Dashboard & Internal Reporting

**Goal:** Billing ops team has full visibility and control.

**Priority:** MEDIUM — operational need grows with customer count.

### Tasks

#### M6.1 — Billing Dashboard Aggregation

- `GET /admin/billing/dashboard` — aggregated view:
  - MRR (total, by tier, by segment)
  - Store count by status (active, past_due, suspended, cancelled)
  - Outstanding invoice total
- Filterable by account, tier, status, date range

#### M6.2 — Internal Reporting Endpoints

- Failed payment rate (% of invoices failing on first attempt)
- Recovery rate (% of failed payments recovered via dunning)
- Churn from suspension (stores cancelled due to non-payment)
- Overage revenue breakdown
- Discount impact analysis

#### M6.3 — Audit Log Viewer

- `GET /admin/billing/audit-log` — searchable billing event log
- Filter by account, event type, date range
- Includes: payment events, status changes, admin overrides, payment method changes

#### M6.4 — Admin Billing Controls (remaining)

- Edit billing cycle date for a store
- Set custom pricing per store
- Temporary reactivation with expiration date

---

## Milestone 7: Security & Fraud

**Goal:** Harden billing against abuse and ensure compliance.

**Priority:** MEDIUM-LOW — important but lower urgency than revenue-impacting features.

### Tasks

#### M7.1 — Stripe Radar Integration

- Enable Stripe Radar for fraud scoring on payments
- Handle `radar.early_fraud_warning` webhook events
- Auto-flag accounts with high-risk payments

#### M7.2 — Custom Fraud Rules

- Payment method velocity checks (rapid add/remove of cards)
- Chargeback monitoring: auto-flag accounts with chargebacks
- Rate limiting on payment retries and billing API endpoints

#### M7.3 — Anomalous Access Detection

- Track login IP/device/geolocation for billing portal access
- Alert on unusual login patterns (new IP, new device, impossible travel)
- Admin alerts on suspicious account activity

#### M7.4 — Compliance Verification

- PCI DSS validation (confirm no raw card data flows through pal-mono)
- NACHA compliance review for ACH transactions
- Encryption audit (at rest AES-256, in transit TLS 1.2+)
- Penetration testing on billing endpoints

---

## Milestone Dependency Graph

```
M1 (Dunning & Enforcement)
 |
 v
M2 (Suspension & Reactivation)  -- depends on M1 state machine
 |
 +---> M3 (Customer Portal)     -- depends on M2 for status display
 |
 +---> M4 (Credit Ledger)       -- independent, can parallel with M3
 |
 v
M5 (Corporate/MSA)              -- depends on M1-M3 being stable
 |
 v
M6 (Admin Dashboard)            -- depends on M1 audit log, benefits from M4-M5 data
 |
 v
M7 (Security & Fraud)           -- can start in parallel with M5-M6
```

---

## Suggested Implementation Order


| Order | Milestone                     | Est. Tasks | Rationale                       |
| ----- | ----------------------------- | ---------- | ------------------------------- |
| 1     | M1: Dunning & Enforcement     | ~15        | Revenue protection, biggest gap |
| 2     | M2: Suspension & Reactivation | ~8         | Makes M1 meaningful             |
| 3     | M3: Customer Portal           | ~10        | Reduces support load            |
| 4     | M4: Credit Ledger & Usage     | ~7         | Accuracy for billing            |
| 5     | M5: Corporate/MSA             | ~8         | Enterprise readiness            |
| 6     | M6: Admin Dashboard           | ~8         | Ops visibility                  |
| 7     | M7: Security & Fraud          | ~8         | Hardening                       |


**Total estimated tasks:** ~64

---

## Notes

- Each milestone can be broken into individual PAL-* tasks in Notion
- M1 and M2 are the critical path — everything else builds on them
- M3 and M4 can run in parallel once M2 is stable
- M5-M7 are less interdependent and can be prioritized based on customer demand
- Existing Stripe webhook infrastructure means M1 is mostly new business logic, not new integrations

