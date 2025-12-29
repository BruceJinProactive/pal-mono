# Monitoring Image Processor Architecture

## Overview

This document describes the event-driven architecture for automated monitoring image processing in the pal-mono system. When images are uploaded to AWS SQS (connected to input sources), they automatically trigger AI analysis and generate monitoring runs.

## Design Philosophy

### Core Principles

1. **Event-Driven** - Use SQS → Lambda for asynchronous processing
2. **Automatic Trigger** - Image upload automatically starts analysis (no manual intervention)
3. **Separation of Concerns** - Lambda handles AI analysis, API handles DB operations
4. **Observable** - Datadog provides comprehensive monitoring, metrics, and alerting
5. **Resilient** - Built-in retries, dead letter queue, and failure notifications
6. **Simple** - Single Lambda function processes entire flow end-to-end

### Why This Architecture?

**Current State:**
- Images are uploaded to AWS SQS
- SQS is connected to input sources (cameras, devices)
- Manual API endpoint exists for triggering runs
- No automatic processing on image upload

**Desired State:**
- New images in SQS automatically trigger AI analysis
- Monitoring configs associated with input source are identified
- AI evaluation is performed
- Monitoring run is created with results
- All without manual intervention

## Architecture Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│                         Input Source                             │
│                     (Camera, Device, etc.)                       │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                │ Upload image
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                          AWS SQS Queue                           │
│                   (monitoring-images queue)                      │
│                                                                   │
│  Message Format:                                                 │
│  {                                                                │
│    "s3_bucket": "monitoring-images",                             │
│    "s3_key": "camera-123/2025-12-23T10-30-00.jpg",              │
│    "signal_source_id": "uuid",                                   │
│    "project_id": "uuid",                                         │
│    "uploaded_at": "2025-12-23T10:30:00Z"                        │
│  }                                                                │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                │ Trigger (SQS Event Source)
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│           Lambda: Monitoring Image Processor                     │
│                      (Datadog Layer)                             │
│                                                                   │
│  1. Parse SQS message (signal_source_id, image location)        │
│  2. Query internal API for monitoring configs:                   │
│     GET /v1/internal/monitoring/configs?signal_source_id=...     │
│  3. Download image from S3 once (reuse for all configs)         │
│  4. For each enabled config:                                     │
│     a. Get config rules                                          │
│     b. Perform AI analysis (Claude 3.5 Sonnet)                   │
│     c. POST /v1/internal/monitoring/runs (store results)        │
│  5. Delete SQS message (success)                                 │
│  6. Send metrics to Datadog                                      │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                │ POST with analysis results (×N)
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│           Internal API: Monitoring Run Creation                  │
│                                                                   │
│  POST /v1/internal/monitoring/runs                               │
│                                                                   │
│  1. Validate monitoring_config exists                            │
│  2. Create monitoring_run record with:                           │
│     - trigger_metadata (auto-triggered from SQS)                 │
│     - evaluation_result (AI analysis)                            │
│     - started_at, completed_at timestamps                        │
│  3. If result=fail and alerts configured:                        │
│     - Trigger alert delivery (future phase)                      │
│  4. Commit transaction                                           │
│  5. Return run details                                           │
└─────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

### 1. AWS SQS Queue

**Purpose:** Receive image upload notifications from input sources

**Queue Name:** `monitoring-images-queue` (from env var)

**Message Format:**
```json
{
  "s3_bucket": "monitoring-images",
  "s3_key": "camera-123/2025-12-23T10-30-00.jpg",
  "signal_source_id": "770e8400-e29b-41d4-a716-446655440002",
  "project_id": "660e8400-e29b-41d4-a716-446655440001",
  "uploaded_at": "2025-12-23T10:30:00Z",
  "metadata": {
    "device_type": "camera",
    "location": "front_counter"
  }
}
```

