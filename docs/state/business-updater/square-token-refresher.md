# Square Token Refresher - Detailed Implementation

> **Last updated:** 2025-03-01

## Overview

The Square Token Refresher automatically refreshes OAuth 2.0 access tokens for Square POS integrations before they expire. This ensures uninterrupted service for:
- Menu syncing
- Order management
- Customer data access
- Location information

## Current Implementation Analysis

### Location
- **Main Logic:** `/api/routes/integrations/square/_implementation.py` (lines 191-306)
- **Utilities:** `/api/routes/integrations/square/_util.py` (lines 91-200)
- **Router:** `/api/routes/integrations/__init__.py` (lines 46-58)

### Current Flow

```
API Endpoint: POST /v1/integrations/square/refresh-expiring
    ↓
check_and_refresh_expiring_square_tokens(session, days_threshold=7)
    ↓
Query all Square integrations
    ↓
Filter by expiration (< 7 days)
    ↓
For each integration:
    ↓
refresh_square_token(account_name, integration_id, session)
    ↓
Call Square OAuth API
    ↓
update_integration_credentials()
    ↓
Update expires_at in DB
    ↓
Return summary
```

### Database Schema

**Table:** `integrations`

Relevant columns:
```sql
id                UUID PRIMARY KEY
account_id        UUID REFERENCES accounts(id)
provider          VARCHAR (='square')
type              VARCHAR (='pos')
secret_key        VARCHAR  -- AWS Secrets Manager key
expires_at        TIMESTAMP WITH TIME ZONE
created_at        TIMESTAMP WITH TIME ZONE
updated_at        TIMESTAMP WITH TIME ZONE
```

**AWS Secrets Manager Structure:**
```json
{
  "access_token": "sq0atp-...",
  "refresh_token": "sq0rtr-...",
  "merchant_id": "...",
  "token_type": "bearer",
  "expires_at": "2025-02-12T00:00:00Z"
}
```

### Current Code

#### Discovery & Orchestration

```python
def check_and_refresh_expiring_square_tokens(
    session, days_threshold: int = 7
) -> dict:
    integration_repository = IntegrationRepository(session)

    # Get all Square POS integrations
    square_integrations = (
        integration_repository.get_all_integrations_by_provider_and_type(
            provider=IntegrationProvider.square,
            type=IntegrationType.pos
        )
    )

    expiration_threshold = datetime.now(timezone.utc) + timedelta(days=days_threshold)
    total_checked = 0
    total_refreshed = 0
    total_failed = 0
    errors = []

    for integration in square_integrations:
        if not integration.secret_key or not integration.expires_at:
            continue

        total_checked += 1

        # Check if expiring soon
        if integration.expires_at < expiration_threshold:
            try:
                account = session.query(Account).filter(
                    Account.id == integration.account_id
                ).first()

                refresh_square_token(
                    account.name,
                    integration.id,
                    session
                )
                total_refreshed += 1

            except Exception as e:
                total_failed += 1
                errors.append(f"Integration {integration.id}: {str(e)}")

    return {
        "total_checked": total_checked,
        "total_refreshed": total_refreshed,
        "total_failed": total_failed,
        "errors": errors
    }
```

#### Token Refresh Logic

```python
def refresh_square_token(
    account_name: str,
    integration_id: str,
    session
) -> dict:
    integration_repository = IntegrationRepository(session)

    # Get integration
    integration = integration_repository.get_integration_by_id(integration_id)

    # Get current credentials
    credentials = get_square_credentials_from_aws(account_name, integration.secret_key)
    refresh_token = credentials.get("refresh_token")

    # Get Square client credentials
    client_secret = get_square_client_secret()

    # Call Square OAuth endpoint
    response = requests.post(
        "https://connect.squareup.com/oauth2/token",
        json={
            "client_id": SQUARE_APPLICATION_ID,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        },
        headers={"Content-Type": "application/json"}
    )

    if response.status_code != 200:
        raise Exception(f"Square API error: {response.text}")

    data = response.json()

    # Update credentials
    update_integration_credentials(
        session=session,
        integration_repository=integration_repository,
        account_name=account_name,
        integration_id=integration_id,
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_at_str=data["expires_at"]
    )

    return data
```

