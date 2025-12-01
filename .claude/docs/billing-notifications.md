# Billing Notifications System

## Overview

The billing notifications system provides automated, multi-channel notifications for critical billing events including trial management, payment processing, usage quotas, and account status changes.

## Architecture

### High-Level Flow

```
Trigger Sources → EventBridge → Notification Service → Delivery Channels
     ↓              ↓                   ↓                     ↓
- Stripe       Events with      - Throttling          - Email (primary)
- Scheduled    billing event    - Deduplication       - SMS (critical)
- Business     schemas          - Preferences         - In-app (future)
  Logic                         - Template rendering
                                - Logging
```

### Components

#### 1. Trigger Sources

**Stripe Webhooks** (`/api/webhooks/stripe`)
- Real-time payment and subscription lifecycle events
- Events: `invoice.payment_failed`, `invoice.payment_succeeded`, `customer.subscription.updated`, etc.
- Webhook signature verification for security
- Publishes EventBridge events for notification handling

**Scheduled Jobs** (Cron-based)
- `trial_ending_checker`: Daily at 9 AM UTC - Finds trials ending in 3 days
- `trial_expired_checker`: Daily at 10 AM UTC - Detects expired trials
- `usage_quota_checker`: Every 6 hours - Monitors quota thresholds (80%, 100%)
- `card_expiry_checker`: Daily at 8 AM UTC - Alerts for cards expiring in 30/7/1 days
- `suspended_account_followup`: Daily at 11 AM UTC - Sends reminders to suspended accounts
- `grace_period_enforcer`: Daily at 12 PM UTC - Blocks calls for overages without payment

**Business Logic Events**
- Triggered during normal operations (credit grants, plan changes, manual suspensions)
- Published directly to EventBridge from service layer

#### 2. EventBridge Integration

All billing events flow through AWS EventBridge for decoupled, event-driven architecture.

**Event Schema** (`events/schema.py`):
```python
@dataclass
class TrialEndingSoonEvent(BaseEvent):
    detail_type: ClassVar[str] = "billing.TrialEndingSoon"
    account_id: UUID
    account_name: str
    trial_end_date: datetime
    days_remaining: int
    subscription_plan_name: str
```

**Complete Event Types**:
- `billing.TrialEndingSoon` / `billing.TrialEnded`
- `billing.PaymentFailed` / `billing.PaymentSucceeded`
- `billing.SubscriptionActivated` / `billing.SubscriptionCancelled`
- `billing.PlanChanged`
- `billing.UsageQuotaWarning` / `billing.UsageQuotaExceeded`
- `billing.CreditGranted`
- `billing.AccountSuspended` / `billing.AccountReactivated`
- `billing.PaymentMethodExpiring`

#### 3. Notification Service

Core orchestration layer (`services/notification_service/`).

**Key Functions**:
- **Event routing**: Maps EventBridge events to notification types
- **Throttling**: Prevents notification spam with configurable windows
- **Deduplication**: Prevents duplicate notifications from multiple triggers
- **Preference checking**: Respects user notification settings
- **Template rendering**: Builds messages with dynamic variables
- **Channel selection**: Routes to appropriate delivery channel (email/SMS/in-app)
- **Retry handling**: Exponential backoff for failed deliveries
- **Audit logging**: Comprehensive tracking in `notifications` table

**Service Structure**:
```
notification_service/
├── _implementation.py       # Main NotificationService class
├── _event_handlers.py       # EventBridge event handlers
├── _email_builder.py        # Email template rendering
├── _sms_builder.py          # SMS message formatting
├── _throttle.py             # Throttling logic
├── _deduplication.py        # Duplicate detection
└── _delivery.py             # Channel delivery coordination
```

#### 4. Delivery Channels

**Email (Primary)** - via Postmark
- All notifications (informational, warnings, critical)
- Template-based with variable substitution
- Open and click tracking enabled
- Branded design with clear CTAs
- Retry logic: 3 attempts (5min, 1hr, 6hr delays)

**SMS (Critical Only)** - via Twilio
- Payment failures (final retry), account suspensions, call blocking
- Max 160 characters with shortened links
- Requires explicit opt-in (TCPA compliance)
- Rate limit: 3 SMS per day per account
- Includes opt-out mechanism

**In-App (Future)**
- Supplementary to email/SMS
- Real-time via WebSocket
- Notification center UI with badge counts

## Data Model

### notifications (New Table)
Complete audit trail of all notification attempts. This is the only new table required.