**Configuration:**
- **Visibility Timeout:** 5 minutes (matching Lambda timeout)
- **Message Retention:** 14 days
- **Dead Letter Queue:** Yes, after 3 retries
- **Batch Size:** 1-10 messages per Lambda invocation

### 2. Lambda: Image Upload Processor (Discovery)

**Purpose:** Discover which monitoring configs should process this image

**Configuration:**
- **Runtime:** Python 3.12
- **Timeout:** 2 minutes
- **Memory:** 256 MB
- **Concurrency:** Reserved concurrency TBD
- **Trigger:** SQS queue as event source
- **Batch Size:** 5 messages per invocation
- **Retry:** 2 retries with exponential backoff
- **DLQ:** Yes, with Datadog monitor

**Logic:**
1. Parse SQS message(s)
2. For each message:
   - Extract signal_source_id, project_id, image location
   - Call internal API: `GET /v1/internal/monitoring/configs?signal_source_id={id}&enabled=true`
   - For each enabled monitoring config:
     - Publish `MonitoringAnalysisRequested` event to EventBridge
     - Include config_id, image location, rules
   - Delete SQS message on success
3. Log metrics to Datadog

**Event Published:**
```json
{
  "monitoring_config_id": "550e8400-e29b-41d4-a716-446655440000",
  "signal_source_id": "770e8400-e29b-41d4-a716-446655440002",
  "project_id": "660e8400-e29b-41d4-a716-446655440001",
  "s3_bucket": "monitoring-images",
  "s3_key": "camera-123/2025-12-23T10-30-00.jpg",
  "uploaded_at": "2025-12-23T10:30:00Z",
  "requested_at": "2025-12-23T10:30:02Z"
}
```

### 3. EventBridge Event Bus

**Purpose:** Route analysis requests to processor Lambda

**Bus Name:** `pal-main-event-bus`

**Event Rule:**
- **Event Pattern:** `monitoring.AnalysisRequested`
- **Target:** Monitoring Analysis Processor Lambda
- **Retry:** 2 retries with exponential backoff
- **DLQ:** Yes

### 4. Lambda: Monitoring Analysis Processor (Execution)

**Purpose:** Perform AI analysis and create monitoring run

**Configuration:**
- **Runtime:** Python 3.12
- **Timeout:** 5 minutes (AI analysis takes time)
- **Memory:** 1024 MB (image processing + AI)
- **Concurrency:** Reserved concurrency 5 (control AI API usage)
- **Retry:** 2 retries with exponential backoff
- **DLQ:** Yes, with Datadog monitor
- **Datadog Layer:** Added for automatic instrumentation

**Logic:**
1. Parse event from EventBridge
2. Validate event payload
3. Download image from S3
4. Get monitoring config via internal API:
   - `GET /v1/internal/monitoring/configs/{config_id}`
   - Extract rules, reference images, thresholds
5. Perform AI analysis:
   - If `ai_analysis` type:
     - Load reference images (if provided)
     - Call Claude AI with prompt and images
     - Compare captured vs reference
     - Generate finding and confidence score
   - If `threshold` type:
     - Extract metric from image metadata
     - Compare against threshold
     - Generate pass/fail result
6. Create monitoring run via internal API:
   - `POST /v1/internal/monitoring/runs`
   - Include evaluation_result, trigger_metadata
7. Send metrics to Datadog
8. Handle errors with Datadog error tracking

### 5. Internal API: Discovery Endpoint

**Purpose:** Provide configs associated with a signal source

**Endpoint:** `GET /v1/internal/monitoring/configs`

**Location:** `/api/routes/internal/monitoring.py` (new file)

**Query Parameters:**
- `signal_source_id` (UUID, required)
- `enabled` (boolean, optional, default: true)

**Response:**
```json
{
  "configs": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "project_id": "660e8400-e29b-41d4-a716-446655440001",
      "signal_source_id": "770e8400-e29b-41d4-a716-446655440002",
      "name": "Counter Cleanliness Monitor",
      "rules": {
        "type": "ai_analysis",
        "prompt": "Check if counter is clean",
        "reference_image_urls": ["s3://bucket/ref.jpg"],
        "confidence_threshold": 0.8
      },
      "enabled": true
    }
  ]
}
```

