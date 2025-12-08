# Stripe Webhook Setup Guide

This document describes how to configure Stripe webhooks for billing notifications in the pal-mono system.

## Overview

The Stripe webhook integration enables automatic billing notifications when payment events occur in Stripe. The system listens for two specific webhook events:

- `invoice.payment_failed` - Triggers when a payment attempt fails
- `invoice.payment_succeeded` - Triggers when a payment is successfully processed

## Webhook Endpoint

**URL**: `https://api.palona.ai/v1/integrations/stripe/webhook`

**Method**: POST

**Authentication**: Stripe webhook signature verification

## Configuration Steps

### 1. Set Environment Variable

Add the Stripe webhook signing secret to your environment configuration:

```bash
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxx
```

**Where to get this**:
1. Go to Stripe Dashboard → Developers → Webhooks
2. Click on your webhook endpoint
3. Copy the "Signing secret" value

### 2. Register Webhook in Stripe Dashboard

1. Navigate to: https://dashboard.stripe.com/webhooks
2. Click "Add endpoint"
3. Enter the webhook URL: `https://api.palona.ai/v1/integrations/stripe/webhook`
4. Select events to listen to:
   - `invoice.payment_failed`
   - `invoice.payment_succeeded`
5. Click "Add endpoint"
6. Copy the webhook signing secret and add it to your environment variables

### 3. Environment-Specific Endpoints

**Development (LAT)**:
- URL: `https://lat-api.palona.ai/v1/integrations/stripe/webhook`

**Staging (STG)**:
- URL: `https://stg-api.palona.ai/v1/integrations/stripe/webhook`

**Production (PRD)**:
- URL: `https://api.palona.ai/v1/integrations/stripe/webhook`

## How It Works

### Event Flow

```
Stripe Event → Webhook Endpoint → Verify Signature → Extract Data →
Map Customer to Account → Create BillingEvent → Send Notification Email
```

### 1. invoice.payment_failed

**Trigger**: When Stripe fails to charge a customer's payment method.

**Payload Extracted**:
- `amount_due` - Amount that failed (in dollars)
- `currency` - Currency code (e.g., USD)
- `attempt_count` - Number of payment attempts
- `invoice_url` - Link to the invoice

**Email Sent**: Payment Failed notification to account's notification email

### 2. invoice.payment_succeeded

**Trigger**: When Stripe successfully processes a payment.

**Payload Extracted**:
- `amount_paid` - Amount successfully charged (in dollars)
- `currency` - Currency code (e.g., USD)
- `invoice_url` - Link to the invoice
- `period_start` - Billing period start date
- `period_end` - Billing period end date

**Email Sent**: Payment Succeeded notification to account's notification email

## Customer ID Mapping

The webhook handler maps Stripe customer IDs to internal account IDs:

1. Extract `customer` field from the Stripe invoice object
2. Query database: `SELECT * FROM accounts WHERE stripe_customer_id = ?`
3. If no account found, log warning and skip notification
4. If account found, proceed with notification

## Security

### Signature Verification

All incoming webhooks are verified using Stripe's signature verification:

```python
import stripe

event = stripe.Webhook.construct_event(
    payload,
    sig_header,
    STRIPE_WEBHOOK_SECRET
)
```

**Rejection Scenarios**:
- Missing `stripe-signature` header → 400 Bad Request
- Invalid signature → 400 Bad Request
- Invalid payload → 400 Bad Request

## Testing

### Local Testing with Stripe CLI

1. Install Stripe CLI: https://stripe.com/docs/stripe-cli
2. Login: `stripe login`
3. Forward events to local: `stripe listen --forward-to localhost:8000/v1/integrations/stripe/webhook`
4. Trigger test events:
   ```bash
   stripe trigger invoice.payment_failed
   stripe trigger invoice.payment_succeeded
   ```

### Testing in LAT/STG

Use Stripe Dashboard's "Send test webhook" feature:

1. Go to Stripe Dashboard → Developers → Webhooks
2. Click on your webhook endpoint
3. Click "Send test webhook"
4. Select event type and click "Send test webhook"

## Monitoring

### Logs

All webhook events are logged with the following format:

```
[Stripe Webhook] Received event: invoice.payment_failed
[Stripe Webhook] Processed invoice.payment_failed for account {account_id}
```

**Warning Logs**:
- `[Stripe Webhook] No account found for Stripe customer {customer_id}`
- `[Stripe Webhook] invoice.payment_failed missing customer ID`

**Error Logs**:
- `[Stripe Webhook] Invalid payload`
- `[Stripe Webhook] Invalid signature`
- `[Stripe Webhook] Error processing webhook: {error}`

### Stripe Dashboard Monitoring

Monitor webhook delivery in Stripe Dashboard:

1. Go to: Developers → Webhooks → [Your endpoint]
2. View recent deliveries
3. Check response codes (200 = success)
4. Retry failed deliveries manually if needed

## Troubleshooting

### Webhook not receiving events

**Check**:
1. Webhook URL is correct in Stripe Dashboard
2. Endpoint is publicly accessible (not behind firewall)
3. SSL certificate is valid
4. Selected events include `invoice.payment_failed` and `invoice.payment_succeeded`

### Signature verification failing

**Check**:
1. `STRIPE_WEBHOOK_SECRET` environment variable is set correctly
2. Using the correct signing secret for the environment
3. Not using test mode secret in production or vice versa

### No notifications being sent

**Check**:
1. Account has valid `stripe_customer_id` in database
2. Account has `notification_preferences.email_enabled = true`
3. Account has valid email in `notification_email` or `email` field
4. Postmark API key is configured correctly
5. Check application logs for errors

## Database Schema

### Required Fields

**accounts table**:
```sql
stripe_customer_id VARCHAR   -- Maps to Stripe customer
notification_preferences JSONB -- {"email_enabled": true}
notification_email VARCHAR    -- Override email for notifications
```

## API Response Codes

- `200 OK` - Webhook processed successfully
- `400 Bad Request` - Invalid signature or payload
- `500 Internal Server Error` - Server error processing webhook

## Related Documentation

- [Billing Notifications Requirements](./REQUIREMENTS_POC.md)
- [Notification Architecture](./ARCHITECTURE.md)
- [Stripe Webhook Documentation](https://stripe.com/docs/webhooks)