#### Credentials Update

```python
def update_integration_credentials(
    session,
    integration_repository,
    account_name: str,
    integration_id: str,
    access_token: str,
    refresh_token: str,
    expires_at_str: str
):
    integration = integration_repository.get_integration_by_id(integration_id)

    # Get existing credentials
    credentials = get_square_credentials_from_aws(account_name, integration.secret_key)

    # Update credentials
    credentials["access_token"] = access_token
    credentials["refresh_token"] = refresh_token
    credentials["expires_at"] = expires_at_str

    # Save to Secrets Manager
    update_square_credentials_in_aws(
        account_name,
        integration.secret_key,
        credentials
    )

    # Update database
    new_expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
    integration_repository.update_integration(
        integration_id=integration_id,
        expires_at=new_expires_at
    )

    session.commit()
```

### Issues with Current Implementation

1. **No Parallel Processing** - All integrations processed sequentially
2. **No Retries** - Single failure fails entire batch
3. **No Observability** - No events published, only endpoint response
4. **Tight Coupling** - Discovery and execution in same function
5. **Manual Trigger** - Requires external cron/scheduler
6. **No Failure Isolation** - One error doesn't stop others, but no visibility
7. **No Authentication** - Endpoint is public (security risk)

## Event-Driven Architecture

### Components

```
┌──────────────────────────────────────────────────────────────┐
│  EventBridge Scheduler                                        │
│  Rule: pal-daily-square-token-refresh                        │
│  Schedule: cron(0 2 * * ? *)  # 2 AM UTC daily              │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     │ POST /v1/internal/scheduled/square-token-refresh
                     │ Headers: X-API-Key: ***
                     ▼
┌──────────────────────────────────────────────────────────────┐
│  Internal API: Discovery Endpoint                            │
│  File: /api/routes/internal/scheduled.py                     │
│                                                               │
│  1. Query all Square integrations                            │
│  2. Filter by expires_at < NOW() + 7 days                   │
│  3. For each integration:                                     │
│     - Get account details                                     │
│     - Publish SquareTokenRefreshRequested event              │
│  4. Return summary: {total_queued: N}                        │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     │ Publish N events (fan-out)
                     ▼
┌──────────────────────────────────────────────────────────────┐
│  EventBridge: pal-main-event-bus                             │
│  DetailType: integration.square.TokenRefreshRequested        │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     │ N parallel invocations
                     ▼
┌──────────────────────────────────────────────────────────────┐
│  Lambda: square-token-refresher                              │
│  Runtime: Python 3.12                                         │
│  Timeout: 5 minutes                                           │
│  Concurrency: 10 (reserved)                                   │
│                                                               │
│  1. Parse event                                               │
│  2. Get refresh_token from Secrets Manager                   │
│  3. Call Square OAuth API                                     │
│  4. POST /v1/internal/integrations/{id}/credentials          │
│  5. Publish SquareTokenRefreshCompleted event                │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     │ POST with new credentials
                     ▼
┌──────────────────────────────────────────────────────────────┐
│  Internal API: DB Update Endpoint                            │
│  File: /api/routes/internal/integrations.py                  │
│                                                               │
│  1. Validate integration exists                               │
│  2. Update Secrets Manager                                    │
│  3. Update integration.expires_at                             │
│  4. Commit transaction                                        │
│  5. Return success                                            │
└──────────────────────────────────────────────────────────────┘
```

## Implementation Details

### Phase 1: Event Schemas

**File:** `/events/schema.py`

