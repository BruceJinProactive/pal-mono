# Business Data Updater Architecture

## Overview

This document describes the event-driven architecture for scheduled business data updates in the pal-mono system. The architecture enables automated, scalable, and observable updates for:

1. **Square Token Refresher** - Refreshes OAuth tokens before expiration
2. **Toast Menu Updater** - Syncs restaurant menus and dining options to knowledge base

## Design Philosophy

### Core Principles

1. **Event-Driven** - Use EventBridge for triggering work asynchronously
2. **Fan-Out Pattern** - One event per integration/project for parallel processing and isolation
3. **Separation of Concerns** - API handles DB operations, Lambda handles external API work
4. **Observable** - Datadog provides comprehensive monitoring, metrics, and alerting
5. **Resilient** - Built-in retries, dead letter queues, and failure notifications

### Why This Architecture?

**Current Problems:**
- Manual API endpoints require external cron jobs
- No observability or failure notifications
- Single-threaded processing (all integrations in one request)
- Tight coupling between discovery and execution
- No retry mechanism for failures

**Solutions:**
- EventBridge Scheduler provides reliable, managed scheduling
- Fan-out pattern enables parallel Lambda executions
- Clean separation enables independent scaling and retries
- Datadog Lambda extension provides automatic monitoring and alerting

## Architecture Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│                    EventBridge Scheduler                         │
│              (Daily Cron: 2 AM UTC, 3 AM UTC)                   │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                │ HTTP POST (with API Key)
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Internal API: Discovery Phase                   │
│                                                                   │
│  POST /v1/internal/scheduled/square-token-refresh                │
│  POST /v1/internal/scheduled/toast-menu-update                   │
│                                                                   │
│  • Query PostgreSQL for integrations/projects                    │
│  • Apply business logic (expiration filters, etc.)               │
│  • For each item → Publish event to EventBridge                  │
│  • Return summary (total queued)                                 │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                │ Publish N events (fan-out)
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      EventBridge Event Bus                       │
│                      (pal-main-event-bus)                        │
│                                                                   │
│  Event Types:                                                    │
│  • integration.square.TokenRefreshRequested                      │
│  • integration.toast.MenuUpdateRequested                         │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
                    ▼                       ▼
         ┌────────────────────┐  ┌────────────────────┐
         │  Square Lambda     │  │  Toast Lambda      │
         │  (Datadog Layer)   │  │  (Datadog Layer)   │
         │                    │  │                    │
         │  • Get event       │  │  • Get event       │
         │  • Call Square API │  │  • Call Toast API  │
         │  • Call internal   │  │  • Call internal   │
         │    API for DB      │  │    API for DB      │
         │  • Send metrics to │  │  • Send metrics to │
         │    Datadog         │  │    Datadog         │
         └────────────────────┘  └────────────────────┘
                    │                       │
                    └───────────┬───────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│           Internal API: Database Operations Phase                │
│                                                                   │
│  POST /v1/internal/integrations/{id}/credentials                 │
│  POST /v1/internal/knowledge/{project_id}/dining-options         │
│                                                                   │
│  • Validate request (API key, payload)                           │
│  • Execute PostgreSQL updates                                    │
│  • Update Secrets Manager                                        │
│  • Update Pinecone (knowledge base)                              │
│  • Return success/failure                                        │
└─────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

### 1. EventBridge Scheduler

**Purpose:** Trigger scheduled tasks at specified intervals

**Configuration:**
- **Square Token Refresh:** Daily at 2:00 AM UTC
- **Toast Menu Update:** Daily at 3:00 AM UTC

**Target:** Internal API endpoints via API Gateway

**Authentication:** API Key passed in headers

### 2. Internal API - Discovery Endpoints

**Purpose:** Query database, apply business logic, fan out events

**Location:** `/api/routes/internal/scheduled.py`

**Endpoints:**

#### `POST /v1/internal/scheduled/square-token-refresh`

**Logic:**
1. Query all Square integrations via `IntegrationRepository`
2. Filter for integrations expiring within 7 days
3. For each matching integration:
   - Publish `SquareTokenRefreshRequested` event
   - Include integration_id, account_id in event payload
