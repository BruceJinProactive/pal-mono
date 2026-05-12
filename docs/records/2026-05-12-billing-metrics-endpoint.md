# Billing Metrics Endpoint

**Date**: 2026-05-12
**Status**: Implemented

## Context

When sending analytics invoices from the manage app, admins must manually look up and enter call counts, reservation counts, and order amounts. Additionally, admins manually select the agent type (answering, ordering, reservation) which is error-prone. The system already has the data to surface these metrics and determine agent type automatically.

## Goal

Expose a billing metrics API endpoint that the manage app can call to pull actual usage data (calls, avg duration, reservations, orders, dollar value) for an account over a billing period. The manage app uses this to:

1. Pre-populate invoice email fields automatically
2. Determine the correct invoice template variant based on real activity

## API Endpoint


| Method | Path                                                                            | Status | Description                                               |
| ------ | ------------------------------------------------------------------------------- | ------ | --------------------------------------------------------- |
| GET    | `/v1/admin/accounts/{account_name}/billing/metrics?start_date=...&end_date=...` | 200    | Returns billing metrics for the account over a date range |


Requires `account.read` permission (same as existing billing endpoints).

### Request


| Param          | Type           | Required | Description                     |
| -------------- | -------------- | -------- | ------------------------------- |
| `account_name` | path           | Yes      | Account identifier              |
| `start_date`   | query (string) | Yes      | Billing period start (ISO date) |
| `end_date`     | query (string) | Yes      | Billing period end (ISO date)   |


### Response Schema

`BillingMetricsResponse` in `api/schemas/admin/billing.py`:

```python
class BillingMetricsResponse(BaseModel):
    account_name: str
    period_start: str
    period_end: str
    total_calls: int
    avg_call_duration_seconds: float
    total_reservations: int
    total_orders: int
    order_total_dollars: float
    template_variant: str
    template_id: int
```

## Data Sources


| Metric               | Source                  | Method                                                         |
| -------------------- | ----------------------- | -------------------------------------------------------------- |
| Total calls          | `PhoneCall` table       | `analytics_repository.get_call_metrics(...)` -> index 0        |
| Avg call duration    | `PhoneCall.duration`    | `analytics_repository.get_call_metrics(...)` -> index 1        |
| Reservations booked  | `Reservation` table     | `analytics_repository.get_conversion_summary(...)` -> index -2 |
| Orders placed (paid) | `Order` table           | `analytics_repository.get_conversion_summary(...)` -> index 2  |
| Order dollar value   | `Order.subtotal` (paid) | `analytics_repository.get_conversion_summary(...)` -> index 4  |


## Template Selection

The response includes `template_variant` and `template_id` (Postmark) derived from activity:


| Orders > 0 | Reservations > 0 | Variant                | Template ID |
| ---------- | ---------------- | ---------------------- | ----------- |
| No         | No               | `answering`            | 42569088    |
| Yes        | No               | `ordering`             | 44949422    |
| No         | Yes              | `reservation`          | 44949423    |
| Yes        | Yes              | `ordering_reservation` | 44949424    |


`SendInvoiceEmailRequest` now accepts an optional `template_id` field. When provided, `send_invoice_email_with_analytics` uses it instead of the default template.

## Files Changed

- `api/schemas/admin/billing.py` -- added `BillingMetricsResponse`, added `template_id` to `SendInvoiceEmailRequest`
- `api/routes/admin/_billing.py` -- added `get_billing_metrics()` handler, passed `template_id` to email service
- `api/routes/admin/__init__.py` -- wired up GET endpoint with `account.read` permission
- `services/subscription_service/invoice_email_service.py` -- accept optional `template_id` param
- `tests/api/routes/admin/test_billing_metrics.py` -- unit tests