```python
@dataclass
class SquareTokenRefreshRequested(BaseEvent):
    """Event published when a Square token needs refreshing."""

    detail_type: ClassVar[str] = "integration.square.TokenRefreshRequested"

    # Required fields
    integration_id: UUID
    account_id: UUID
    account_name: str
    secret_key: str  # AWS Secrets Manager key
    current_expires_at: datetime
    days_threshold: int

    # Metadata
    requested_at: datetime
    requested_by: str = "scheduler"  # or "manual" for manual triggers


@dataclass
class SquareTokenRefreshCompleted(BaseEvent):
    """Event published when a Square token refresh completes."""

    detail_type: ClassVar[str] = "integration.square.TokenRefreshCompleted"

    # Required fields
    integration_id: UUID
    account_id: UUID
    account_name: str
    success: bool

    # Success fields
    new_expires_at: Optional[datetime] = None
    previous_expires_at: Optional[datetime] = None

    # Failure fields
    error_message: Optional[str] = None
    error_code: Optional[str] = None

    # Metadata
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: int = 0
    lambda_request_id: Optional[str] = None
```

### Phase 2: Discovery Endpoint

**File:** `/api/routes/internal/scheduled.py` (new file)

```python
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging

from db import get_db
from db.repositories.integration_repository import IntegrationRepository
from db.repositories.account_repository import AccountRepository
from db.tables.integration import IntegrationProvider, IntegrationType
from events import publish_event
from events.schema import SquareTokenRefreshRequested

logger = logging.getLogger(__name__)

scheduled_router = APIRouter()


def validate_api_key(x_api_key: str = Header(...)) -> bool:
    """Validate API key for internal endpoints."""
    # TODO: Get expected key from Secrets Manager
    expected_key = os.getenv("INTERNAL_API_KEY")
    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return True


@scheduled_router.post("/square-token-refresh")
async def trigger_square_token_refresh(
    days_threshold: int = 7,
    session: Session = Depends(get_db),
    _: bool = Depends(validate_api_key)
):
    """
    Discovery endpoint for Square token refresh.

    Queries database for expiring tokens and publishes events.
    Called by EventBridge Scheduler daily.
    """
    integration_repo = IntegrationRepository(session)
    account_repo = AccountRepository(session)

    try:
        # Get all Square POS integrations
        square_integrations = (
            integration_repo.get_all_integrations_by_provider_and_type(
                provider=IntegrationProvider.square,
                type=IntegrationType.pos
            )
        )

        # Calculate expiration threshold
        threshold = datetime.now(timezone.utc) + timedelta(days=days_threshold)

        # Filter and publish events
        events_published = 0
        skipped = 0
        errors = []

        for integration in square_integrations:
            # Skip if missing required data
            if not integration.secret_key or not integration.expires_at:
                skipped += 1
                logger.warning(
                    f"Skipping integration {integration.id}: "
                    f"missing secret_key or expires_at"
                )
                continue

            # Check if expiring soon
            if integration.expires_at < threshold:
                try:
                    # Get account details
                    account = account_repo.get_account_by_id(integration.account_id)

                    # Publish event
                    event = SquareTokenRefreshRequested(
                        integration_id=integration.id,
                        account_id=integration.account_id,
                        account_name=account.name,
                        secret_key=integration.secret_key,
                        current_expires_at=integration.expires_at,
                        days_threshold=days_threshold,
                        requested_at=datetime.now(timezone.utc),
                        requested_by="scheduler"
                    )

                    success = await publish_event(event)

                    if success:
                        events_published += 1
                        logger.info(
                            f"Published refresh event for integration {integration.id}",
                            extra={
                                "integration_id": str(integration.id),
                                "account_id": str(integration.account_id),
                                "expires_at": integration.expires_at.isoformat()
                            }
                        )
                    else:
                        errors.append(
                            f"Failed to publish event for integration {integration.id}"
                        )

                except Exception as e:
                    errors.append(
                        f"Error processing integration {integration.id}: {str(e)}"
                    )
                    logger.error(
                        f"Error processing integration {integration.id}",
                        exc_info=True,
                        extra={"integration_id": str(integration.id)}
                    )

        # Return summary
        return {
            "success": True,
            "total_integrations": len(square_integrations),
            "events_published": events_published,
            "skipped": skipped,
            "errors": errors,
            "threshold_days": days_threshold,
            "threshold_date": threshold.isoformat()
        }

    except Exception as e:
        logger.error("Error in square token refresh discovery", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger token refresh: {str(e)}"
        )
```