```sql
- id: UUID (PK)
- account_id: UUID (FK → accounts.id)
- notification_type: Enum (trial_ending_soon, trial_ended, payment_failed,
                          payment_succeeded, usage_quota_warning, usage_quota_exceeded,
                          credit_granted, account_suspended, account_reactivated,
                          plan_changed, subscription_cancelled, card_expiring)
- channel: Enum (email, sms, in_app)
- recipient: String (email address or phone number)
- trigger_event_id: String (EventBridge event ID for deduplication)
- template_id: String (Postmark/Twilio template ID, hardcoded in service)
- template_variables: JSONB (data used for template rendering)
- status: Enum (pending, sent, failed, throttled, skipped)
- status_details: String (error messages, provider responses)
- provider_message_id: String (Postmark MessageID or Twilio SID)
- sent_at: Timestamp
- retry_count: Integer (default: 0)
- next_retry_at: Timestamp (null if not retrying)
- metadata: JSONB ({
    "delivered_at": timestamp,
    "opened_at": timestamp,
    "clicked_at": timestamp,
    "last_sent_similar": timestamp  // For throttling checks
  })
- created_at: Timestamp
- updated_at: Timestamp

-- Indexes for performance
CREATE INDEX idx_notifications_account_type_sent
  ON notifications(account_id, notification_type, sent_at DESC)
  WHERE status = 'sent';

CREATE INDEX idx_notifications_dedup
  ON notifications(account_id, notification_type, created_at DESC);

CREATE INDEX idx_notifications_retry
  ON notifications(next_retry_at)
  WHERE status = 'pending' AND next_retry_at IS NOT NULL;
```

### accounts (Extended Existing Table)
Add notification preference columns to existing `accounts` table instead of creating a new table.

```sql
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS:
- notification_email: String (nullable, override primary contact email)
- notification_phone: String (nullable, for SMS, E.164 format)
- notification_preferences: JSONB DEFAULT '{"email": true, "sms": false}'
```

**Notes:**
- All notification types enabled by default (email: true, sms: false for non-critical)
- Critical notifications (payment_failed, account_suspended, usage_quota_exceeded) always send regardless of preferences
- Per-type preferences can be added later if needed via JSONB updates
- Quiet hours and timezone can be added to the JSONB when required

### Template Management (Code-based, No Table)
Template IDs are hardcoded in the notification service configuration:

```python
# services/notification_service/_templates.py
NOTIFICATION_TEMPLATES = {
    NotificationType.TRIAL_ENDING_SOON: {
        "email_template_id": "trial-ending-soon",  # Postmark template alias
        "sms_template": "Your Palona trial ends in {days} days. Add card: {url}",
        "priority": NotificationPriority.MEDIUM
    },
    NotificationType.PAYMENT_FAILED: {
        "email_template_id": "payment-failed",
        "sms_template": "Payment failed. Update card to avoid service interruption: {url}",
        "priority": NotificationPriority.HIGH
    },
    NotificationType.ACCOUNT_SUSPENDED: {
        "email_template_id": "account-suspended",
        "sms_template": "Your Palona account is suspended. Pay now: {url}",
        "priority": NotificationPriority.CRITICAL
    },
    # ... more templates
}
```

### Throttling (Query-based, No Table)
Throttling is implemented by querying `notifications` with proper indexes:

```python
def check_throttle(account_id: UUID, notification_type: NotificationType) -> tuple[bool, str]:
    """
    Check if notification should be throttled based on recent send history.
    Returns: (should_send, reason)
    """
    throttle_rules = {
        NotificationType.TRIAL_ENDING_SOON: timedelta(days=3),
        NotificationType.TRIAL_ENDED: timedelta(days=1),
        NotificationType.PAYMENT_FAILED: timedelta(hours=24),
        NotificationType.USAGE_QUOTA_WARNING: timedelta(hours=24),
        NotificationType.CARD_EXPIRING: timedelta(days=7),
        # payment_succeeded, credit_granted: No throttling
    }

    throttle_window = throttle_rules.get(notification_type)
    if not throttle_window:
        return (True, "No throttling")

    last_sent = db.query(Notification).filter(
        Notification.account_id == account_id,
        Notification.notification_type == notification_type,
        Notification.status == 'sent',
        Notification.sent_at > (now() - throttle_window)
    ).order_by(Notification.sent_at.desc()).first()

    if last_sent:
        return (False, f"Throttled: Last sent {last_sent.sent_at}")

    return (True, "Throttle check passed")
```

## Key Scenarios

### 1. Trial Ending Flow

