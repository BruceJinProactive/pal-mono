# Monitoring API - Version 1

## Overview

RESTful API for continuous monitoring system. Provides automated analysis of signal sources (cameras, sensors) with configurable rules and alerting.

**Base Path**: `/v1/operation/projects/{project_id}/monitoring`
**Authentication**: Required (Bearer token)
**Authorization**: Project-level permissions (validated via path parameter)

> **Security Note**: All endpoints include `project_id` as a path parameter to ensure authorization checks happen during FastAPI's dependency resolution phase, preventing unauthorized access.

---

## Core Resources

### 1. Monitoring Configurations
Configure what to monitor, when to check, and how to alert.

### 2. Monitoring Runs
Execution history of monitoring checks with captured data and analysis results.

---

## Endpoints

### Monitoring Configurations

#### List Monitoring Configs
```http
GET /v1/operation/projects/{project_id}/monitoring/configs
```

**Path Parameters:**
- `project_id` (UUID, required) - Project UUID

**Query Parameters:**
- `enabled` (boolean, optional) - Filter by enabled status
- `signal_source_id` (UUID, optional) - Filter by signal source
- `page` (integer, optional, default: 1) - Page number (min: 1)
- `page_size` (integer, optional, default: 10) - Items per page (min: 1, max: 100)

**Response:** `200 OK`
```json
{
  "configs": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "project_id": "660e8400-e29b-41d4-a716-446655440001",
      "signal_source_id": "770e8400-e29b-41d4-a716-446655440002",
      "name": "Counter Cleanliness Monitor",
      "description": "Monitors counter area for cleanliness during business hours",
      "rules": {
        "type": "ai_analysis",
        "prompt": "Check if counter is clean and organized",
        "reference_image_urls": [
          "s3://bucket/reference1.jpg"
        ],
        "comparison_mode": "best_match",
        "confidence_threshold": 0.8
      },
      "enabled": true,
      "created_at": "2025-12-23T10:00:00Z",
      "updated_at": "2025-12-23T10:00:00Z"
    }
  ],
  "total": 15,
  "total_pages": 2,
  "page": 1,
  "page_size": 10
}
```

**Errors:**
- `403 Forbidden` - User lacks project access
- `500 Internal Server Error` - Server error

---

#### Get Monitoring Config
```http
GET /v1/operation/projects/{project_id}/monitoring/configs/{config_id}
```

**Path Parameters:**
- `project_id` (UUID, required) - Project UUID
- `config_id` (UUID, required) - Monitoring configuration ID

**Response:** `200 OK`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "project_id": "660e8400-e29b-41d4-a716-446655440001",
  "signal_source_id": "770e8400-e29b-41d4-a716-446655440002",
  "name": "Counter Cleanliness Monitor",
  "description": "Monitors counter area for cleanliness during business hours",
  "rules": {
    "type": "ai_analysis",
    "prompt": "Check if counter is clean and organized",
    "reference_image_urls": [
      "s3://bucket/reference1.jpg"
    ],
    "comparison_mode": "best_match",
    "confidence_threshold": 0.8
  },
  "enabled": true,
  "created_at": "2025-12-23T10:00:00Z",
  "updated_at": "2025-12-23T10:00:00Z"
}
```

**Errors:**
- `403 Forbidden` - User lacks project access
- `404 Not Found` - Config not found
- `500 Internal Server Error` - Server error

---

#### Create Monitoring Config
```http
POST /v1/operation/projects/{project_id}/monitoring/configs
```

**Path Parameters:**
- `project_id` (UUID, required) - Project UUID

**Request Body:**
```json
{
  "signal_source_id": "770e8400-e29b-41d4-a716-446655440002",
  "name": "Counter Cleanliness Monitor",
  "description": "Monitors counter area for cleanliness during business hours",
  "rules": {
    "type": "ai_analysis",
    "prompt": "Check if counter is clean and organized",
    "reference_image_urls": [
      "s3://bucket/reference1.jpg"
    ],
    "comparison_mode": "best_match",
    "confidence_threshold": 0.8
  },
  "enabled": true
}
```

**Field Validations:**
- `signal_source_id` (UUID, required) - Must exist and belong to project
- `name` (string, required) - 1-255 chars, unique per project
- `description` (string, optional) - Max 2000 chars
- `rules` (object, required) - See Rules Schema below
- `enabled` (boolean, optional, default: true)

**Response:** `201 Created`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "project_id": "660e8400-e29b-41d4-a716-446655440001",
  "signal_source_id": "770e8400-e29b-41d4-a716-446655440002",
  "name": "Counter Cleanliness Monitor",
  "description": "Monitors counter area for cleanliness during business hours",
  "rules": {
    "type": "ai_analysis",
    "prompt": "Check if counter is clean and organized",
    "reference_image_urls": [
      "s3://bucket/reference1.jpg"
    ],
    "comparison_mode": "best_match",
    "confidence_threshold": 0.8
  },
  "enabled": true,
  "created_at": "2025-12-23T10:00:00Z",
  "updated_at": "2025-12-23T10:00:00Z"
}
```