### Phase 3: Lambda Function

**File:** `lambdas/square_token_refresher/handler.py` (new Lambda project)

```python
import json
import os
import boto3
import requests
from datetime import datetime, timezone
from typing import Dict, Any
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
secrets_client = boto3.client('secretsmanager')
eventbridge_client = boto3.client('events')

# Configuration
SQUARE_APPLICATION_ID = os.environ['SQUARE_APPLICATION_ID']
SQUARE_CLIENT_SECRET_NAME = os.environ['SQUARE_CLIENT_SECRET_NAME']
INTERNAL_API_URL = os.environ['INTERNAL_API_URL']
INTERNAL_API_KEY = os.environ['INTERNAL_API_KEY']
EVENT_BUS_NAME = os.environ['EVENT_BUS_NAME']


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for Square token refresh.

    Receives SquareTokenRefreshRequested event from EventBridge.
    """
    start_time = datetime.now(timezone.utc)
    request_id = context.request_id

    try:
        # Parse event
        detail = event['detail']
        integration_id = detail['integration_id']
        account_id = detail['account_id']
        account_name = detail['account_name']
        secret_key = detail['secret_key']
        current_expires_at = detail['current_expires_at']

        logger.info(
            f"Processing token refresh for integration {integration_id}",
            extra={
                "integration_id": integration_id,
                "account_id": account_id,
                "account_name": account_name
            }
        )

        # Get current credentials
        credentials = get_credentials_from_secrets_manager(secret_key)
        refresh_token = credentials['refresh_token']

        # Get Square client secret
        client_secret = get_square_client_secret()

        # Call Square OAuth API
        new_credentials = refresh_token_with_square(
            refresh_token=refresh_token,
            client_secret=client_secret
        )

        # Update via internal API
        update_integration_credentials_via_api(
            integration_id=integration_id,
            credentials=new_credentials
        )

        # Calculate duration
        duration_ms = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )

        # Publish success event
        publish_completion_event(
            integration_id=integration_id,
            account_id=account_id,
            account_name=account_name,
            success=True,
            new_expires_at=new_credentials['expires_at'],
            previous_expires_at=current_expires_at,
            duration_ms=duration_ms,
            request_id=request_id
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "integration_id": integration_id,
                "new_expires_at": new_credentials['expires_at']
            })
        }

    except Exception as e:
        logger.error(
            f"Error refreshing token: {str(e)}",
            exc_info=True,
            extra={
                "integration_id": detail.get('integration_id'),
                "error": str(e)
            }
        )

        # Calculate duration
        duration_ms = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )

        # Publish failure event
        publish_completion_event(
            integration_id=detail.get('integration_id'),
            account_id=detail.get('account_id'),
            account_name=detail.get('account_name'),
            success=False,
            error_message=str(e),
            error_code=type(e).__name__,
            duration_ms=duration_ms,
            request_id=request_id
        )

        # Re-raise to trigger Lambda retry
        raise


def get_credentials_from_secrets_manager(secret_key: str) -> Dict[str, Any]:
    """Get integration credentials from Secrets Manager."""
    response = secrets_client.get_secret_value(SecretId=secret_key)
    return json.loads(response['SecretString'])


def get_square_client_secret() -> str:
    """Get Square client secret from Secrets Manager."""
    response = secrets_client.get_secret_value(SecretId=SQUARE_CLIENT_SECRET_NAME)
    secret = json.loads(response['SecretString'])
    return secret['client_secret']


def refresh_token_with_square(
    refresh_token: str,
    client_secret: str
) -> Dict[str, Any]:
    """Call Square OAuth API to refresh token."""
    response = requests.post(
        "https://connect.squareup.com/oauth2/token",
        json={
            "client_id": SQUARE_APPLICATION_ID,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        },
        headers={"Content-Type": "application/json"},
        timeout=30
    )

    if response.status_code != 200:
        raise Exception(
            f"Square API error: {response.status_code} - {response.text}"
        )

    return response.json()


def update_integration_credentials_via_api(
    integration_id: str,
    credentials: Dict[str, Any]
) -> None:
    """Update integration credentials via internal API."""
    url = f"{INTERNAL_API_URL}/v1/internal/integrations/{integration_id}/credentials"

    response = requests.post(
        url,
        json={
            "access_token": credentials['access_token'],
            "refresh_token": credentials['refresh_token'],
            "expires_at": credentials['expires_at'],
            "token_type": credentials.get('token_type', 'Bearer')
        },
        headers={
            "Content-Type": "application/json",
            "X-API-Key": INTERNAL_API_KEY
        },
        timeout=30
    )

    if response.status_code != 200:
        raise Exception(
            f"Internal API error: {response.status_code} - {response.text}"
        )


def publish_completion_event(
    integration_id: str,
    account_id: str,
    account_name: str,
    success: bool,
    new_expires_at: str = None,
    previous_expires_at: str = None,
    error_message: str = None,
    error_code: str = None,
    duration_ms: int = 0,
    request_id: str = None
) -> None:
    """Publish SquareTokenRefreshCompleted event."""
    detail = {
        "integration_id": integration_id,
        "account_id": account_id,
        "account_name": account_name,
        "success": success,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": duration_ms,
        "lambda_request_id": request_id
    }

    if success:
        detail["new_expires_at"] = new_expires_at
        detail["previous_expires_at"] = previous_expires_at
    else:
        detail["error_message"] = error_message
        detail["error_code"] = error_code

    eventbridge_client.put_events(
        Entries=[{
            "Source": "pal-mono",
            "DetailType": "integration.square.TokenRefreshCompleted",
            "Detail": json.dumps(detail),
            "EventBusName": EVENT_BUS_NAME
        }]
    )
```