4. Return summary: `{total_queued: 5, detail: [...]}`

**Event Payload Example:**
```json
{
  "integration_id": "uuid",
  "account_id": "uuid",
  "account_name": "Restaurant ABC",
  "days_threshold": 7,
  "requested_at": "2025-01-12T02:00:00Z"
}
```

#### `POST /v1/internal/scheduled/toast-menu-update`

**Logic:**
1. Query all Toast integrations via `IntegrationRepository`
2. Join with `ProjectIntegration` to get associated projects
3. For each project+integration pair:
   - Publish `ToastMenuUpdateRequested` event
   - Include project_id, integration_id, namespace
4. Return summary: `{total_queued: 12, detail: [...]}`

**Event Payload Example:**
```json
{
  "project_id": "uuid",
  "integration_id": "uuid",
  "project_name": "Restaurant ABC Production",
  "account_name": "Restaurant ABC",
  "namespace": "restaurant-abc-prod",
  "update_type": "dining_options",
  "requested_at": "2025-01-12T03:00:00Z"
}
```

### 3. EventBridge Event Bus

**Purpose:** Route events to appropriate consumers

**Bus Name:** `pal-main-event-bus` (from env var `MAIN_EVENT_BUS_NAME`)

**Event Rules:**
- `SquareTokenRefreshRequested` → Square Token Refresher Lambda
- `ToastMenuUpdateRequested` → Toast Menu Updater Lambda

**Event Attributes:**
- **Source:** `pal-mono` (fixed)
- **DetailType:** Event-specific (e.g., `integration.square.TokenRefreshRequested`)
- **Detail:** Event payload (JSON)

### 4. Lambda Functions

**Purpose:** Execute work (external API calls), delegate DB operations to internal API

**Configuration:**
- **Runtime:** Python 3.12
- **Timeout:** 5 minutes
- **Memory:** 512 MB (adjust based on testing)
- **Concurrency:** Reserved concurrency TBD (prevent overwhelming APIs)
- **Retry:** 2 retries with exponential backoff
- **DLQ:** Yes, with Datadog monitor for alarm
- **Datadog Layer:** Added for automatic instrumentation

**Common Pattern:**
1. Parse event from EventBridge
2. Validate event payload
3. Call external API (Square, Toast, etc.)
4. Call internal API endpoint to persist results
5. Send metrics and structured logs to Datadog
6. Handle errors with Datadog error tracking

### 5. Internal API - Database Operation Endpoints

**Purpose:** Provide controlled access to database for Lambdas

**Location:** `/api/routes/internal/integrations.py`

**Authentication:** API Key (same as scheduler endpoints)

**Endpoints:**

#### `POST /v1/internal/integrations/{integration_id}/credentials`

**Request Body:**
```json
{
  "access_token": "new_token",
  "refresh_token": "new_refresh_token",
  "expires_at": "2025-02-12T00:00:00Z",
  "token_type": "Bearer"
}
```

**Logic:**
1. Validate integration exists
2. Get current secret_key from integration
3. Update AWS Secrets Manager with new tokens
4. Update integration.expires_at in PostgreSQL
5. Commit transaction
6. Return success

#### `POST /v1/internal/knowledge/{project_id}/dining-options`

**Request Body:**
```json
{
  "dining_options_json": "{...}",
  "source": "toast",
  "integration_id": "uuid"
}
```

**Logic:**
1. Validate project exists and has namespace
2. Query Pinecone for existing dining options (metadata: `isDiningOptions=True`)
3. Compare new vs existing (string comparison)
4. If different or missing:
   - Delete old vectors
   - Upload new dining options as text
   - Create embeddings
5. Return result

## Event Schema Design

All events inherit from `BaseEvent` class (see `/events/schema.py`).

### Request Events (Trigger Work)