**Errors:**
- `400 Bad Request` - Invalid input (duplicate name, invalid rules, etc.)
- `403 Forbidden` - User lacks project access
- `404 Not Found` - Project or signal source not found
- `500 Internal Server Error` - Server error

---

#### Update Monitoring Config
```http
PATCH /v1/operation/projects/{project_id}/monitoring/configs/{config_id}
```

**Path Parameters:**
- `project_id` (UUID, required) - Project UUID
- `config_id` (UUID, required) - Monitoring configuration ID

**Request Body:** (all fields optional)
```json
{
  "name": "Updated Counter Monitor",
  "description": "Updated description",
  "rules": {
    "type": "ai_analysis",
    "prompt": "Updated prompt",
    "reference_image_urls": [
      "s3://bucket/new-reference.jpg"
    ],
    "comparison_mode": "best_match",
    "confidence_threshold": 0.85
  },
  "enabled": false
}
```

**Response:** `200 OK`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "project_id": "660e8400-e29b-41d4-a716-446655440001",
  "signal_source_id": "770e8400-e29b-41d4-a716-446655440002",
  "name": "Updated Counter Monitor",
  "description": "Updated description",
  "rules": {
    "type": "ai_analysis",
    "prompt": "Updated prompt",
    "reference_image_urls": [
      "s3://bucket/new-reference.jpg"
    ],
    "comparison_mode": "best_match",
    "confidence_threshold": 0.85
  },
  "enabled": false,
  "created_at": "2025-12-23T10:00:00Z",
  "updated_at": "2025-12-23T11:00:00Z"
}
```

**Errors:**
- `400 Bad Request` - Invalid input
- `403 Forbidden` - User lacks project access
- `404 Not Found` - Config not found
- `500 Internal Server Error` - Server error

---

#### Delete Monitoring Config
```http
DELETE /v1/operation/projects/{project_id}/monitoring/configs/{config_id}
```

**Path Parameters:**
- `project_id` (UUID, required) - Project UUID
- `config_id` (UUID, required) - Monitoring configuration ID

**Response:** `204 No Content`

**Errors:**
- `403 Forbidden` - User lacks project access
- `404 Not Found` - Config not found
- `500 Internal Server Error` - Server error

---

#### Trigger Manual Run
```http
POST /v1/operation/projects/{project_id}/monitoring/configs/{config_id}/run
```

**Path Parameters:**
- `project_id` (UUID, required) - Project UUID
- `config_id` (UUID, required) - Monitoring configuration ID

**Request Body:** (optional)
```json
{
  "s3_bucket": "monitoring-images",
  "s3_key": "camera-123/2025-12-23T10-30-00.jpg"
}
```

**Response:** `202 Accepted`
```json
{
  "run_id": "880e8400-e29b-41d4-a716-446655440003",
  "monitoring_config_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "message": "Monitoring run started"
}
```

**Errors:**
- `400 Bad Request` - Invalid input or config disabled
- `403 Forbidden` - User lacks project access
- `404 Not Found` - Config not found
- `500 Internal Server Error` - Server error

---

### Monitoring Runs

#### List Monitoring Runs
```http
GET /v1/operation/projects/{project_id}/monitoring/configs/{monitoring_config_id}/runs
```

**Path Parameters:**
- `project_id` (UUID, required) - Project UUID
- `monitoring_config_id` (UUID, required) - Monitoring config UUID

**Query Parameters:**
- `start_date` (datetime, optional) - Filter runs after this date (ISO 8601)
- `end_date` (datetime, optional) - Filter runs before this date (ISO 8601)
- `result` (string, optional) - Filter by result (`pass`, `fail`, `error`)
- `page` (integer, optional, default: 1) - Page number (min: 1)
- `page_size` (integer, optional, default: 10) - Items per page (min: 1, max: 100)

**Response:** `200 OK`
```json
{
  "runs": [
    {
      "id": "880e8400-e29b-41d4-a716-446655440003",
      "monitoring_config_id": "550e8400-e29b-41d4-a716-446655440000",
      "trigger_metadata": {
        "trigger_source": "manual_api",
        "user_id": "user-123",
        "endpoint": "/api/v1/operation/monitoring/configs/550e8400.../run",
        "triggered_at": "2025-12-23T10:30:00Z"
      },
      "started_at": "2025-12-23T10:30:00Z",
      "completed_at": "2025-12-23T10:30:05Z",
      "evaluation_result": {
        "analysis_type": "ai_vision",
        "result": "fail",
        "confidence": 0.92,
        "finding": "Counter has visible food debris in northeast corner",
        "details": {
          "reference_image": "s3://bucket/reference.jpg",
          "captured_image": "s3://bucket/capture-123.jpg",
          "comparison_mode": "best_match",
          "matched_reference": "s3://bucket/reference.jpg"
        },
        "model": "claude-3.5-sonnet",
        "processing_time_ms": 2340
      },
      "error_message": null
    }
  ],
  "total": 150,
  "total_pages": 15,
  "page": 1,
  "page_size": 10
}
```

**Errors:**
- `403 Forbidden` - User lacks project access
- `404 Not Found` - Monitoring config not found
- `500 Internal Server Error` - Server error

---

#### Get Monitoring Run
```http
GET /v1/operation/projects/{project_id}/monitoring/runs/{run_id}
```

**Path Parameters:**
- `project_id` (UUID, required) - Project UUID
- `run_id` (UUID, required) - Monitoring run ID

**Response:** `200 OK`
```json
{
  "id": "880e8400-e29b-41d4-a716-446655440003",
  "monitoring_config_id": "550e8400-e29b-41d4-a716-446655440000",
  "trigger_metadata": {
    "trigger_source": "manual_api",
    "user_id": "user-123",
    "endpoint": "/api/v1/operation/monitoring/configs/550e8400.../run",
    "triggered_at": "2025-12-23T10:30:00Z"
  },
  "started_at": "2025-12-23T10:30:00Z",
  "completed_at": "2025-12-23T10:30:05Z",
  "evaluation_result": {
    "analysis_type": "ai_vision",
    "result": "fail",
    "confidence": 0.92,
    "finding": "Counter has visible food debris in northeast corner",
    "details": {
      "reference_image": "s3://bucket/reference.jpg",
      "captured_image": "s3://bucket/capture-123.jpg",
      "comparison_mode": "best_match",
      "matched_reference": "s3://bucket/reference.jpg"
    },
    "model": "claude-3.5-sonnet",
    "processing_time_ms": 2340
  },
  "error_message": null
}
```

**Errors:**
- `403 Forbidden` - User lacks project access
- `404 Not Found` - Run not found
- `500 Internal Server Error` - Server error

---

## Data Schemas

### Rules Schema

Monitoring configurations support two types of rules:

#### AI Analysis Rules
```json
{
  "type": "ai_analysis",
  "prompt": "string (required, 1-2000 chars) - What to check for",
  "reference_image_urls": [
    "string (optional) - S3 URLs of reference images"
  ],
  "comparison_mode": "string (optional) - 'best_match' or 'all_match', default: 'best_match'",
  "confidence_threshold": "number (optional) - 0.0-1.0, default: 0.8"
}
```

**Example:**
```json
{
  "type": "ai_analysis",
  "prompt": "Verify that the counter area is clean with no visible debris or clutter",
  "reference_image_urls": [
    "s3://monitoring-refs/clean-counter-example-1.jpg",
    "s3://monitoring-refs/clean-counter-example-2.jpg"
  ],
  "comparison_mode": "best_match",
  "confidence_threshold": 0.85
}
```

#### Threshold Rules
```json
{
  "type": "threshold",
  "metric": "string (required) - Name of metric to check",
  "operator": "string (required) - 'lt', 'gt', 'lte', 'gte', 'eq', 'between'",
  "value": "number (required for single-value operators)",
  "min": "number (required for 'between')",
  "max": "number (required for 'between')",
  "unit": "string (optional) - Unit of measurement"
}
```

**Example:**
```json
{
  "type": "threshold",
  "metric": "temperature",
  "operator": "between",
  "min": 35,
  "max": 40,
  "unit": "fahrenheit"
}
```

---

### Trigger Metadata Schema

Captures context about what triggered a monitoring run:

#### S3 Event Trigger
```json
{
  "trigger_source": "auto",
  "s3_bucket": "monitoring-images",
  "s3_key": "camera-123/2025-12-23T10-30-00.jpg",
  "event_time": "2025-12-23T10:30:00Z"
}
```

#### Manual API Trigger
```json
{
  "trigger_source": "manual_api",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "endpoint": "/api/v1/operation/monitoring/configs/{id}/run",
  "triggered_at": "2025-12-23T10:30:00Z"
}
```

#### Scheduled Trigger
```json
{
  "trigger_source": "scheduled",
  "cron_job_id": "scheduler-worker-1",
  "scheduled_for": "2025-12-23T10:30:00Z",
  "triggered_at": "2025-12-23T10:30:02Z"
}
```

---

### Evaluation Result Schema

#### AI Analysis Result
```json
{
  "analysis_type": "ai_vision",
  "result": "pass | fail | error",
  "confidence": 0.92,
  "finding": "Human-readable description of what was found",
  "details": {
    "reference_image": "s3://bucket/reference.jpg",
    "captured_image": "s3://bucket/capture-123.jpg",
    "comparison_mode": "best_match",
    "matched_reference": "s3://bucket/reference.jpg"
  },
  "model": "claude-3.5-sonnet",
  "processing_time_ms": 2340
}
```

#### Threshold Check Result
```json
{
  "analysis_type": "threshold",
  "result": "pass | fail | error",
  "metric": "temperature",
  "measured_value": 45,
  "expected_range": { "min": 35, "max": 40 },
  "unit": "fahrenheit",
  "finding": "Temperature 45°F exceeds maximum threshold of 40°F",
  "processing_time_ms": 120
}
```

---

## Common Patterns

### Pagination
All list endpoints support pagination with consistent parameters:
- `page`: Page number (default: 1, min: 1)
- `page_size`: Items per page (default: 10, min: 1, max: 100)

Response format:
```json
{
  "items": [...],
  "total": 150,
  "total_pages": 15,
  "page": 1,
  "page_size": 10
}
```

### Date Filtering
Date parameters accept ISO 8601 format:
- `YYYY-MM-DD` (date only)
- `YYYY-MM-DDTHH:MM:SSZ` (full timestamp)

Examples:
- `start_date=2025-12-01`
- `end_date=2025-12-23T23:59:59Z`

### Error Response Format
All errors follow a consistent format:
```json
{
  "detail": "Human-readable error message"
}
```

---

## Use Cases

### 1. Create AI Vision Monitor
```http
POST /v1/operation/projects/660e8400-e29b-41d4-a716-446655440001/monitoring/configs
Content-Type: application/json

