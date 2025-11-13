# Observability Strategy - Business Data Updater

## Overview

This document explains the observability strategy for the Business Data Updater system, which uses **Datadog Lambda Extension** instead of completion events for monitoring and alerting.

## Architecture Decision

### Option Selected: Datadog Lambda Extension

**Why:**
- Simpler architecture (no completion events needed)
- Better developer experience (Datadog UI > CloudWatch)
- Automatic instrumentation (traces, errors, cold starts)
- Unified monitoring with rest of infrastructure
- Easier correlation between logs, metrics, and traces

### Option Rejected: Completion Events + CloudWatch

**Why not:**
- Additional infrastructure complexity (EventBridge rules, SNS topics)
- Limited future use cases (no downstream event-driven needs)
- Inferior monitoring UX compared to Datadog
- Additional maintenance overhead

## Event Flow

```
EventBridge Scheduler
  → Discovery API Endpoint
    → Publishes Request Events (TokenRefreshRequested, MenuUpdateRequested)
      → EventBridge Routes to Lambda
        → Lambda Executes Work
          → Sends Metrics to Datadog (via extension)
          → Sends Logs to Datadog (auto-collected)
            → Datadog Monitors Alert on Failures
```

## What Gets Monitored

### Automatic (via Datadog Lambda Extension)

These metrics are collected automatically without code changes:

- Lambda invocations count
- Lambda errors count
- Lambda duration (p50, p90, p99)
- Lambda cold starts
- Memory usage
- Billed duration
- All logs (structured and unstructured)
- Distributed traces (with `@tracer.wrap()`)

### Custom Business Metrics

Sent explicitly via `statsd`:

```python
from datadog import statsd

# Success/failure tracking
statsd.increment('square.token_refresh.success', tags=['account:Restaurant ABC'])
statsd.increment('square.token_refresh.failure', tags=['error:SquareAPIError'])

# Performance tracking
statsd.histogram('square.token_refresh.duration_ms', 1234, tags=['provider:square'])

# Business metrics
statsd.increment('toast.menu_update.changes_detected')
statsd.gauge('toast.menu_update.items_updated', 5)
```

### Structured Logs

Auto-collected and indexed by Datadog:

```python
import structlog

logger = structlog.get_logger()

logger.info("token_refresh_success",
    integration_id=integration_id,
    account_name=account_name,
    duration_ms=1234)

logger.error("token_refresh_failed",
    integration_id=integration_id,
    error=str(e),
    exc_info=True)
```

## Alerting Strategy

### Datadog Monitors

**Critical Alerts:**
- Square token refresh failures > 3 in 1 hour → Slack #ops-alerts
- Toast menu update failures > 5 in 1 hour → Slack #ops-alerts
- Lambda errors > 2 in 15 minutes → Slack #ops-alerts
- DLQ message count > 0 → Slack #ops-alerts

**Warning Alerts:**
- Lambda duration p95 > 4 minutes
- No Lambda invocations in 25 hours (scheduler failure)
- Lambda cold start rate > 30%

### Alert Routing

```
Datadog Monitor Triggers
  → Slack (via Datadog Slack integration)
  → PagerDuty (for critical alerts)
  → Email (for warning alerts)
```

## Dashboards

### Main Dashboard: Business Updaters Overview

**Widgets:**
1. **Success Rate Timeseries** - Square vs Toast over last 7 days
2. **Invocation Count** - Daily invocations by service
3. **Duration Percentiles** - p50, p90, p99 over last 24 hours
4. **Error Rate** - Failure rate by error type
5. **Changes Detected** - How often menus are actually updated
6. **Cold Starts** - Cold start frequency and duration
7. **DLQ Messages** - Failed messages needing attention

### Per-Service Dashboards

**Square Token Refresher:**
- Tokens refreshed per day
- Average time until expiration
- Failure rate by error type
- API response times

**Toast Menu Updater:**
- Menu updates per day
- Changes detected rate
- Items updated distribution
- API response times

## Lambda Configuration

### Required Environment Variables

```bash
DD_API_KEY=<datadog-api-key>           # From AWS Secrets Manager
DD_SITE=datadoghq.com                  # Datadog site
DD_SERVICE=square-token-refresher      # Service name
DD_ENV=production                       # Environment (lat, stg, prd)
DD_LAMBDA_HANDLER=lambda_function.lambda_handler  # Original handler
```

### Required Layer