```python
@dataclass
class SquareTokenRefreshRequested(BaseEvent):
    detail_type: ClassVar[str] = "integration.square.TokenRefreshRequested"

    integration_id: UUID
    account_id: UUID
    account_name: str
    secret_key: str
    days_threshold: int
    current_expires_at: datetime
    requested_at: datetime
    requested_by: str = "scheduler"

@dataclass
class ToastMenuUpdateRequested(BaseEvent):
    detail_type: ClassVar[str] = "integration.toast.MenuUpdateRequested"

    project_id: UUID
    integration_id: UUID
    account_id: UUID
    project_name: str
    account_name: str
    namespace: str
    secret_key: str
    update_type: str  # "dining_options" or "full_menu"
    requested_at: datetime
    requested_by: str = "scheduler"
```

**Note:** Observability is handled by Datadog Lambda extension, not completion events.

## Data Flow Examples

### Square Token Refresh Flow

```
1. EventBridge Scheduler (2:00 AM UTC)
   └─> POST /v1/internal/scheduled/square-token-refresh

2. Discovery Endpoint
   ├─> Query: SELECT * FROM integrations
   │          WHERE provider='square' AND type='pos'
   │          AND expires_at < NOW() + INTERVAL '7 days'
   ├─> Found: 5 integrations
   └─> Publish 5 events to EventBridge

3. EventBridge Routes Events
   └─> 5 concurrent Lambda invocations

4. Square Lambda (per integration)
   ├─> Get refresh_token from Secrets Manager
   ├─> POST https://connect.squareup.com/oauth2/token
   ├─> Receive: access_token, refresh_token, expires_at
   ├─> POST /v1/internal/integrations/{id}/credentials
   └─> Send metrics to Datadog (success/failure, duration)

5. Internal API Endpoint
   ├─> Update Secrets Manager
   ├─> UPDATE integrations SET expires_at = ?
   ├─> COMMIT
   └─> Return success

6. Observability
   └─> Datadog monitors alert on failure rate > threshold
```

### Toast Menu Update Flow

```
1. EventBridge Scheduler (3:00 AM UTC)
   └─> POST /v1/internal/scheduled/toast-menu-update

2. Discovery Endpoint
   ├─> Query: SELECT p.*, i.* FROM projects p
   │          JOIN project_integrations pi ON p.id = pi.project_id
   │          JOIN integrations i ON pi.integration_id = i.id
   │          WHERE i.provider='toast' AND i.type='pos'
   ├─> Found: 12 project+integration pairs
   └─> Publish 12 events to EventBridge

3. EventBridge Routes Events
   └─> 12 concurrent Lambda invocations

4. Toast Lambda (per project+integration)
   ├─> Get Toast credentials from Secrets Manager
   ├─> POST https://toast-api.com/oauth/token (get bearer token)
   ├─> GET https://toast-api.com/config/v2/diningOptions
   ├─> POST /v1/internal/knowledge/{project_id}/dining-options
   └─> Send metrics to Datadog (success/failure, changes_detected, duration)

5. Internal API Endpoint
   ├─> Query Pinecone for existing dining options
   ├─> Compare old vs new (string match)
   ├─> If different:
   │   ├─> Delete old vectors
   │   └─> Upload new dining options
   ├─> COMMIT (if any DB updates needed)
   └─> Return success

6. Observability
   └─> Datadog dashboards show: items_updated, changes_detected
```

## Implementation Phases

### Phase 1: Event Schema & Internal Endpoints (This Codebase)

**Goal:** Add event schemas and internal API endpoints without changing existing behavior

**Tasks:**
1. Add 2 request event schemas to `/events/schema.py` (no completion events)
2. Create `/api/routes/internal/scheduled.py` with discovery endpoints
3. Create `/api/routes/internal/integrations.py` with DB operation endpoints
4. Register routers in `/api/routes/internal/__init__.py`
5. Write unit tests for endpoints
6. Deploy to LAT environment

**Testing:**
- Call discovery endpoints manually → verify events published
- Call DB operation endpoints manually → verify DB updates
- Check CloudWatch for event delivery

**Rollback:** No risk, new endpoints don't affect existing code

### Phase 2: Lambda Functions (Separate Deployment)

**Goal:** Create Lambda functions that consume events and execute work

