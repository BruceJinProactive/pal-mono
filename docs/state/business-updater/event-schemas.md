# Event Schemas - Business Data Updater

> **Last updated:** 2025-03-01

## Overview

This document defines all event schemas used in the business data updater system. All events follow the `BaseEvent` pattern defined in `/events/schema.py` and are published to the `pal-main-event-bus` EventBridge bus.

**Observability Approach:** This architecture uses Datadog for monitoring and alerting, NOT completion events. Lambda functions send metrics and structured logs directly to Datadog via the Lambda extension layer.

## Event Conventions

### Base Event Structure

All events inherit from `BaseEvent`:

```python
@dataclass
class BaseEvent:
    detail_type: ClassVar[str]  # Must be defined in subclass

    def to_detail(self) -> Dict[str, Any]:
        """
        Convert event to EventBridge detail format.
        Handles UUID and datetime serialization automatically.
        """
        ...
```

### Event Naming Convention

**Pattern:** `{domain}.{entity}.{action}`

**Examples:**
- `integration.square.TokenRefreshRequested`
- `integration.toast.MenuUpdateRequested`
- `catering.RequestCreated`

### Event Types

**Request Events:**
- Trigger work to be performed
- Published by API discovery endpoints
- Consumed by Lambda functions
- Naming: `*Requested` or `*Created`

**Note:** This architecture does NOT use Completion events. Observability is handled by Datadog Lambda extension.

### Common Fields

All events should include:
- **Entity IDs:** UUID fields for resources (integration_id, project_id, etc.)
- **Timestamps:** When event occurred (requested_at, completed_at)
- **Metadata:** Additional context (requested_by, duration_ms, etc.)

## Square Token Refresher Events

### SquareTokenRefreshRequested

**DetailType:** `integration.square.TokenRefreshRequested`

**Purpose:** Triggers a Lambda function to refresh a Square OAuth token

**Published By:** `/api/routes/internal/scheduled.py` discovery endpoint

**Consumed By:** `square-token-refresher` Lambda function

**Schema:**

```python
@dataclass
class SquareTokenRefreshRequested(BaseEvent):
    detail_type: ClassVar[str] = "integration.square.TokenRefreshRequested"

    # Resource identifiers
    integration_id: UUID
    account_id: UUID
    account_name: str

    # Configuration
    secret_key: str  # AWS Secrets Manager key for integration credentials
    days_threshold: int  # How many days before expiration to refresh

    # Current state
    current_expires_at: datetime  # When the current token expires

    # Metadata
    requested_at: datetime  # When this refresh was requested
    requested_by: str = "scheduler"  # Who triggered: "scheduler" or "manual"
```

**EventBridge JSON Example:**

```json
{
  "version": "0",
  "id": "12345678-1234-1234-1234-123456789012",
  "detail-type": "integration.square.TokenRefreshRequested",
  "source": "pal-mono",
  "account": "123456789012",
  "time": "2025-01-12T02:00:15Z",
  "region": "us-east-1",
  "resources": [],
  "detail": {
    "integration_id": "a1b2c3d4-e5f6-4a5b-9c8d-7e6f5a4b3c2d",
    "account_id": "f1e2d3c4-b5a6-4c5d-8e7f-6a5b4c3d2e1f",
    "account_name": "Restaurant ABC",
    "secret_key": "pal/lat/square/restaurant-abc-pos",
    "days_threshold": 7,
    "current_expires_at": "2025-01-15T18:30:00Z",
    "requested_at": "2025-01-12T02:00:15Z",
    "requested_by": "scheduler"
  }
}
```

**Lambda Handler Pattern:**