**Authentication:** API Key (same pattern as business updaters)

### 6. Internal API: Run Creation Endpoint

**Purpose:** Create monitoring run record with analysis results

**Endpoint:** `POST /v1/internal/monitoring/runs`

**Location:** `/api/routes/internal/monitoring.py` (same file)

**Request Body:**
```json
{
  "monitoring_config_id": "550e8400-e29b-41d4-a716-446655440000",
  "trigger_metadata": {
    "trigger_source": "auto",
    "s3_bucket": "monitoring-images",
    "s3_key": "camera-123/2025-12-23T10-30-00.jpg",
    "event_time": "2025-12-23T10:30:00Z"
  },
  "evaluation_result": {
    "analysis_type": "ai_vision",
    "result": "fail",
    "confidence": 0.92,
    "finding": "Counter has visible food debris",
    "details": {
      "reference_image": "s3://bucket/reference.jpg",
      "captured_image": "s3://bucket/capture-123.jpg",
      "comparison_mode": "best_match"
    },
    "model": "claude-3.5-sonnet",
    "processing_time_ms": 2340
  },
  "started_at": "2025-12-23T10:30:02Z",
  "completed_at": "2025-12-23T10:30:05Z"
}
```

**Logic:**
1. Validate monitoring_config exists
2. Create `monitoring_runs` record
3. If result=fail and alerts configured:
   - Trigger alert delivery (future phase)
4. Commit transaction
5. Return run details

**Authentication:** API Key

## Event Schema Design

All events inherit from `BaseEvent` class (see `/events/schema.py`).

### MonitoringAnalysisRequested Event

```python
@dataclass
class MonitoringAnalysisRequested(BaseEvent):
    detail_type: ClassVar[str] = "monitoring.AnalysisRequested"

    # Resource identifiers
    monitoring_config_id: UUID
    signal_source_id: UUID
    project_id: UUID

    # Image location
    s3_bucket: str
    s3_key: str

    # Metadata
    uploaded_at: datetime
    requested_at: datetime
    requested_by: str = "auto-processor"
```

## Data Flow Example

### Image Upload → AI Analysis → Run Creation

```
1. Input Source (Camera)
   └─> Uploads image to S3
       └─> Sends message to SQS queue

2. SQS Queue
   └─> Message: {signal_source_id, project_id, s3_bucket, s3_key}

3. Image Upload Processor Lambda
   ├─> Parse SQS message
   ├─> GET /v1/internal/monitoring/configs?signal_source_id=...
   ├─> Found: 2 monitoring configs
   ├─> Publish 2 events to EventBridge
   └─> Delete SQS message

4. EventBridge Routes Events
   └─> 2 concurrent Lambda invocations

5. Monitoring Analysis Processor Lambda (per config)
   ├─> Download image from S3
   ├─> GET /v1/internal/monitoring/configs/{id}
   ├─> Call Claude AI with prompt + images
   ├─> Result: "fail" (cleanliness issue detected)
   ├─> POST /v1/internal/monitoring/runs
   └─> Send metrics to Datadog (result, duration, confidence)

6. Internal API Endpoint
   ├─> Create monitoring_runs record
   ├─> evaluation_result = {result: "fail", finding: "..."}
   ├─> trigger_metadata = {trigger_source: "auto", ...}
   ├─> COMMIT
   └─> Return success

7. Observability
   └─> Datadog dashboards show:
       - Images processed per hour
       - Pass/fail rates per config
       - AI processing duration
       - Error rates and types
```

## Key Differences from Business Updater

