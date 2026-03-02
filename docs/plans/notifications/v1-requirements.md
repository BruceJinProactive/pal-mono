# Admin User Email Notifications V1 Requirements Doc

## 1. Overview

V1 implements a **minimal billing notification system** that sends the **right email to the right account** for key subscription + payment events.

No EventBridge, no SMS, no scheduled jobs, no notifications DB.

Everything is synchronous and email-only via Postmark.

---

## 2. Goals

**Primary Goal**

> Prove that the system can send the right email to the right account for the most important billing events.

**V1 Objectives**

- Wire **Stripe webhooks** and **subscription service events** to Postmark via a shared `BillingEvent` handler.
- Support **4 email types**:
    - `SubscriptionActivated`
    - `SubscriptionCancelled`
    - `PaymentFailed`
    - `PaymentSucceeded`
- Add **account-level notification settings**:
    - `notification_email` override
    - `email_enabled` preference
- Add a **setter in admin-console** to edit these preferences.

**Success Criteria**

- For a test account, triggering:
    - `invoice.payment_failed` / `invoice.payment_succeeded` in Stripe
    - `create_account_subscription()` / `cancel_subscription()` in the app

        results in the correct email being sent to the expected email address.

- Admins can enable/disable billing emails and override the recipient email per account.

---

## 3. Scope (V1)

**In Scope**

- Email notifications only (Postmark).
- Stripe ’ webhook ’ internal event ’ email.
- Subscription service ’ internal event ’ email.
- Account-level notification preferences.
- Admin-console UI to manage those preferences.

**Out of Scope (explicitly NOT in V1)**

- Notifications database (`notifications` table).
- EventBridge / message bus.
- Throttling / deduplication.
- Retries / background workers.
- SMS / Twilio.
- Scheduled jobs (trial, quota, expiry).

---

## 4. Data Model

### 4.1 `accounts` table changes

Add:

```sql
notification_preferences JSONB NOT NULL DEFAULT '{"email_enabled": true}',
notification_email TEXT NULL
```

**Semantics**

- `notification_preferences.email_enabled`:
    - `true` (default): send billing emails.
    - `false`: **do not send** any billing notifications for this account.
- `notification_email`:
    - If set ’ use as recipient for billing emails.
    - If null ’ fallback to `accounts.email`.

Effective recipient:

```tsx
recipient = account.notification_email ?? account.email;
```

If `recipient` is empty ’ skip sending and log.

---

## 5. Event Model (Code-Level)

### 5.1 Event Types