```python
import time
from datadog import statsd
from ddtrace import tracer
import structlog

logger = structlog.get_logger()

@tracer.wrap(service='square-token-refresher')
def lambda_handler(event, context):
    detail = event['detail']

    integration_id = detail['integration_id']
    account_id = detail['account_id']
    account_name = detail['account_name']
    secret_key = detail['secret_key']

    start = time.time()

    try:
        # Get credentials from Secrets Manager
        credentials = secrets_client.get_secret_value(SecretId=secret_key)

        # Refresh token with Square
        new_token_data = refresh_square_token(credentials)

        # Update via internal API
        update_integration_credentials(integration_id, new_token_data)

        # Send success metrics to Datadog
        statsd.increment('square.token_refresh.success',
            tags=[f'account:{account_name}', 'provider:square'])
        statsd.histogram('square.token_refresh.duration_ms',
            (time.time() - start) * 1000,
            tags=['provider:square'])

        logger.info("token_refresh_success",
            integration_id=integration_id,
            account_id=account_id,
            account_name=account_name,
            duration_ms=(time.time() - start) * 1000)

        return {'statusCode': 200}

    except Exception as e:
        # Send failure metrics to Datadog
        statsd.increment('square.token_refresh.failure',
            tags=[f'account:{account_name}', f'error:{type(e).__name__}'])

        logger.error("token_refresh_failed",
            integration_id=integration_id,
            account_id=account_id,
            error=str(e),
            exc_info=True)

        raise  # Let Lambda retry
```

**Observability:** Metrics and logs are automatically sent to Datadog via the Lambda extension layer.

## Toast Menu Updater Events

### ToastMenuUpdateRequested

**DetailType:** `integration.toast.MenuUpdateRequested`

**Purpose:** Triggers a Lambda function to update menu data from Toast

**Published By:** `/api/routes/internal/scheduled.py` discovery endpoint

**Consumed By:** `toast-menu-updater` Lambda function

**Schema:**

```python
@dataclass
class ToastMenuUpdateRequested(BaseEvent):
    detail_type: ClassVar[str] = "integration.toast.MenuUpdateRequested"

    # Resource identifiers
    project_id: UUID
    integration_id: UUID
    account_id: UUID

    # Names (for logging/debugging)
    project_name: str
    account_name: str

    # Configuration
    namespace: str  # Pinecone namespace for this project
    secret_key: str  # AWS Secrets Manager key for Toast credentials
    update_type: str = "dining_options"  # "dining_options" or "full_menu"

    # Metadata
    requested_at: datetime
    requested_by: str = "scheduler"  # Who triggered: "scheduler" or "manual"
```

**EventBridge JSON Example:**

```json
{
  "version": "0",
  "id": "aabbccdd-eeff-0011-2233-445566778899",
  "detail-type": "integration.toast.MenuUpdateRequested",
  "source": "pal-mono",
  "account": "123456789012",
  "time": "2025-01-12T03:00:08Z",
  "region": "us-east-1",
  "resources": [],
  "detail": {
    "project_id": "d4e5f6a7-b8c9-6d7e-2f1a-0b9c8d7e6f5a",
    "integration_id": "e5f6a7b8-c9d0-7e8f-3a2b-1c0d9e8f7a6b",
    "account_id": "f6a7b8c9-d0e1-8f9a-4b3c-2d1e0f9a8b7c",
    "project_name": "Restaurant DEF Production",
    "account_name": "Restaurant DEF",
    "namespace": "restaurant-def-prod",
    "secret_key": "pal/lat/toast/restaurant-def-pos",
    "update_type": "dining_options",
    "requested_at": "2025-01-12T03:00:08Z",
    "requested_by": "scheduler"
  }
}
```

**Lambda Handler Pattern:**