| Aspect | Business Updater | Monitoring Processor |
|--------|-----------------|---------------------|
| **Trigger** | EventBridge Scheduler (cron) | AWS SQS (image upload) |
| **Discovery** | Internal API queries DB | Internal API queries DB |
| **Fan-out** | One event per integration | One event per monitoring config |
| **Execution** | External API call (Square, Toast) | AI analysis (Claude) |
| **Data Source** | External APIs | S3 images |
| **Frequency** | Scheduled (daily) | Event-driven (per upload) |
| **Processing** | Quick (<30s) | Longer (AI analysis 1-5min) |

## Implementation Phases

### Phase 1: Event Schema & Internal Endpoints ✅ COMPLETED

**Goal:** Add event schemas and internal API endpoints

**Status:** ✅ **COMPLETED** (2025-12-29)

**Implementation Details:**

**Files Created/Modified:**
- ✅ `/events/schema.py` - Added `MonitoringAnalysisRequested` event class
- ✅ `/events/__init__.py` - Exported new event for imports
- ✅ `/api/routes/internal/monitoring.py` - Created new internal API endpoints
- ✅ `/api/routes/internal/__init__.py` - Registered monitoring router

**Endpoints Implemented:**

1. **GET /v1/internal/monitoring/configs** - Discovery endpoint
   - Query params: `signal_source_id` (required), `enabled` (optional, default: true)
   - Returns: List of monitoring configs for signal source
   - Used by: Image Upload Processor Lambda

2. **GET /v1/internal/monitoring/configs/{config_id}** - Get config details
   - Path param: `config_id`
   - Returns: Full config with rules and reference images
   - Used by: Analysis Processor Lambda

3. **POST /v1/internal/monitoring/runs** - Create monitoring run
   - Body: monitoring_config_id, trigger_metadata, evaluation_result, timestamps
   - Returns: Created run details
   - Used by: Monitoring Image Processor Lambda

**Validation:**
- ✅ Type checking passed (pyright --level error)
- ✅ Async session handling with `get_db_async`
- ✅ Proper error handling (404, 500 with rollback)
- ✅ Structured logging with context

**Testing:**
- ✅ Database-level tests passed (SQL verification)
- ⏳ Database migrations must be applied first

**Next Steps:**
1. Apply database migrations (monitoring_configs, monitoring_runs tables)
2. Deploy to LAT environment
3. Manual testing of endpoints
4. Proceed to Phase 2 (Lambda implementation)

**Rollback:** No risk, new endpoints don't affect existing code

### Phase 2: Monitoring Image Processor Lambda

**Goal:** Single Lambda to discover configs, perform AI analysis, and create runs

**Tasks:**
1. Create Lambda package structure
2. Implement SQS message parsing
3. Call internal API for config discovery (GET /configs?signal_source_id=...)
4. Download image from S3 once (reuse for all configs)
5. For each enabled config:
   - Get config details and rules
   - Integrate Claude AI for image analysis
   - Implement reference image comparison
   - Add threshold checking logic
   - Call internal API to create runs (POST /runs)
6. Add error handling and Datadog instrumentation
7. Deploy to LAT environment

**Testing:**
- Manually send test message to SQS
- Verify Lambda discovers configs correctly
- Verify AI analysis works correctly
- Verify run creation via internal API
- Check pass/fail results are accurate
- Test reference image comparison
- Verify metrics in Datadog

**Rollback:** Delete Lambda, messages stay in SQS

### Phase 3: End-to-End Integration

**Goal:** Full flow from SQS to run creation

**Tasks:**
1. Configure SQS as Lambda trigger
2. Configure IAM permissions
3. Set up DLQ for Lambda
4. Monitor for 1 week in LAT

**Testing:**
- Upload test image to S3
- Send message to SQS
- Verify full flow executes (discovery → AI analysis → run creation)
- Check monitoring run created in database
- Review metrics and logs in Datadog

**Rollback:** Disable SQS trigger

### Phase 4: Observability & Alerting

**Goal:** Production-grade monitoring with Datadog

**Tasks:**
1. Create Datadog dashboard
2. Set up monitors for failures
3. Configure Slack/PagerDuty alerts
4. Create runbook for common issues