**3 Days Before Trial Ends**:
- **Trigger**: Scheduled job checks `trial_end_date`
- **Event**: `billing.TrialEndingSoon`
- **Notification**: Email with CTA to add payment method
- **Frequency**: Once per trial (throttled)

**Trial Expires**:
- **Trigger**: Scheduled job or status change
- **Event**: `billing.TrialEnded`
- **Logic**: Check if payment method exists on Stripe customer
  - **With card**: "Processing first payment" email
  - **Without card**: "Add card to continue" email with urgency
- **Business Impact**: Account call blocking (see `should_block_calls` in subscription service)

### 2. Payment Failure Flow

**First Failure**:
- **Trigger**: Stripe webhook `invoice.payment_failed`
- **Event**: `billing.PaymentFailed(attempt_number=1)`
- **Notification**: Email - "Payment failed, we'll retry in 3 days"
- **Tone**: Reassuring, access remains active
- **Subscription**: Stays `active`

**Second Failure (Final Retry)**:
- **Event**: `billing.PaymentFailed(attempt_number=2)`
- **Notification**: Email + SMS - "Update card within 2 days to avoid suspension"
- **Tone**: Urgent but helpful
- **Business Logic**: 2-day grace period starts

**Grace Period Expires**:
- **Trigger**: Scheduled `grace_period_enforcer` job
- **Event**: `billing.AccountSuspended`
- **Actions**:
  - Update `account.status = 'suspended'`
  - Update `subscription.status = 'expired'`
  - Block all calls
- **Notification**: Email + SMS - "Account suspended - Payment required"

**Payment Succeeds After Retry**:
- **Trigger**: Stripe webhook `invoice.payment_succeeded`
- **Event**: `billing.AccountReactivated` (if was suspended)
- **Actions**:
  - Restore `account.status = 'active'`
  - Unblock calls
- **Notification**: "Welcome back! Account reactivated"

### 3. Usage Quota Flow

**80% Quota Reached**:
- **Trigger**: Usage checker job or real-time meter event
- **Event**: `billing.UsageQuotaWarning(percentage_used=80)`
- **Notification**: Email - "Approaching call quota" with upgrade options
- **Frequency**: Once per billing cycle per threshold

**100% Quota Exceeded**:
- **Event**: `billing.UsageQuotaExceeded`
- **Logic Branches**:

  **With Payment Method**:
  - Email - "Overage charges will apply ($X per call)"
  - Show estimated charge
  - Continue service normally

  **Without Payment Method**:
  - Email + SMS - "Add card to continue service"
  - Grant 3-day grace period
  - Daily reminders
  - After grace period: Block calls, send suspension notification

### 4. Card Expiry Flow

**30/7/1 Days Before Expiry**:
- **Trigger**: Daily `card_expiry_checker` job
- **Event**: `billing.PaymentMethodExpiring`
- **Notification**: Email with card details (brand, last4, expiry)
- **Frequency**: At each threshold (30d, 7d, 1d)

### 5. Credit Granted Flow

**Sources**: Plan activation, admin grant, referral

- **Trigger**: `grant_credit_to_account()` in subscription service
- **Event**: `billing.CreditGranted(reason, issued_by)`
- **Notification**: Email - "You've received $X credit!"
- **Content**: Shows new balance, explains automatic application

### 6. Plan Change Flow

- **Trigger**: `switch_subscription_plan()` in subscription service
- **Event**: `billing.PlanChanged`
- **Notification**: Email with side-by-side comparison
- **Content**:
  - Features gained/lost
  - Price change
  - Prorated amount (credit or charge)
  - Effective date

### 7. Subscription Cancellation Flow

- **Trigger**: `cancel_subscription()` or Stripe webhook
- **Event**: `billing.SubscriptionCancelled`
- **Notification**: Email explaining:
  - Access continues until end of billing period
  - Data retention policy
  - Reactivation process

## Throttling & Deduplication

### Throttling Rules

Prevents notification spam during cascading failures.

| Notification Type | Max Frequency | Window |
|-------------------|---------------|--------|
| trial_ending_soon | 1 per 3 days | Per trial |
| trial_ended | 1 per day | Ongoing |
| payment_failed | 1 per attempt | Per billing cycle |
| payment_retry | 1 per day | Ongoing |
| payment_succeeded | Unlimited | N/A |
| usage_quota_warning | 1 per threshold | Per billing cycle |
| card_expiring | 1 per week | Per expiry period |
| account_suspended | 1 immediate + 1/day | Ongoing |