```python
import time
from datadog import statsd
from ddtrace import tracer
import structlog

logger = structlog.get_logger()

@tracer.wrap(service='toast-menu-updater')
def lambda_handler(event, context):
    detail = event['detail']

    project_id = detail['project_id']
    integration_id = detail['integration_id']
    account_name = detail['account_name']
    project_name = detail['project_name']
    namespace = detail['namespace']
    secret_key = detail['secret_key']
    update_type = detail['update_type']

    start = time.time()

    try:
        # Get Toast credentials
        credentials = secrets_client.get_secret_value(SecretId=secret_key)

        # Get OAuth token
        access_token = get_toast_access_token(credentials)

        # Fetch data based on update_type
        if update_type == "dining_options":
            data = fetch_dining_options(access_token, credentials['business_id'])
        elif update_type == "full_menu":
            data = fetch_full_menu(access_token, credentials['business_id'])

        # Update via internal API
        result = update_knowledge_base(project_id, data)

        # Send success metrics to Datadog
        statsd.increment('toast.menu_update.success',
            tags=[f'account:{account_name}', 'provider:toast', f'update_type:{update_type}'])
        statsd.histogram('toast.menu_update.duration_ms',
            (time.time() - start) * 1000,
            tags=['provider:toast'])

        if result.get('changes_detected'):
            statsd.increment('toast.menu_update.changes_detected',
                tags=[f'account:{account_name}'])
            statsd.gauge('toast.menu_update.items_updated',
                result.get('items_updated', 0),
                tags=[f'account:{account_name}'])

        logger.info("menu_update_success",
            project_id=project_id,
            integration_id=integration_id,
            project_name=project_name,
            changes_detected=result.get('changes_detected', False),
            items_updated=result.get('items_updated', 0),
            duration_ms=(time.time() - start) * 1000)

        return {'statusCode': 200}

    except Exception as e:
        # Send failure metrics to Datadog
        statsd.increment('toast.menu_update.failure',
            tags=[f'account:{account_name}', f'error:{type(e).__name__}'])

        logger.error("menu_update_failed",
            project_id=project_id,
            integration_id=integration_id,
            error=str(e),
            exc_info=True)

        raise  # Let Lambda retry
```

**Observability:** Metrics and logs are automatically sent to Datadog via the Lambda extension layer.

## Event Publishing Examples

### From API Discovery Endpoint

```python
from events import publish_event
from events.schema import SquareTokenRefreshRequested

# Inside API endpoint
async def trigger_square_token_refresh(session, days_threshold=7):
    # Query integrations...

    for integration in square_integrations:
        # Create event
        event = SquareTokenRefreshRequested(
            integration_id=integration.id,
            account_id=integration.account_id,
            account_name=account.name,
            secret_key=integration.secret_key,
            days_threshold=days_threshold,
            current_expires_at=integration.expires_at,
            requested_at=datetime.now(timezone.utc),
            requested_by="scheduler"
        )

        # Publish to EventBridge
        success = await publish_event(event)

        if not success:
            logger.error(f"Failed to publish event for {integration.id}")
```

### From Lambda Function (Datadog Metrics)

```python
from datadog import statsd
import structlog

logger = structlog.get_logger()

def send_success_metrics(provider: str, operation: str, account_name: str, duration_ms: float):
    """Send success metrics to Datadog."""
    statsd.increment(f'{provider}.{operation}.success',
        tags=[f'account:{account_name}', f'provider:{provider}'])
    statsd.histogram(f'{provider}.{operation}.duration_ms',
        duration_ms,
        tags=[f'provider:{provider}'])

    logger.info(f"{operation}_success",
        provider=provider,
        account_name=account_name,
        duration_ms=duration_ms)

def send_failure_metrics(provider: str, operation: str, account_name: str, error: Exception):
    """Send failure metrics to Datadog."""
    statsd.increment(f'{provider}.{operation}.failure',
        tags=[f'account:{account_name}', f'error:{type(error).__name__}'])

    logger.error(f"{operation}_failed",
        provider=provider,
        account_name=account_name,
        error=str(error),
        exc_info=True)
```

## Event Routing Configuration

### EventBridge Rules (Terraform)