{
  "signal_source_id": "770e8400-e29b-41d4-a716-446655440002",
  "name": "Kitchen Cleanliness Check",
  "description": "Monitors kitchen area during prep hours",
  "rules": {
    "type": "ai_analysis",
    "prompt": "Verify kitchen surfaces are clean, no cross-contamination visible",
    "reference_image_urls": [
      "s3://refs/clean-kitchen-1.jpg"
    ],
    "confidence_threshold": 0.9
  },
  "enabled": true
}
```

### 2. Create Temperature Monitor
```http
POST /v1/operation/projects/660e8400-e29b-41d4-a716-446655440001/monitoring/configs
Content-Type: application/json

{
  "signal_source_id": "880e8400-e29b-41d4-a716-446655440003",
  "name": "Refrigerator Temperature Monitor",
  "description": "Ensures fridge stays within safe temperature range",
  "rules": {
    "type": "threshold",
    "metric": "temperature",
    "operator": "between",
    "min": 35,
    "max": 40,
    "unit": "fahrenheit"
  },
  "enabled": true
}
```

### 3. Trigger Manual Check
```http
POST /v1/operation/projects/660e8400-e29b-41d4-a716-446655440001/monitoring/configs/550e8400.../run
Content-Type: application/json

{
  "s3_bucket": "monitoring-images",
  "s3_key": "camera-front/2025-12-23T15-00-00.jpg"
}
```

### 4. Review Recent Failures
```http
GET /v1/operation/projects/660e8400-e29b-41d4-a716-446655440001/monitoring/configs/550e8400.../runs?result=fail&page=1&page_size=20
```

### 5. Disable Monitor Temporarily
```http
PATCH /v1/operation/projects/660e8400-e29b-41d4-a716-446655440001/monitoring/configs/550e8400...
Content-Type: application/json