```
arn:aws:lambda:us-east-1:464622532012:layer:Datadog-Python312:latest
```

### Handler Change

Original:
```python
handler = lambda_function.lambda_handler
```

With Datadog:
```python
handler = datadog_lambda.handler.handler  # Datadog wrapper
```

## Code Patterns

### Lambda Handler Template

```python
import time
from datadog import statsd
from ddtrace import tracer
import structlog

logger = structlog.get_logger()

@tracer.wrap(service='square-token-refresher')
def lambda_handler(event, context):
    detail = event['detail']
    account_name = detail['account_name']
    start = time.time()

    try:
        # Do work
        result = do_work(detail)

        # Send success metrics
        statsd.increment('square.token_refresh.success',
            tags=[f'account:{account_name}', 'provider:square'])
        statsd.histogram('square.token_refresh.duration_ms',
            (time.time() - start) * 1000)

        logger.info("operation_success",
            account_name=account_name,
            duration_ms=(time.time() - start) * 1000)

        return {'statusCode': 200}

    except Exception as e:
        # Send failure metrics
        statsd.increment('square.token_refresh.failure',
            tags=[f'account:{account_name}', f'error:{type(e).__name__}'])

        logger.error("operation_failed",
            account_name=account_name,
            error=str(e),
            exc_info=True)

        raise  # Let Lambda retry
```

### Tagging Strategy

**Always include these tags:**
- `account:{account_name}` - For per-customer filtering
- `provider:{provider}` - square, toast, etc.
- `error:{ErrorType}` - For failure categorization

**Optional tags:**
- `update_type:{type}` - dining_options, full_menu
- `environment:{env}` - lat, stg, prd

## Cost Considerations

### Datadog Pricing

Datadog charges for:
- **Lambda invocations** - $0.20 per million invocations
- **Custom metrics** - $0.05 per custom metric per month
- **Logs** - $0.10 per GB ingested

### Estimated Monthly Cost

**Assumptions:**
- 20 Square token refreshes/day = 600/month
- 50 Toast menu updates/day = 1,500/month
- Total invocations: ~2,100/month

**Cost:**
- Invocations: $0.20 * 0.0021 = $0.0004/month
- Custom metrics: ~10 metrics * $0.05 = $0.50/month
- Logs: ~100 MB * $0.10 = $0.01/month

**Total: ~$0.51/month** (negligible)

## Comparison to Completion Events

| Feature | Datadog Extension | Completion Events |
|---------|-------------------|-------------------|
| **Setup complexity** | Low | High |
| **Infrastructure** | Lambda layer only | EventBridge rules, SNS topics |
| **Monitoring UX** | Excellent (Datadog) | Good (CloudWatch) |
| **Alerting** | Excellent (Datadog) | Good (SNS) |
| **Correlation** | Automatic | Manual |
| **Event-driven reactions** | No | Yes |
| **Cost** | $0.51/month | ~$0.20/month |
| **Maintenance** | Low | Medium |
| **Extensibility** | Medium | High |

## When to Use Each Approach

### Use Datadog Extension When:
- ✅ Primary need is operational monitoring
- ✅ Team already uses Datadog
- ✅ Want simpler architecture
- ✅ Value better UX over extensibility
- ✅ No downstream event-driven requirements

### Use Completion Events When:
- ✅ Need to trigger other AWS services on completion
- ✅ Building event-driven platform
- ✅ Multiple consumers need completion notifications
- ✅ Want AWS-native solution
- ✅ Future event-driven use cases planned

## For This System: Datadog Extension

**Why:**
- Square token refresh and Toast menu updates are standalone operations
- No downstream services need completion notifications
- Team values operational visibility over architectural flexibility
- Simpler system is easier to maintain
- Datadog already used for other services

## Migration Path

If future requirements need completion events:

1. Add `*Completed` event schemas
2. Update Lambda to publish completion events
3. Keep Datadog for operational monitoring
4. Use completion events only for downstream automation
5. Best of both worlds

## References

- Datadog Lambda Extension: https://docs.datadoghq.com/serverless/libraries_integrations/extension/
- Datadog Python Library: https://github.com/DataDog/datadogpy
- DDTrace (APM): https://ddtrace.readthedocs.io/
- Architecture: `.claude/docs/business_updater/ARCHITECTURE.md`
- Event Schemas: `.claude/docs/business_updater/EVENT_SCHEMAS.md`