```hcl
# Route SquareTokenRefreshRequested to Lambda
resource "aws_cloudwatch_event_rule" "square_token_refresh_requested" {
  name           = "pal-square-token-refresh-requested"
  description    = "Routes SquareTokenRefreshRequested events to Lambda"
  event_bus_name = "pal-main-event-bus"

  event_pattern = jsonencode({
    source      = ["pal-mono"]
    detail-type = ["integration.square.TokenRefreshRequested"]
  })
}

resource "aws_cloudwatch_event_target" "square_lambda" {
  rule           = aws_cloudwatch_event_rule.square_token_refresh_requested.name
  event_bus_name = "pal-main-event-bus"
  arn            = aws_lambda_function.square_token_refresher.arn
}

# Route ToastMenuUpdateRequested to Lambda
resource "aws_cloudwatch_event_rule" "toast_menu_update_requested" {
  name           = "pal-toast-menu-update-requested"
  description    = "Routes ToastMenuUpdateRequested events to Lambda"
  event_bus_name = "pal-main-event-bus"

  event_pattern = jsonencode({
    source      = ["pal-mono"]
    detail-type = ["integration.toast.MenuUpdateRequested"]
  })
}

resource "aws_cloudwatch_event_target" "toast_lambda" {
  rule           = aws_cloudwatch_event_rule.toast_menu_update_requested.name
  event_bus_name = "pal-main-event-bus"
  arn            = aws_lambda_function.toast_menu_updater.arn
}
```

## Datadog Monitoring Configuration

### Lambda Configuration

```hcl
# Add Datadog Lambda extension layer
resource "aws_lambda_function" "square_token_refresher" {
  function_name = "square-token-refresher"
  runtime       = "python3.12"

  layers = [
    "arn:aws:lambda:us-east-1:464622532012:layer:Datadog-Python312:latest"
  ]

  environment {
    variables = {
      DD_API_KEY        = var.datadog_api_key
      DD_SITE           = "datadoghq.com"
      DD_SERVICE        = "square-token-refresher"
      DD_ENV            = var.environment
      DD_LAMBDA_HANDLER = "lambda_function.lambda_handler"
    }
  }

  handler = "datadog_lambda.handler.handler"  # Datadog wrapper
}
```

### Datadog Monitors

```hcl
# Monitor for Square token refresh failures
resource "datadog_monitor" "square_token_refresh_failures" {
  name    = "Square Token Refresh Failures"
  type    = "metric alert"
  message = <<-EOT
    Square token refresh failure rate is above threshold.

    Check Datadog logs for details: https://app.datadoghq.com/logs

    @slack-ops-alerts
  EOT

  query = "sum(last_1h):sum:square.token_refresh.failure{*}.as_count() > 3"

  monitor_thresholds {
    critical = 3
    warning  = 2
  }
}

# Monitor for Toast menu update failures
resource "datadog_monitor" "toast_menu_update_failures" {
  name    = "Toast Menu Update Failures"
  type    = "metric alert"
  message = <<-EOT
    Toast menu update failure rate is above threshold.

    Check Datadog logs for details: https://app.datadoghq.com/logs

    @slack-ops-alerts
  EOT

  query = "sum(last_1h):sum:toast.menu_update.failure{*}.as_count() > 5"

  monitor_thresholds {
    critical = 5
    warning  = 3
  }
}

# Monitor for Lambda errors
resource "datadog_monitor" "lambda_errors" {
  name    = "Business Updater Lambda Errors"
  type    = "metric alert"
  message = "Lambda errors detected in business updaters @slack-ops-alerts"

  query = "sum(last_15m):sum:aws.lambda.errors{service:square-token-refresher OR service:toast-menu-updater}.as_count() > 2"

  monitor_thresholds {
    critical = 2
  }
}
```

## Future Event Extensions

### Potential Additional Events

**1. Agent Notification Events:**

If agents need to be notified when menus change:

```python
@dataclass
class MenuUpdatedNotification(BaseEvent):
    detail_type: ClassVar[str] = "agent.MenuUpdated"

    project_id: UUID
    agent_ids: List[UUID]
    update_summary: str  # "New menu items added", etc.
    changes: List[Dict[str, Any]]  # Structured change log
```

**2. Manual Intervention Events:**

If critical failures need escalation beyond Datadog alerts:

```python
@dataclass
class TokenRefreshManualInterventionRequired(BaseEvent):
    detail_type: ClassVar[str] = "integration.square.ManualInterventionRequired"

    integration_id: UUID
    account_id: UUID
    failure_reason: str
    retry_attempts: int
    next_expiration: datetime
    urgency: str  # "critical", "high", "medium"
```

## Event Testing

### Manual Event Publishing (CLI)