**Metrics to Track:**
- Images processed per hour
- Pass/fail rates per config
- AI processing duration (p50, p95, p99)
- Error rates by type
- Lambda cold starts
- Queue depth

## Security Considerations

### Authentication
- **Internal Endpoints:** API key in `X-API-Key` header
- **Lambda Permissions:** Minimal IAM roles (S3 read, SQS consume)
- **Secrets:** Store API keys in Secrets Manager

### Data Protection
- **Image Access:** Lambda has read-only S3 access
- **Sensitive Data:** Never log image contents or findings with PII
- **Encryption:** S3 encryption at rest

## Monitoring & Observability

### Datadog Metrics

**Lambda Metrics (Automatic via Datadog Layer):**
```
lambda.invocations (by function_name, project_id)
lambda.errors (by function_name, error_type)
lambda.duration (by function_name)
lambda.cold_starts

Custom Business Metrics (sent via statsd):
monitoring.processor.sqs_received
monitoring.processor.configs_discovered
monitoring.processor.analysis_success
monitoring.processor.analysis_failure
monitoring.processor.analysis_duration_ms
monitoring.processor.pass_rate (by config_id)
monitoring.processor.fail_rate (by config_id)
monitoring.run.created
```

### Datadog Monitors

**Critical:**
- Image upload processor error rate > 5%
- Analysis processor error rate > 10%
- DLQ message count > 0
- SQS queue depth > 1000 (backlog)

**Warning:**
- Analysis duration p95 > 4 minutes
- No images processed in last hour (system issue)
- Lambda cold start rate > 30%

## Error Handling & Retries

### Retry Strategy

**SQS Messages:**
- Max receives: 3 attempts
- Visibility timeout: 5 minutes
- DLQ after 3 failures

**Lambda Retries:**
- Max attempts: 3 (initial + 2 retries)
- Backoff: Exponential
- DLQ: Send to dead letter queue after max retries

### Failure Scenarios

**SQS Processing Errors:**
- Invalid message format → Log warning, send to DLQ
- Internal API unavailable → Retry
- No configs found → Log info, delete message (success case)

**AI Analysis Errors:**
- Image download failure → Retry
- Claude API error → Retry with backoff
- Invalid reference image → Log error, mark run as error
- Timeout → Retry

## Future Enhancements

### Additional Features
- **Scheduled Analysis:** Support cron-based monitoring (not just event-driven)
- **Batch Processing:** Process multiple images per run
- **Alert Delivery:** Email, SMS, push notifications on fail
- **Trend Analysis:** Detect patterns over time
- **Multi-Image Analysis:** Compare sequences of images

### Performance Optimizations
- **Image Caching:** Cache reference images in Lambda
- **Parallel Processing:** Process multiple configs in parallel
- **Model Selection:** Use faster models for simple checks

## References

- Event Bus Implementation: `/events/__init__.py`
- Event Schemas: `/events/schema.py`
- Monitoring API: `.claude/docs/operations/monitoring/api/v1.md`
- Monitoring PRD: `.claude/docs/operations/monitoring/prd.md`
- Business Updater Pattern: `.claude/docs/business_updater/ARCHITECTURE.md`

## Summary

The Monitoring Image Processor completes the automated monitoring system:

1. **Input Sources** - Cameras/devices upload images to SQS
2. **Monitoring Image Processor** - Single Lambda that discovers configs, performs AI analysis, and creates runs
3. **Internal API** - Handles database operations

**Architecture Benefits:**
- **Event-Driven:** Automatic processing on image upload
- **Fan-Out:** Multiple monitoring configs per image (processed sequentially)
- **Scalable:** Parallel Lambda executions for different SQS messages
- **Observable:** Datadog metrics and monitors
- **Resilient:** Retries and DLQ for Lambda failures
- **Simple:** Single function processes entire flow end-to-end
- **Efficient:** Image downloaded once and reused for all configs