**Implementation**: Query `notifications` with indexed lookups to check recent send history.

### Deduplication

Prevents duplicates from multiple trigger sources (webhook + scheduled job).

**Strategy**:
- Use EventBridge `event_id` as deduplication key
- Check `notifications` for recent matching notifications
- Deduplication window: 1 hour for real-time events, 24 hours for scheduled

## Integration Points

### Stripe Webhooks

**Endpoint**: `POST /api/webhooks/stripe`

**Required Webhook Events**:
- `invoice.payment_succeeded` → Payment receipt
- `invoice.payment_failed` → Payment failure notification
- `invoice.upcoming` → 7-day advance notice of charge
- `customer.subscription.updated` → Plan changes
- `customer.subscription.deleted` → Cancellation
- `customer.subscription.trial_will_end` → 3-day trial warning
- `payment_method.attached` → Check if should unblock calls
- `payment_method.detached` → Payment method removed warning

**Security**: Signature verification using `stripe.Webhook.construct_event()` with webhook secret.

**Idempotency**: Check `event.id` in logs before processing to prevent duplicate handling.

### Subscription Service

**Publish Events From**:
- `create_account_subscription()` → SubscriptionActivated
- `handle_stripe_checkout_success()` → SubscriptionActivated + CreditGranted
- `grant_credit_to_account()` → CreditGranted
- `switch_subscription_plan()` → PlanChanged
- `cancel_subscription()` → SubscriptionCancelled
- `update_account()` (status change) → AccountSuspended / AccountReactivated

### Usage Billing Service

**Integration Points**:
- After `send_meter_event()`: Check if threshold crossed
- In `get_usage_metrics()`: Calculate percentage for warnings

### Email Service

**Current**: Postmark integration (`services/email_service/`)

**Enhancement Needed**:
- Create Postmark templates for each notification type (in Postmark dashboard)
- Define template IDs in notification service code (`_templates.py`)
- Pass template variables from notification service to email service

## Error Handling

### Retry Strategy

**Email Retries**:
- Attempt 1: Immediate
- Attempt 2: 5 minutes later
- Attempt 3: 1 hour later
- Attempt 4: 6 hours later
- After max retries: Mark failed, alert ops team

**SMS Retries**: Same strategy, but max 2 retries (cost consideration)

### Fallback Mechanisms

1. **Template Fallback**:
   - Primary: Postmark template via API
   - Fallback: Plain text template from DB
   - Last resort: Hardcoded message

2. **Delivery Fallback**:
   - Failed emails: Log to admin dashboard for manual follow-up
   - Failed SMS: Queue for later delivery
   - Critical notifications: Alert ops team via monitoring system

3. **Data Enrichment Fallback**:
   - Stripe API fails: Use cached data from last successful fetch
   - Missing variables: Use sensible defaults, log warning

## Monitoring

### Key Metrics

**Operational**:
- Delivery rate by type (target: >98% email, >95% SMS)
- Average delivery time (target: <5min critical, <30min others)
- Failure rate by provider (target: <2%)
- Retry success rate (target: >80%)

**Engagement**:
- Email open rate (target: >40% critical, >25% informational)
- Email click rate on CTAs (target: >15%)
- SMS opt-out rate (target: <5%)

**Business Impact**:
- Payment recovery rate after notifications
- Churn reduction from proactive notifications
- Support ticket reduction for billing issues

### Alerts

- Delivery rate drops below 95%
- Failures exceed 10/hour
- Critical notification fails to send
- Webhook processing lag > 5 minutes

## Compliance

### CAN-SPAM Act (Email)
- ✅ Physical address in footer
- ✅ Clear "From" name (Palona)
- ✅ Accurate subject lines
- ✅ Unsubscribe link (non-transactional only)
- ✅ Exception: Transactional billing emails exempt from opt-out

### TCPA (SMS)
- ✅ Explicit consent required before sending
- ✅ Opt-in checkbox separate from other agreements
- ✅ Opt-out instructions in every SMS ("Reply STOP")
- ✅ Honor opt-out within 10 business days (FCC Opt-Out Rule effective April 2025)
- ✅ Maintain consent records for 4 years

### GDPR (EU Users)
- ✅ Data minimization: Only store necessary data
- ✅ Right to access: Users can request notification history
- ✅ Right to deletion: Cascade delete notification logs
- ✅ Purpose limitation: Contact info only for stated purposes

## Implementation Phases