```bash
# Publish test event to EventBridge
aws events put-events \
  --entries '[
    {
      "Source": "pal-mono",
      "DetailType": "integration.square.TokenRefreshRequested",
      "Detail": "{\"integration_id\":\"test-123\",\"account_id\":\"test-456\",\"account_name\":\"Test Restaurant\",\"secret_key\":\"test-secret\",\"days_threshold\":7,\"current_expires_at\":\"2025-01-15T00:00:00Z\",\"requested_at\":\"2025-01-12T02:00:00Z\",\"requested_by\":\"manual\"}",
      "EventBusName": "pal-main-event-bus"
    }
  ]'
```

### Unit Test Example

```python
import pytest
from events import publish_event
from events.schema import SquareTokenRefreshRequested
from datetime import datetime, timezone, timedelta
from uuid import uuid4

@pytest.mark.asyncio
async def test_publish_square_token_refresh_requested():
    """Test publishing SquareTokenRefreshRequested event."""

    event = SquareTokenRefreshRequested(
        integration_id=uuid4(),
        account_id=uuid4(),
        account_name="Test Restaurant",
        secret_key="test-secret",
        days_threshold=7,
        current_expires_at=datetime.now(timezone.utc) + timedelta(days=5),
        requested_at=datetime.now(timezone.utc),
        requested_by="test"
    )

    # Mock EventBridge client
    with patch('events._eventbridge.publish_event') as mock_publish:
        mock_publish.return_value = True

        success = await publish_event(event)

        assert success
        mock_publish.assert_called_once()

        # Verify event structure
        call_args = mock_publish.call_args
        assert call_args[0][0] == "pal-mono"  # source
        assert call_args[0][1] == "integration.square.TokenRefreshRequested"  # detail_type
        assert "integration_id" in call_args[0][2]  # detail dict
```

### Integration Test Example

```python
@pytest.mark.integration
async def test_square_token_refresh_end_to_end():
    """Test complete Square token refresh flow with events."""

    # 1. Create test integration
    integration = create_test_integration(expires_in_days=5)

    # 2. Trigger discovery endpoint
    response = await client.post(
        "/v1/internal/scheduled/square-token-refresh",
        headers={"X-API-Key": TEST_API_KEY}
    )
    assert response.status_code == 200
    assert response.json()['events_published'] >= 1

    # 3. Wait for Lambda execution
    await asyncio.sleep(10)

    # 4. Verify database updated
    updated_integration = get_integration_by_id(integration.id)
    assert updated_integration.expires_at > integration.expires_at

    # 5. Check Datadog metrics (optional - requires Datadog API client)
    datadog_client = get_datadog_client()
    metrics = datadog_client.Metric.query(
        start=int(time.time()) - 600,
        end=int(time.time()),
        query='sum:square.token_refresh.success{*}'
    )
    assert metrics['series']  # Verify metrics were sent
```

## References

- Base Event Implementation: `/events/schema.py`
- Event Publishing: `/events/__init__.py`
- EventBridge Client: `/events/_eventbridge.py`
- Existing Event Examples: `SampleEvent`, `CateringRequestCreated`, etc. in `/events/schema.py`

## Best Practices

### Event Schema Design

1. **Always include timestamps** - `requested_at` for traceability
2. **Use UUIDs for identifiers** - Ensures uniqueness and enables correlation
3. **Include context** - Names (account_name, project_name) help with debugging and Datadog tags
4. **Add metadata** - `requested_by` indicates trigger source (scheduler vs manual)
5. **Idempotency** - Include request IDs if operations should be idempotent
6. **Versioning** - Consider adding `schema_version` field for future changes
7. **Privacy** - Never include credentials or PII in events

### Datadog Observability

1. **Tag everything** - Use account_name, provider, update_type for filtering
2. **Structured logging** - Use structlog for consistent log format
3. **Custom metrics** - Send success/failure/duration metrics
4. **Error context** - Include error type in tags for categorization
5. **Correlation** - Datadog automatically correlates logs, traces, and metrics
6. **APM tracing** - Use `@tracer.wrap()` decorator for distributed tracing