{
  "enabled": false
}
```

---

## Authorization

All endpoints require:
1. **Authentication**: Valid Bearer token
2. **Authorization**: Project-level permission via `require_project_permission()`

Permission checks:
- `GET` endpoints: `monitoring.read`
- `POST /configs`: `monitoring.write`
- `PATCH /configs/{id}`: `monitoring.write`
- `DELETE /configs/{id}`: `monitoring.delete`
- `POST /configs/{id}/run`: `monitoring.execute`

---

## Rate Limits

- Standard endpoints: 100 requests/minute per user
- Manual run trigger: 10 requests/minute per config (to prevent abuse)

---

## Versioning

**Current Version**: v1

API version is included in URL path (`/v1/...`). Breaking changes will increment the version number.

---

## Implementation Status

### ✅ Implemented (V1)
- ✅ CRUD operations for monitoring configs
- ✅ Manual run triggering
- ✅ Run history retrieval
- ✅ AI analysis rules
- ✅ Threshold rules
- ✅ Single signal source per config
- ✅ Pagination and filtering
- ✅ Project-level authorization
- ✅ Name uniqueness validation

### 📂 Implementation Files

**API Schemas**: [api/schemas/operations/monitoring.py](../../../../api/schemas/operations/monitoring.py)
- `CreateMonitoringConfigRequest`, `UpdateMonitoringConfigRequest`
- `MonitoringConfigResponse`, `ListMonitoringConfigsResponse`
- `TriggerRunRequest`, `TriggerRunResponse`
- `MonitoringRunResponse`, `ListMonitoringRunsResponse`
- `AIAnalysisRules`, `ThresholdRules` (discriminated union)

**Repositories**:
- [monitoring_config_repository.py](../../../../db/repositories/monitoring_config_repository.py) - `MonitoringConfigRepositoryAsync`
- [monitoring_run_repository.py](../../../../db/repositories/monitoring_run_repository.py) - `MonitoringRunRepositoryAsync`

**Service Layer**: [services/monitoring_service/](../../../../services/monitoring_service/)
- `create_config()`, `get_configs()`, `get_config()`
- `update_config()`, `delete_config()`
- `trigger_run()`, `get_runs()`, `get_run()`
- `build_config_response()`, `build_run_response()`

**API Routes**: [api/routes/operation/_monitoring.py](../../../../api/routes/operation/_monitoring.py)
- All route handlers with error handling
- Integrated into [operation router](../../../../api/routes/operation/__init__.py)

### 🎯 Architecture Patterns

**Repository Pattern**:
- Async repositories for database operations
- SQLAlchemy session management
- Error handling with proper rollback

**Service Layer**:
- Business logic separation
- Validation (project exists, source exists, unique names)
- Authorization via project ownership
- Response builders

**API Layer**:
- FastAPI route decorators
- Pydantic schema validation
- HTTP status codes: 201 (create), 200 (update), 204 (delete), 202 (trigger)
- Authorization via `require_project_permission()`

### 📊 Actual Endpoints

**Monitoring Configs:**
```
POST   /v1/operation/projects/{project_id}/monitoring/configs                    - Create (201)
GET    /v1/operation/projects/{project_id}/monitoring/configs                    - List (200)
GET    /v1/operation/projects/{project_id}/monitoring/configs/{config_id}        - Get (200)
PATCH  /v1/operation/projects/{project_id}/monitoring/configs/{config_id}        - Update (200)
DELETE /v1/operation/projects/{project_id}/monitoring/configs/{config_id}        - Delete (204)
POST   /v1/operation/projects/{project_id}/monitoring/configs/{config_id}/run    - Trigger (202)
```

**Monitoring Runs:**
```
GET    /v1/operation/projects/{project_id}/monitoring/configs/{config_id}/runs   - List (200)
GET    /v1/operation/projects/{project_id}/monitoring/runs/{run_id}              - Get (200)
```

### 🔧 Testing

**Prerequisites**:
1. Start services: `docker-compose up -d --build`
2. Create a signal source first (required)
3. Obtain valid Bearer token for authentication

**Manual Test Flow**:
```bash
# 1. Create monitoring config
POST /v1/operation/projects/{project_id}/monitoring/configs
{
  "signal_source_id": "...",
  "name": "Counter Cleanliness Monitor",
  "rules": {
    "type": "ai_analysis",
    "prompt": "Check if counter is clean",
    "confidence_threshold": 0.8
  }
}