**Key Differentiators from Business Updater:**
- Triggered by SQS (not scheduler)
- AI-heavy processing (not external API)
- Per-image processing (not periodic batch)
- Higher latency tolerance (1-5 min vs <30s)

---

## Implementation Status

### ✅ Phase 1: COMPLETED (2025-12-29)

**What Was Built:**

1. **Internal API Endpoints** (`/api/routes/internal/monitoring.py`)
   - `GET /v1/internal/monitoring/configs?signal_source_id={uuid}` - Discovery
   - `GET /v1/internal/monitoring/configs/{config_id}` - Get config details
   - `POST /v1/internal/monitoring/runs` - Create monitoring run
   - Registered in internal router

2. **Request/Response Schemas**
   - `InternalMonitoringConfigResponse` - Simplified for Lambda
   - `ListInternalMonitoringConfigsResponse` - List wrapper
   - `CreateMonitoringRunRequest` - Run creation payload
   - `CreateMonitoringRunResponse` - Run creation result

**Validation:**
- ✅ Type checking passed (pyright)
- ✅ Linting passed (ruff)
- ✅ Database-level tests passed
- ✅ Follows existing patterns
- ✅ Error handling with automatic rollback
- ✅ Structured logging

**Ready For:**
- Database migration deployment
- LAT environment testing
- Lambda implementation (Phase 2)

### ⏳ Phases 2-4: NOT STARTED

**Remaining Work:**
- Phase 2: Monitoring Image Processor Lambda (single function)
- Phase 3: End-to-End Integration
- Phase 4: Observability & Alerting

---

## Quick Reference

### Internal API Endpoints (Available Now)

```bash
# Discovery - Get configs by signal source
GET /v1/internal/monitoring/configs?signal_source_id={uuid}&enabled=true

# Get config details
GET /v1/internal/monitoring/configs/{config_id}

# Create monitoring run
POST /v1/internal/monitoring/runs
{
  "monitoring_config_id": "uuid",
  "trigger_metadata": {"trigger_source": "auto", "sqs_message_id": "...", ...},
  "evaluation_result": {"result": "pass", "confidence": 0.9, "finding": "...", ...},
  "started_at": "2025-12-29T10:00:00Z",
  "completed_at": "2025-12-29T10:00:05Z",
  "error_message": null
}
```

### Lambda Flow Example

```python
# Pseudo-code for Monitoring Image Processor Lambda
def handler(event, context):
    # 1. Parse SQS message
    sqs_record = event['Records'][0]
    signal_source_id = parse_message(sqs_record)

    # 2. Discover configs
    configs = get_configs_by_signal_source(signal_source_id)

    # 3. Download image once
    image = download_from_s3(bucket, key)

    # 4. Process each config
    for config in configs:
        # Perform AI analysis
        result = analyze_image(image, config.rules)

        # Store result
        create_monitoring_run(config.id, result)
```

### Testing Endpoints

```bash
# 1. Start services
docker-compose up -d --build

# 2. Test discovery endpoint (replace UUID)
curl -X GET "http://localhost:8000/v1/internal/monitoring/configs?signal_source_id=YOUR_UUID&enabled=true"

# 3. Test get config by ID
curl -X GET "http://localhost:8000/v1/internal/monitoring/configs/YOUR_CONFIG_ID"

# 4. Test create run
curl -X POST "http://localhost:8000/v1/internal/monitoring/runs" \
  -H "Content-Type: application/json" \
  -d '{
    "monitoring_config_id": "YOUR_CONFIG_ID",
    "trigger_metadata": {"trigger_source": "test"},
    "evaluation_result": {"result": "pass", "confidence": 0.95},
    "started_at": "2025-12-29T10:00:00Z",
    "completed_at": "2025-12-29T10:00:05Z"
  }'
```

---

**Version:** 1.0
**Last Updated:** 2025-12-29
**Status:** Phase 1 Complete - Ready for Lambda Implementation