### Phase 1: Foundation (Weeks 1-2)
- Create `notifications` table with indexes
- Extend `accounts` table with notification preference columns
- Define event schemas (top 5 scenarios)
- Build notification service core (throttling, deduplication, logging)
- Create 5 Postmark templates in dashboard
- Implement Stripe webhook endpoint
- Trial ending + payment notifications

### Phase 2: Payment Lifecycle
- Complete payment failure → suspension flow
- Grace period enforcement
- Card expiry notifications
- Plan change notifications
- Subscription cancellation notifications

### Phase 3: Usage Quotas
- Usage quota checker job
- Quota warning notifications (80%, 100%)
- Overage notification logic
- No-card + overage flow with call blocking

### Phase 4: SMS & Preferences
- Twilio SMS integration
- SMS opt-in flow
- Critical alert SMS templates
- Notification preferences API
- Quiet hours support

### Phase 5: Production Ready
- Retry worker for failed notifications
- Monitoring & alerting
- Admin dashboard for notifications
- Performance optimization
- Load testing

### Phase 6: Future Enhancements
- In-app notifications
- Webhook notifications for third-party integrations
- A/B testing for templates
- ML-based predictive alerts
- Multi-language support

## API Endpoints

### Admin Endpoints (Future)

```
GET    /admin/accounts/{account_name}/notifications
       List notification history

GET    /admin/accounts/{account_name}/notifications/preferences
       Get notification preferences

PATCH  /admin/accounts/{account_name}/notifications/preferences
       Update notification preferences

POST   /admin/accounts/{account_name}/notifications/{id}/retry
       Manually retry failed notification

GET    /admin/notifications/stats
       System-wide notification metrics
```

## Testing

### Unit Tests
- Throttling logic with various time windows
- Deduplication with overlapping events
- Template variable extraction from events
- Email/SMS message building
- Retry logic with exponential backoff

### Integration Tests
- Webhook signature verification
- Stripe API interactions (test mode)
- Postmark email sending (test server)
- EventBridge event publishing
- Database transactions

### End-to-End Tests
- Full payment failure → suspension flow
- Trial ending → card added → activation flow
- Usage quota → overage → payment flow
- Plan change complete flow
- Webhook → event → notification → delivery

## Configuration

### Environment Variables

```bash
# Email
POSTMARK_SERVER_TOKEN=xxx

# SMS (when implemented)
TWILIO_ACCOUNT_SID=xxx
TWILIO_AUTH_TOKEN=xxx
TWILIO_PHONE_NUMBER=+1xxx

# Stripe
STRIPE_WEBHOOK_SECRET=whsec_xxx

# EventBridge
EVENT_BUS_NAME=pal-mono-events

# Notification Service
NOTIFICATION_RETRY_MAX_ATTEMPTS=3
NOTIFICATION_THROTTLE_WINDOW_HOURS=24
```

### Feature Flags (Future)

```bash
ENABLE_SMS_NOTIFICATIONS=false
ENABLE_IN_APP_NOTIFICATIONS=false
ENABLE_NOTIFICATION_WEBHOOKS=false
```

## Troubleshooting

### Common Issues

**Notifications not sending**:
1. Check `notifications` table for status and error details
2. Verify throttling hasn't blocked send (query recent `notifications` for same type)
3. Check if account has notification preferences disabled (query `accounts.notification_preferences`)
4. Verify Postmark/Twilio credentials are valid

**Duplicate notifications**:
1. Check deduplication logic is enabled
2. Verify EventBridge event IDs are being logged
3. Review scheduled job timing (may overlap with webhooks)

**Stripe webhooks not processing**:
1. Verify webhook signature secret is correct
2. Check webhook endpoint is publicly accessible
3. Review Stripe dashboard for failed webhook attempts
4. Verify event types are subscribed in Stripe dashboard

**SMS not delivering**:
1. Verify user has SMS enabled in preferences
2. Check phone number format (E.164)
3. Verify Twilio account has sufficient balance
4. Check SMS rate limiting hasn't been exceeded

## Future Enhancements

### Priority 1 (Next Quarter)
- In-app notification center UI
- Notification preferences self-service (customer portal)
- Advanced usage forecasting ("You'll exceed quota on X date")

### Priority 2 (Future)
- A/B testing for email templates
- Multi-language support
- Custom notification webhooks for enterprise customers
- Notification analytics dashboard
- Smart send-time optimization (ML-based)

## Related Documentation

- [Architecture Overview](.claude/docs/architecture.md)
- [Subscription Service](../services/subscription_service/)
- [Event System](../events/)
- [Email Service](../services/email_service/)