**Lambda Dependencies (`requirements.txt`):**
```
requests==2.31.0
boto3==1.34.0
```

### Phase 4: DB Update Endpoint

**File:** `/api/routes/internal/integrations.py` (new file)

```python
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import logging

from db import get_db
from db.repositories.integration_repository import IntegrationRepository
from api.routes.integrations.square._util import (
    get_square_credentials_from_aws,
    update_square_credentials_in_aws
)

logger = logging.getLogger(__name__)

integrations_router = APIRouter()


class UpdateCredentialsRequest(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: str  # ISO 8601 format
    token_type: str = "Bearer"


def validate_api_key(x_api_key: str = Header(...)) -> bool:
    """Validate API key for internal endpoints."""
    expected_key = os.getenv("INTERNAL_API_KEY")
    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return True


@integrations_router.post("/{integration_id}/credentials")
async def update_integration_credentials(
    integration_id: str,
    request: UpdateCredentialsRequest,
    session: Session = Depends(get_db),
    _: bool = Depends(validate_api_key)
):
    """
    Update integration credentials.

    Called by Lambda after successful token refresh.
    Updates both Secrets Manager and database.
    """
    integration_repo = IntegrationRepository(session)

    try:
        # Get integration
        integration = integration_repo.get_integration_by_id(integration_id)
        if not integration:
            raise HTTPException(status_code=404, detail="Integration not found")

        # Get account
        account = session.query(Account).filter(
            Account.id == integration.account_id
        ).first()

        # Get current credentials
        current_creds = get_square_credentials_from_aws(
            account.name,
            integration.secret_key
        )

        # Update credentials
        current_creds['access_token'] = request.access_token
        current_creds['refresh_token'] = request.refresh_token
        current_creds['expires_at'] = request.expires_at
        current_creds['token_type'] = request.token_type

        # Save to Secrets Manager
        update_square_credentials_in_aws(
            account.name,
            integration.secret_key,
            current_creds
        )

        # Parse expires_at
        new_expires_at = datetime.fromisoformat(
            request.expires_at.replace("Z", "+00:00")
        )

        # Update database
        integration_repo.update_integration(
            integration_id=integration_id,
            expires_at=new_expires_at
        )

        session.commit()

        logger.info(
            f"Updated credentials for integration {integration_id}",
            extra={
                "integration_id": integration_id,
                "account_id": str(integration.account_id),
                "new_expires_at": new_expires_at.isoformat()
            }
        )

        return {
            "success": True,
            "integration_id": integration_id,
            "expires_at": new_expires_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error updating credentials for {integration_id}",
            exc_info=True,
            extra={"integration_id": integration_id}
        )
        session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update credentials: {str(e)}"
        )
```