```tsx
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

### 5.2 Central Handler

All integration points must construct a `BillingEvent` and call:

```tsx
async function handleBillingEvent(event: BillingEvent): Promise<void>;
```

V1 implementation:

```tsx
// Pseudocode
async function handleBillingEvent(event: BillingEvent) {
  await sendBillingEmail(event);
}
```

---

## 6. Flow

**Global V1 flow:**

> Source ’ BillingEvent ’ handleBillingEvent ’ sendBillingEmail ’ Postmark

Where **sources** are:

- Stripe webhooks
- Subscription service methods

---

## 7. Integration Points (Behavior)

### 7.1 Stripe Webhooks

### `invoice.payment_failed`

- Trigger: Stripe cannot charge the customer.
- Behavior:
    - Map Stripe `customer` ’ `accountId`.
    - Build:

        ```tsx
        event = {
          type: 'PaymentFailed',
          accountId,
          payload: {
            amount_due,
            currency,
            attempt_count,
            invoice_url,
          }
        }
        ```

    - Call `handleBillingEvent(event)`.

### `invoice.payment_succeeded`

- Trigger: An invoice is paid successfully.
- Behavior:
    - Map `customer` ’ `accountId`.
    - Build:

        ```tsx
        event = {
          type: 'PaymentSucceeded',
          accountId,
          payload: {
            amount_paid,
            currency,
            invoice_url,
            period_start,
            period_end,
          }
        }
        ```

    - Call `handleBillingEvent(event)`.

---

### 7.2 Subscription Service Events

### `create_account_subscription()` ’ `SubscriptionActivated`

- Trigger: Successful subscription creation (Stripe + DB).
- Behavior:
    - Build:

        ```tsx
        event = {
          type: 'SubscriptionActivated',
          accountId,
          payload: {
            plan_name,
            price,
            currency,
            trial_end,      // optional
          }
        }
        ```

    - Call `handleBillingEvent(event)`.

### `cancel_subscription()` ’ `SubscriptionCancelled`

- Trigger: User or admin cancels subscription (Stripe + DB).
- Behavior:
    - Build:

        ```tsx
        event = {
          type: 'SubscriptionCancelled',
          accountId,
          payload: {
            plan_name,
            cancel_effective_date,
          }
        }
        ```

    - Call `handleBillingEvent(event)`.

---

## 8. Email Sending Logic (V1)

### 8.1 `sendBillingEmail(event: BillingEvent)`

Responsibilities:

1. Load account.
2. Check preferences.
3. Resolve recipient.
4. Map event ’ Postmark template + variables.
5. Call Postmark API.
6. Handle simple errors (log only).

Pseudocode:

```tsx
async function sendBillingEmail(event: BillingEvent) {
  const account = await loadAccount(event.accountId);
  if (!account) return;

  const prefs = (account.notification_preferences ?? {}) as { email_enabled?: boolean };
  const emailEnabled = prefs.email_enabled ?? true;
  if (!emailEnabled) return;

  const recipient = account.notification_email ?? account.email;
  if (!recipient) {
    log.warn('No recipient email for account', { accountId: account.id });
    return;
  }

  const { templateId, templateVariables } = mapEventToTemplate(event, account);

  try {
    await postmark.sendEmailWithTemplate({
      To: recipient,
      TemplateId: templateId,
      TemplateModel: templateVariables,
    });
  } catch (err) {
    log.error('Failed to send billing email', { event, err });
  }
}
```

---

## 9. Postmark Templates

For V1, define **one template per event type**:

1. **SubscriptionActivated**
    - Subject: "Your subscription is now active"
    - Variables: `account_name`, `plan_name`, `price_formatted`, `trial_end`, `billing_url`
2. **SubscriptionCancelled**
    - Subject: "Your subscription has been cancelled"
    - Variables: `account_name`, `plan_name`, `cancel_effective_date`, `billing_url`
3. **PaymentFailed**
    - Subject: "We couldn't process your payment"
    - Variables: `account_name`, `amount_due_formatted`, `attempt_count`, `invoice_url`, `billing_url`
4. **PaymentSucceeded**
    - Subject: "Payment received"
    - Variables: `account_name`, `amount_paid_formatted`, `invoice_url`, `period_start`, `period_end`

Template IDs are stored in config, e.g.:

```tsx
const POSTMARK_TEMPLATES = {
  SubscriptionActivated: 'xxxxx',
  SubscriptionCancelled: 'yyyyy',
  PaymentFailed: 'zzzzz',
  PaymentSucceeded: 'aaaaa',
};
```

---

## 10. Admin Console Requirements

- On account detail page, show & edit:
    - `notification_email` (text field, optional)
    - `notification_preferences.email_enabled` (checkbox)
- UX:
    - Checkbox label example: "Send billing emails to this account"
    - Helper: "If notification email is empty, we'll use the main account email."

API (example):

- `PATCH /admin/accounts/:id/notifications`

Body:

```json
{
  "notification_email": "billing@acme.com",
  "notification_preferences": {
    "email_enabled": true
  }
}
```

---

## 11. Error Handling (V1)

- If Stripe webhook cannot map `customer` ’ `accountId`:
    - Log error; do not send email.
- If account has **no email** (no `notification_email` and no `email`):
    - Log warning; do not send email.
- If Postmark returns an error:
    - Log error; no retries in V1.
