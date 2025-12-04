# Billing Notifications Architecture

## Goals

Follow the SMART framework: Specific, Measurable, Achievable, Relevant, and Time-bound.

- [x]  Design infra
- [ ]  Modify **`accounts`** table to support notification preferences
- [ ]  Introduce event types (triggers)
- [ ]  Create Postmark templates
- [ ]  Add integration points (Stripe webhooks, subscription service events)
- [ ]  Finalize the pipeline
- [ ]  Add setter for notification preferences in admin-console/manage-app

### Version Roadmap

- **v1  PoC:** prove that the system can send the **right email to the right account** for the most important billing events.
- **v2  Production:** have a **reliable, observable, idempotent notification system** for all billing-related events.
- **v3  Advanced:** make notifications **user-aware, multi-channel, and measurable.**

---

## V1 - POC

[Admin User Email Notifications V1 Requirements Doc](./REQUIREMENTS_POC.md)

**Goal:**

Prove that the system can send the **right email to the right account** for the most important billing events

**Objectives:**

- Wire **Stripe webhooks** and **subscription service events** to Postmark.
- Support **4 email types**:
    - SubscriptionActivated
    - SubscriptionCancelled
    - PaymentFailed
    - PaymentSucceeded
- Keep it **simple**: no EventBridge, no throttling, no SMS, no scheduled jobs.

**Success looks like:**

- For a test account, you can trigger a Stripe payment fail / success and see the correct email.

### The Flow

```
Source ’ BillingEvent object ’ handleBillingEvent ’ Postmark
```

### Table Changes

**`accounts`** (extend existing table)

```sql
notification_preferences: JSONB (default: {"email_enabled": true})
notification_email: String (nullable, override)
```

### Event type definitions

Stripe webhooks and subscription service will both construct a `BillingEvent` and call `handleBillingEvent(event)`.

```python
type BillingEventType =
  | 'SubscriptionActivated'
  | 'SubscriptionCancelled'
  | 'PaymentFailed'
  | 'PaymentSucceeded';

interface BillingEvent {
  type: BillingEventType;
  accountId: string;
  payload: Record<string, any>;
}
```

### Integration Points - What They Do and Why

#### **Stripe Webhooks**

These are **external triggers from Stripe** that tell us something happened with billing. In v1, we care about two simple but critical ones.

##### `invoice.payment_failed`

- Fired when Stripe cannot charge the customer.
- We look up `account_id` ’ send **PaymentFailed** email.
- Email tells user: payment failed, update card, view invoice.

##### `invoice.payment_succeeded`

- Fired when a payment goes through.
- We send **PaymentSucceeded** email.
- Email confirms payment and links to the invoice.

#### **Subscription Service Events:**

These are **internal triggers from our own code**  they represent product-level changes, not Stripe raw events.

##### `create_account_subscription()` ’ `SubscriptionActivated`

- Triggered when we successfully create a new subscription.
- User gets **SubscriptionActivated** email with plan name, price, and next steps.

##### `cancel_subscription()` ’ `SubscriptionCancelled`

- Triggered when user cancels their plan.
- User gets **SubscriptionCancelled** email showing:
    - When access ends
    - How to reactivate

### Postmark

For v1 we use **one template per event**:

1. **SubscriptionActivated**
    - "Your subscription is active"
    - Variables: `plan_name`, `price`, `trial_end`, `billing_url`
2. **SubscriptionCancelled**
    - "Your subscription has been cancelled"
    - Variables: `plan_name`, `cancel_effective_date`, `billing_url`
3. **PaymentFailed**
    - "We couldn't process your payment"
    - Variables: `amount_due`, `attempt_count`, `invoice_url`, `billing_url`
4. **PaymentSucceeded**
    - "Payment received"
    - Variables: `amount_paid`, `invoice_url`, `period_start`, `period_end`

Each template's purpose is clear and aligned to one action ’ one email.

---

## V2 - Production Ready (EventBridge, Scheduling, Throttling, Retries)

**Goal:**

Have a **reliable, observable, idempotent notification system** for all billing-related events.

**Objectives:**

- Introduce **EventBridge (or Pub/Sub)** as the event bus.
- Add **scheduled jobs** for:
    - Trial ending / trial ended
    - Quota warning / exceeded
    - Card expiring soon
- Add **Notification Orchestrator + Workers**:
    - Orchestrator consumes `billing.*` events ’ writes `notifications` rows.
    - Workers pull from DB ’ send via Postmark (and later Twilio).
- Implement:
    - **Throttling & dedup** via `notification_key` + `event_id`.
    - **Retries** using `retry_count` + `next_retry_at`.
- Expand event coverage to your full billing state model.

**Success looks like:**

- No duplicate emails/SMS from retries or flapping events.
- You can answer "Who got what, when, and on which channel?" from the DB.
- You can safely replay events without spamming users.

---

## V3 - Advanced (SMS, Preferences, Template Grouping, Analytics)

**Goal:**

Make notifications **user-aware, multi-channel, and measurable.**

**Objectives:**

- Add **SMS (Twilio)** for critical notifications (suspension, final payment failure, blocked calls).
- Fully honor **notification preferences**:
    - Per-channel, later maybe per-type.
- **Group templates** to reduce Postmark template sprawl:
    - Trial, PaymentIssue, PaymentSuccess, UsageAlert, AccountChanges, CriticalAlert.
- Add basic **analytics / dash**:
    - Delivery success rates
    - Failures per type
    - Possibly per-tenant reporting

**Success looks like:**

- Users aren't surprised or spammed.
- Support/ops has a simple way to see notification health.
- You can change messaging by editing templates instead of code.