**Tasks:**
1. Create Lambda package structure
2. Port Square token refresh logic to Lambda
3. Port Toast menu update logic to Lambda
4. Add Datadog Lambda extension layer
5. Add error handling and retry logic
6. Configure IAM roles and permissions
7. Deploy to LAT environment

**Testing:**
- Manually publish test events to EventBridge
- Verify Lambda executions in Datadog
- Verify DB updates via internal endpoints
- Test failure scenarios (invalid tokens, API errors)
- Confirm metrics appear in Datadog

**Rollback:** Delete Lambda functions, events go to DLQ

### Phase 3: EventBridge Scheduler Rules

**Goal:** Automate daily execution

**Tasks:**
1. Create EventBridge Scheduler rules (Terraform/CDK)
2. Configure schedules (2 AM, 3 AM UTC)
3. Set up API Gateway authentication
4. Deploy to LAT environment
5. Monitor for 1 week

**Testing:**
- Wait for scheduled execution
- Verify end-to-end flow
- Check metrics and logs

**Rollback:** Disable scheduler rules, revert to manual triggers

### Phase 4: Observability & Monitoring

**Goal:** Production-grade monitoring and alerting with Datadog

**Tasks:**
1. Create Datadog dashboard for business updaters
2. Set up Datadog monitors for failures
3. Configure Datadog alerting to Slack/PagerDuty
4. Verify custom metrics (success rate, duration, etc.)
5. Create runbook for common issues

**Metrics to Track:**
- Total requests per day (from discovery endpoints)
- Success rate per integration (from Lambda metrics)
- Average execution duration (from Datadog APM)
- Token expiration lead time
- API error rates (Square, Toast)
- Lambda cold starts and errors

### Phase 5: Migration & Cleanup

**Goal:** Fully migrate to event-driven system

**Tasks:**
1. Validate production execution for 2 weeks
2. Add authentication to old endpoints (prevent public access)
3. Update documentation
4. Consider deprecating old endpoints

## Security Considerations

### Authentication

**Internal Endpoints:**
- Require API key in `X-API-Key` header
- Store API key in Secrets Manager
- Rotate periodically

**Lambda Permissions:**
- Minimal IAM roles (principle of least privilege)
- VPC configuration for DB access (if needed)
- Secrets Manager read-only access

### Data Protection

**Sensitive Data:**
- Never log tokens or credentials
- Use Secrets Manager for all secrets
- Encrypt event payloads if needed

**Network Security:**
- Internal endpoints not publicly accessible
- API Gateway resource policies
- Lambda VPC configuration

## Monitoring & Observability

### Datadog Metrics

**Lambda Metrics (Automatic via Datadog Layer):**
```
lambda.invocations (by function_name, account_name)
lambda.errors (by function_name, error_type)
lambda.duration (by function_name)
lambda.cold_starts

Custom Business Metrics (sent via statsd):
square.token_refresh.success
square.token_refresh.failure
square.token_refresh.duration_ms
toast.menu_update.success
toast.menu_update.failure
toast.menu_update.changes_detected
toast.menu_update.items_updated
toast.menu_update.duration_ms
```

### Datadog Monitors

**Critical:**
- Square token refresh failure rate > 10% in last hour
- Toast menu update failure rate > 20% in last hour
- Lambda error rate > 5%
- DLQ message count > 0

**Warning:**
- Lambda duration p95 > 4 minutes
- No Lambda invocations in 25 hours (scheduler failure)
- Lambda cold start rate > 30%

### Datadog Dashboard

**Widgets:**
1. Success rate per service (last 30 days)
2. Execution duration percentiles (p50, p90, p99)
3. Error count by type (API errors, DB errors, timeouts)
4. Lambda invocations timeline
5. DLQ message count
6. Cold start frequency
7. Token expiration timeline

### Logs

**Structured Logging (Auto-collected by Datadog):**
```json
{
  "timestamp": "2025-01-12T02:05:32Z",
  "level": "INFO",
  "service": "square-token-refresher",
  "dd.trace_id": "123456789",
  "dd.span_id": "987654321",
  "integration_id": "uuid",
  "account_id": "uuid",
  "account_name": "Restaurant ABC",
  "action": "token_refreshed",
  "duration_ms": 1234,
  "new_expires_at": "2025-02-12T00:00:00Z"
}
```