# 2. List configs
GET /v1/operation/projects/{project_id}/monitoring/configs

# 3. Trigger run
POST /v1/operation/projects/{project_id}/monitoring/configs/{config_id}/run

# 4. List runs
GET /v1/operation/projects/{project_id}/monitoring/configs/{monitoring_config_id}/runs
```

### ❌ Not Yet Implemented

**Async Processing**:
- Background worker for run evaluation
- Queue system for processing
- Webhook notifications on completion

**Advanced Features**:
- Scheduling configuration (cron expressions)
- Alert configuration and delivery
- Multi-source aggregation
- Real-time status via WebSocket
- Batch operations
- Config templates and cloning

### 📋 Next Steps

1. **Database Migration**: Create Alembic migration for `monitoring_configs` and `monitoring_runs` tables
2. **Integration Testing**: Write tests for all endpoints
3. **Async Processing**: Implement background worker for run evaluation
4. **Monitoring**: Add metrics and logging
5. **Alert System**: Implement alert configuration and delivery

---

## Related Documentation

- **PRD**: [.claude/docs/operations/monitoring/prd.md](../prd.md)
- **Database Schema**: [.claude/docs/operations/monitoring/db/v1.md](../db/v1.md)
- **Implementation Summary**: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
- **Architecture Guide**: [CLAUDE.md](../../../../CLAUDE.md)
- **Route Patterns**: [api/routes/CLAUDE.md](../../../../api/routes/CLAUDE.md)

---

**Version**: 1.0
**Last Updated**: 2025-12-29
**Status**: ✅ Implemented - Ready for Database Migration and Testing