### Phase 5: Register Routers

**File:** `/api/routes/internal/__init__.py` (modify existing)

```python
from fastapi import APIRouter
from .events import events_router
from .scheduled import scheduled_router  # NEW
from .integrations import integrations_router  # NEW

internal_router = APIRouter()

internal_router.include_router(events_router, prefix="/events", tags=["Internal Events"])
internal_router.include_router(scheduled_router, prefix="/scheduled", tags=["Scheduled Tasks"])  # NEW
internal_router.include_router(integrations_router, prefix="/integrations", tags=["Internal Integrations"])  # NEW
```

## Infrastructure as Code

### EventBridge Scheduler (Terraform)

```hcl
resource "aws_scheduler_schedule" "square_token_refresh" {
  name        = "pal-daily-square-token-refresh"
  description = "Triggers Square token refresh daily at 2 AM UTC"

  schedule_expression = "cron(0 2 * * ? *)"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_api_gateway_stage.internal.execution_arn
    role_arn = aws_iam_role.scheduler_role.arn

    http_parameters {
      header_parameters = {
        "X-API-Key" = data.aws_secretsmanager_secret_version.internal_api_key.secret_string
      }
    }

    input = jsonencode({
      days_threshold = 7
    })

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 2
    }
  }
}
```

### EventBridge Event Rule (Terraform)

```hcl
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

  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 2
  }

  dead_letter_config {
    arn = aws_sqs_queue.square_token_refresh_dlq.arn
  }
}
```

### Lambda Function (Terraform)

```hcl
resource "aws_lambda_function" "square_token_refresher" {
  function_name = "pal-square-token-refresher"
  role          = aws_iam_role.square_lambda_role.arn

  filename         = "lambdas/square_token_refresher.zip"
  source_code_hash = filebase64sha256("lambdas/square_token_refresher.zip")

  runtime = "python3.12"
  handler = "handler.lambda_handler"
  timeout = 300  # 5 minutes
  memory_size = 512

  reserved_concurrent_executions = 10

  environment {
    variables = {
      SQUARE_APPLICATION_ID      = var.square_application_id
      SQUARE_CLIENT_SECRET_NAME  = aws_secretsmanager_secret.square_client_secret.name
      INTERNAL_API_URL           = var.internal_api_url
      INTERNAL_API_KEY           = data.aws_secretsmanager_secret_version.internal_api_key.secret_string
      EVENT_BUS_NAME             = "pal-main-event-bus"
    }
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.square_token_refresh_dlq.arn
  }
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.square_token_refresher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.square_token_refresh_requested.arn
}
```

## Testing Strategy

### Unit Tests

**Test Discovery Endpoint:**
```python
def test_square_token_refresh_discovery(test_client, test_db):
    # Create test integrations
    integration1 = create_square_integration(
        expires_at=datetime.now(timezone.utc) + timedelta(days=3)  # Expiring
    )
    integration2 = create_square_integration(
        expires_at=datetime.now(timezone.utc) + timedelta(days=30)  # Not expiring
    )

    # Call endpoint
    response = test_client.post(
        "/v1/internal/scheduled/square-token-refresh",
        headers={"X-API-Key": "test-key"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data['events_published'] == 1  # Only integration1
    assert data['total_integrations'] == 2
```