**Datadog automatically:**
- Correlates logs with traces and metrics
- Extracts custom tags from log attributes
- Indexes errors for error tracking
- Provides log analytics and patterns

## Error Handling & Retries

### Retry Strategy

**Lambda Retries:**
- Max attempts: 3 (initial + 2 retries)
- Backoff: Exponential (1s, 4s, 16s)
- DLQ: Send to dead letter queue after max retries

**Internal API Retries:**
- Lambda should retry 5xx errors
- Don't retry 4xx errors (bad request)
- Timeout: 30 seconds per request

### Failure Scenarios

**Square API Errors:**
- Invalid refresh token → Alert ops team, manual intervention needed
- Rate limit → Retry with backoff
- Network timeout → Retry

**Toast API Errors:**
- Invalid credentials → Alert ops team
- Restaurant not found → Skip, log warning
- Rate limit → Retry with backoff

**Database Errors:**
- Deadlock → Retry
- Connection timeout → Retry
- Constraint violation → Don't retry, investigate

**Pinecone Errors:**
- Index not found → Alert ops team
- Quota exceeded → Alert ops team
- Timeout → Retry

## Testing Strategy

### Unit Tests

**API Endpoints:**
- Mock database queries
- Mock EventBridge publish
- Test business logic (filtering, validation)

**Lambda Functions:**
- Mock external API calls
- Mock internal API calls
- Test error handling

### Integration Tests

**End-to-End:**
- Publish test event → verify Lambda execution → verify DB updates
- Call discovery endpoint → verify events published → verify consumption

**Database Tests:**
- Test internal DB endpoints with real database
- Test transaction rollback on errors

### Load Tests

**Concurrent Lambda Executions:**
- Simulate 100 concurrent Square refreshes
- Measure duration, error rate
- Verify no DB deadlocks

## Rollback Plan

### Emergency Rollback

**If production issues arise:**

1. **Disable EventBridge Scheduler rules**
   - Prevents new automated executions
   - Keeps system in known state

2. **Check DLQ for failed messages**
   - Investigate root cause
   - Decide whether to replay or discard

3. **Revert to manual endpoints**
   - Use old endpoints: `/v1/integrations/square/refresh-expiring`
   - Trigger manually until issues resolved

4. **Rollback code changes**
   - Revert API changes if bugs found
   - Redeploy previous version

### Partial Rollback

**If only Square has issues:**
- Disable Square scheduler rule only
- Keep Toast running
- Fix Square Lambda and redeploy

## Future Enhancements

### Additional Integrations

**Datadog can integrate with:**
- Slack for alert notifications
- PagerDuty for on-call escalation
- Jira for automatic ticket creation on critical failures
- Webhooks for custom downstream automation

### Additional Scheduled Tasks

**Same pattern can be used for:**
- Adora menu syncing
- Square menu syncing
- OpenTable reservation syncing
- Resy reservation syncing
- Stripe billing updates
- Usage metric aggregation

### Advanced Features

**Priority Queue:**
- Process critical integrations first
- Deprioritize inactive accounts

**Adaptive Scheduling:**
- Refresh tokens more frequently if nearing expiration
- Update menus during off-peak hours

**Batch Processing:**
- Group multiple updates per restaurant
- Reduce API calls

## References

- Event Bus Implementation: `/events/__init__.py`
- Event Schemas: `/events/schema.py`
- Current Square Refresher: `/api/routes/integrations/square/_implementation.py`
- Current Toast Updater: `/api/routes/integrations/toast/_implementation.py`
- Internal Router: `/api/routes/internal/__init__.py`

## Glossary

- **Fan-out:** Publishing multiple events from a single request
- **DLQ:** Dead Letter Queue - stores failed messages
- **Event Bus:** Central message router (EventBridge)
- **Discovery Phase:** Query DB and publish events
- **Execution Phase:** Lambda processes event
- **DB Operation Phase:** Lambda calls internal API for persistence