**Test Lambda Handler:**
```python
def test_lambda_handler_success(mock_secrets, mock_requests, mock_eventbridge):
    # Mock Square API response
    mock_requests.post.return_value.json.return_value = {
        "access_token": "new_token",
        "refresh_token": "new_refresh",
        "expires_at": "2025-02-12T00:00:00Z"
    }

    # Mock internal API response
    mock_requests.post.return_value.status_code = 200

    # Create test event
    event = {
        "detail": {
            "integration_id": "test-id",
            "account_id": "test-account",
            "account_name": "Test Restaurant",
            "secret_key": "test-secret",
            "current_expires_at": "2025-01-15T00:00:00Z"
        }
    }

    # Call handler
    result = lambda_handler(event, mock_context)

    assert result['statusCode'] == 200
    assert json.loads(result['body'])['success'] == True
```

### Integration Tests

**End-to-End Test:**
```python
async def test_square_token_refresh_e2e():
    # 1. Call discovery endpoint
    response = await client.post(
        "/v1/internal/scheduled/square-token-refresh",
        headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 200

    # 2. Wait for Lambda execution (poll DLQ)
    await asyncio.sleep(10)

    # 3. Verify database updated
    integration = get_integration_by_id(test_integration_id)
    assert integration.expires_at > original_expires_at

    # 4. Verify completion event published
    events = get_events_from_eventbridge(
        detail_type="integration.square.TokenRefreshCompleted"
    )
    assert len(events) > 0
    assert events[0]['detail']['success'] == True
```

## Monitoring & Alerts

### CloudWatch Metrics

```python
# In Lambda
cloudwatch = boto3.client('cloudwatch')

cloudwatch.put_metric_data(
    Namespace='pal-mono/business-updater',
    MetricData=[
        {
            'MetricName': 'SquareTokenRefreshSuccess',
            'Value': 1.0,
            'Unit': 'Count',
            'Dimensions': [
                {'Name': 'Environment', 'Value': os.environ['ENVIRONMENT']}
            ]
        },
        {
            'MetricName': 'SquareTokenRefreshDuration',
            'Value': duration_ms,
            'Unit': 'Milliseconds'
        }
    ]
)
```

### CloudWatch Alarms

```hcl
resource "aws_cloudwatch_metric_alarm" "square_token_refresh_failures" {
  alarm_name          = "pal-square-token-refresh-failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 3600
  statistic           = "Sum"
  threshold           = 3
  alarm_description   = "Alert when Square token refresh has more than 3 failures in 1 hour"

  dimensions = {
    FunctionName = aws_lambda_function.square_token_refresher.function_name
  }

  alarm_actions = [aws_sns_topic.ops_alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "square_dlq_messages" {
  alarm_name          = "pal-square-token-refresh-dlq"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Average"
  threshold           = 0
  alarm_description   = "Alert when messages in Square token refresh DLQ"

  dimensions = {
    QueueName = aws_sqs_queue.square_token_refresh_dlq.name
  }

  alarm_actions = [aws_sns_topic.ops_alerts.arn]
}
```

## Rollback Plan

### Phase 1: Disable Scheduler
```bash
aws scheduler update-schedule \
  --name pal-daily-square-token-refresh \
  --state DISABLED
```

### Phase 2: Check DLQ
```bash
aws sqs receive-message \
  --queue-url https://sqs.us-east-1.amazonaws.com/.../square-token-refresh-dlq \
  --max-number-of-messages 10
```

### Phase 3: Manual Trigger (Old Endpoint)
```bash
curl -X POST https://api.pal.com/v1/integrations/square/refresh-expiring
```

### Phase 4: Rollback Code
```bash
git revert <commit-hash>
./scripts/deploy.sh lat
```

## Future Enhancements

1. **Adaptive Scheduling** - Refresh more frequently as expiration approaches
2. **Batch Processing** - Group multiple refreshes per account
3. **Predictive Alerting** - Alert if token won't refresh in time
4. **Rate Limiting** - Respect Square API rate limits
5. **Metrics Dashboard** - Visualize refresh patterns
6. **Automated Testing** - Daily test refresh in sandbox

## References

- Current Implementation: `/api/routes/integrations/square/_implementation.py:191-306`
- Square OAuth Docs: https://developer.squareup.com/docs/oauth-api/refresh-tokens
- EventBridge Scheduler: https://docs.aws.amazon.com/scheduler/
