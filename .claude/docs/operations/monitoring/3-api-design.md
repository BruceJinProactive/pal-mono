# Monitoring System - API Design

## Overview

**Base URL**: `/v1` (all endpoints prefixed)
**Auth**: Bearer token required on all requests
**Format**: JSON request/response

---

## API Structure

```
/projects/{project_id}/
├── input-sources/          → Camera/sensor management
├── monitoring-configs/     → Check configuration
├── monitoring-runs/        → Execution history
├── alerts/                 → Alert management
└── monitoring/
    ├── dashboard          → Summary stats
    └── analytics          → Time-series data
```

---

## 1. Monitoring Configs API

### CREATE Config

**Setup a new monitoring check**

```
POST /projects/{project_id}/monitoring-configs

Request (Simple):
┌─────────────────────────────────────────────────────────┐
│ {                                                       │
│   "name": "Counter Cleanliness Check",                 │
│   "input_source_id": "camera-uuid",                    │
│   "trigger_mode": "auto",                              │
│   "rules": {                                           │
│     "type": "ai_analysis",                            │
│     "prompt": "Verify counter is clean",              │
│     "reference_image_url": "s3://bucket/standard.jpg",│
│     "confidence_threshold": 0.8                        │
│   },                                                   │
│   "frequency": "every_30_min",                         │
│   "active_hours_start": "06:00:00",                    │
│   "active_hours_end": "22:00:00",                      │
│   "timezone": "America/Los_Angeles",                   │
│   "alert_severity": "warning",                         │
│   "alert_channels": ["email", "in_app"],              │
│   "enabled": true                                      │
│ }                                                       │
└─────────────────────────────────────────────────────────┘

trigger_mode values:
- "manual": Runs only when POST /monitoring-configs/{id}/run is called
- "auto": Automatically runs when new images uploaded to S3
- "scheduled": Automatically runs based on frequency (Phase 2)

Request (With Template & Multiple References):
┌─────────────────────────────────────────────────────────┐
│ {                                                       │
│   "name": "Bakery Inventory Monitor",                  │
│   "input_source_id": "camera-uuid",                    │
│   "trigger_mode": "auto",                              │
│   "rules": {                                           │
│     "type": "ai_analysis",                            │
│     "prompt": {                                        │
│       "role": "AI {{monitor_type}} Monitor",          │
│       "steps": [                                       │
│         {                                              │
│           "name": "STEP 1: IMAGE VALIDITY CHECK",     │
│           "checks": ["Black/Dark", "Irrelevant"]      │
│         },                                             │
│         {                                              │
│           "name": "STEP 2: ZONE DEFINITIONS",         │
│           "zones": "{{zones}}"                         │
│         },                                             │
│         {                                              │
│           "name": "STEP 3: ANALYSIS LOGIC",           │
│           "focus": "{{focus_item}}",                   │
│           "rule": "{{restock_criteria}}"               │
│         }                                              │
│       ],                                               │
│       "output_format": {"type": "json"}               │
│     },                                                 │
│     "prompt_variables": {                             │
│       "monitor_type": "Inventory",                    │
│       "zones": [                                       │
│         {"id": "bread_zone_1", "location": "upper"},  │
│         {"id": "bread_zone_2", "location": "lower"}   │
│       ],                                               │
│       "focus_item": "White trays",                     │
│       "restock_criteria": "ANY empty tray"             │
│     },                                                 │
│     "reference_image_urls": [                          │
│       "s3://bakery/zone-map.png"                      │
│     ],                                                 │
│     "comparison_mode": "best_match",                   │
│     "confidence_threshold": 0.85                       │
│   },                                                   │
│   "frequency": "every_30_min",                         │
│   "active_hours_start": "06:00:00",                    │
│   "active_hours_end": "22:00:00",                      │
│   "timezone": "America/Los_Angeles",                   │
│   "alert_severity": "warning",                         │
│   "alert_channels": ["email", "in_app"],              │
│   "enabled": true                                      │
│ }                                                       │
└─────────────────────────────────────────────────────────┘

Response (201 Created):
┌─────────────────────────────────────────────────────────┐
│ {                                                       │
│   "id": "config-uuid",                                 │
│   "name": "Counter Cleanliness Check",                │
│   "enabled": true,                                     │
│   "next_scheduled_run_at": "2025-01-15T11:00:00Z",   │
│   "created_at": "2025-01-15T10:30:00Z"                │
│ }                                                       │
└─────────────────────────────────────────────────────────┘
```

**Why**: Define what to monitor and when to alert

---

### LIST Configs

**View all monitoring checks for a store**

```
GET /projects/{project_id}/monitoring-configs
    ?enabled=true
    &limit=50
    &offset=0

Response:
┌─────────────────────────────────────────────────────────┐
│ {                                                       │
│   "configs": [                                         │
│     {                                                  │
│       "id": "config-123",                             │
│       "name": "Counter Cleanliness Monitor",          │
│       "frequency": "every_30_min",                    │
│       "enabled": true,                                │
│       "stats": {                                      │
│         "total_runs": 1250,                          │
│         "success_rate": 0.944                        │
│       },                                              │
│       "last_run_at": "2025-01-15T10:30:00Z",         │
│       "next_scheduled_run_at": "2025-01-15T11:00:00Z"│
│     }                                                  │
│   ],                                                   │
│   "total": 8                                           │
│ }                                                       │
└─────────────────────────────────────────────────────────┘
```

**Why**: See all active monitoring checks and their status

---

### GET Config

**View detailed configuration**

```
GET /monitoring-configs/{config_id}

Response:
┌─────────────────────────────────────────────────────────┐
│ Full config including:                                  │
│ • Rules (AI prompt or threshold)                       │
│ • Schedule (frequency, active hours, timezone)         │
│ • Alert settings (channels, recipients, cooldown)      │
│ • Execution tracking (last run, next run)              │
│ • Statistics (total runs, success rate)                │
└─────────────────────────────────────────────────────────┘
```

**Why**: Review and edit check settings

---

### UPDATE Config

**Modify existing check settings**

```
PUT /monitoring-configs/{config_id}

Request (partial update):
┌─────────────────────────────────────────────────────────┐
│ {                                                       │
│   "alert_severity": "critical",                        │
│   "alert_cooldown_minutes": 15,                        │
│   "enabled": false                                     │
│ }                                                       │
└─────────────────────────────────────────────────────────┘
```

**Why**: Adjust frequency, alerts, or pause monitoring

---

### DELETE Config

**Remove a monitoring check**

```
DELETE /monitoring-configs/{config_id}
       ?resolve_alerts=true

Business Rule:
⛔ Cannot delete if open alerts exist
   → Must resolve alerts first OR set resolve_alerts=true
```

**Why**: Clean up unused or outdated checks

---

### TRIGGER Manual Run

**Execute check immediately (outside schedule)**

```
POST /monitoring-configs/{config_id}/run

Response:
┌─────────────────────────────────────────────────────────┐
│ {                                                       │
│   "run_id": "run-xyz789",                              │
│   "status": "pending",                                 │
│   "scheduled_at": "2025-01-15T12:00:00Z"              │
│ }                                                       │
└─────────────────────────────────────────────────────────┘
```

**Why**: Test check immediately or investigate issue

---

### How Trigger Modes Work

**Phase 1: Three Trigger Methods Available**

```
┌─────────────────────────────────────────────────────────┐
│ Method 1: Manual API Trigger                           │
│   • YOU call POST /monitoring-configs/{id}/run        │
│   • System runs check immediately                      │
│   • Use for: Testing, on-demand checks                │
│                                                         │
│ Method 2: S3 Event-Driven (Automatic)                  │
│   • New image uploaded to S3                           │
│   • S3 sends event notification                        │
│   • System automatically triggers matching configs     │
│   • Runs in background (async)                         │
│   • Use for: Real-time monitoring as images arrive    │
│                                                         │
│ Method 3: Scheduled (Phase 2 - Automatic)              │
│   • System triggers checks based on frequency          │
│   • Runs every X minutes (cron job)                    │
│   • Use for: Periodic monitoring at fixed intervals   │
└─────────────────────────────────────────────────────────┘
```

**Method 1: Manual API Trigger**

```
POST /monitoring-configs/{id}/run
  → Creates ONE immediate run
  → Does NOT affect scheduled runs
  → Use for testing or on-demand checks
```

**Method 2: S3 Event-Driven Triggering**

```
How it works:
┌─────────────────────────────────────────────────────────┐
│ 1. Camera uploads new image to S3 bucket               │
│ 2. S3 triggers event notification (EventBridge/SNS)    │
│ 3. System receives event with image metadata           │
│ 4. System finds all configs using that input_source_id │
│ 5. Creates monitoring runs for each matching config    │
│ 6. Executes runs in background (async queue)           │
└─────────────────────────────────────────────────────────┘

Example Flow:
┌─────────────────────────────────────────────────────────┐
│ Camera uploads image:                                   │
│   s3://cameras/store-123/front-counter/2025-01-15.jpg │
│                                                         │
│ S3 Event:                                              │
│   {"bucket": "cameras", "key": "store-123/..."}        │
│                                                         │
│ System Response:                                        │
│   • Finds configs with input_source = this camera      │
│   • Creates runs for [config-1, config-2, config-3]   │
│   • Executes in background:                            │
│     - Fetch image from S3                              │
│     - Run AI analysis                                  │
│     - Generate alerts if needed                        │
│     - Send notifications                               │
└─────────────────────────────────────────────────────────┘

Configuration:
┌─────────────────────────────────────────────────────────┐
│ {                                                       │
│   "name": "Counter Monitor",                           │
│   "trigger_mode": "auto",                              │
│   "input_source_id": "camera-uuid",                    │
│   ...                                                  │
│ }                                                       │
└─────────────────────────────────────────────────────────┘
```

**Method 3: Scheduled Automatic Runs (Phase 2)**

```
┌─────────────────────────────────────────────────────────┐
│ Runs are created AUTOMATICALLY by the system:          │
│                                                         │
│ 1. Create config with frequency (every_30_min)        │
│ 2. System calculates next_scheduled_run_at            │
│ 3. Scheduler creates run when time arrives            │
│ 4. After completion, next run is scheduled            │
│                                                         │
│ You don't manually schedule runs via API!             │
│ The config's frequency setting controls scheduling.   │
└─────────────────────────────────────────────────────────┘

Example Flow:
┌─────────────────────────────────────────────────────────┐
│ Config created:                                         │
│   trigger_mode: "scheduled"                            │
│   frequency: "every_30_min"                            │
│   next_scheduled_run_at: "2025-01-15T11:00:00Z"       │
│                                                         │
│ At 11:00 → System creates run automatically           │
│ At 11:30 → System creates next run automatically      │
│ At 12:00 → System creates next run automatically      │
│ ...continues based on frequency...                     │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Monitoring Runs API

### LIST Runs

**View execution history**

```
GET /monitoring-configs/{config_id}/runs
    ?status=completed
    &result=fail
    &start_date=2025-01-01
    &limit=50

Response:
┌─────────────────────────────────────────────────────────┐
│ {                                                       │
│   "runs": [                                            │
│     {                                                  │
│       "id": "run-123",                                 │
│       "trigger_source": "auto",                        │
│       "trigger_metadata": {                            │
│         "bucket": "cameras",                          │
│         "key": "store-123/front-counter/...",         │
│         "event_time": "2025-01-15T10:29:58Z"         │
│       },                                              │
│       "scheduled_at": "2025-01-15T10:30:00Z",         │
│       "status": "completed",                          │
│       "result": "fail",                               │
│       "execution_duration_ms": 6240,                  │
│       "captured_data_preview": {                      │
│         "type": "image",                             │
│         "thumbnail_url": "https://..."               │
│       },                                              │
│       "evaluation_summary": "Counter has debris",     │
│       "alert_generated": true                         │
│     }                                                  │
│   ],                                                   │
│   "summary": {                                         │
│     "total_runs": 1250,                               │
│     "success_rate": 0.944                             │
│   }                                                    │
│ }                                                       │
└─────────────────────────────────────────────────────────┘

trigger_source values:
- "manual_api": Triggered via POST /monitoring-configs/{id}/run
- "auto": Triggered by S3 image upload event
- "scheduled": Triggered by scheduler (Phase 2)
```

**Why**: Review check history and identify patterns

---

### GET Run Details

**View specific execution**

```
GET /monitoring-runs/{run_id}

Response:
┌─────────────────────────────────────────────────────────┐
│ Complete execution details:                             │
│ • Timeline (scheduled → started → completed)           │
│ • Captured data (image URL, sensor reading)            │
│ • Evaluation result (AI analysis or threshold check)   │
│ • Alerts generated (if any)                            │
│ • Error information (if failed)                        │
└─────────────────────────────────────────────────────────┘
```

**Why**: Investigate specific check result in detail

---

### EXPORT Runs

**Download history for compliance**

```
GET /monitoring-configs/{config_id}/runs/export
    ?start_date=2025-01-01
    &end_date=2025-01-31
    &format=csv

Response: CSV file
┌─────────────────────────────────────────────────────────┐
│ run_id,scheduled_at,result,evaluation_summary,...      │
│ run-123,2025-01-15T10:30:00Z,fail,Counter debris,...   │
└─────────────────────────────────────────────────────────┘
```

**Why**: Generate compliance reports or data analysis

---

## Standard Responses

### Success Response

```json
{
  "success": true,
  "data": { ... }
}
```

### Error Response

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input",
    "details": { ... }
  }
}
```

---

## Common Error Codes

| Code                     | Status | Meaning                              |
| ------------------------ | ------ | ------------------------------------ |
| `VALIDATION_ERROR`       | 400    | Invalid request data                 |
| `UNAUTHORIZED`           | 401    | Missing/invalid auth token           |
| `FORBIDDEN`              | 403    | No permission for resource           |
| `NOT_FOUND`              | 404    | Resource doesn't exist               |
| `CONFIG_HAS_OPEN_ALERTS` | 409    | Can't delete config with open alerts |
| `SOURCE_IN_USE`          | 409    | Can't delete source (configs use it) |
| `RATE_LIMIT_EXCEEDED`    | 429    | Too many requests                    |

---

## Pagination

All list endpoints support pagination:

```
?limit=50     → Items per page (max 100)
?offset=0     → Skip N items

Response includes:
{
  "data": [...],
  "total": 1250,
  "limit": 50,
  "offset": 0,
  "has_more": true
}
```

---

## Rate Limits

| Operation        | Limit    | Window |
| ---------------- | -------- | ------ |
| Read (GET)       | 1000 req | 1 min  |
| Write (POST/PUT) | 100 req  | 1 min  |
| Delete           | 50 req   | 1 min  |
| Manual triggers  | 10 req   | 1 min  |

Response headers:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 987
X-RateLimit-Reset: 1642262400
```

---

## Quick Reference

### Common Workflows

**Setup New Monitoring**

```
1. POST /projects/{id}/monitoring-configs  → Create config
2. POST /monitoring-configs/{id}/run       → Test immediately
3. GET  /projects/{id}/alerts              → Watch for alerts
```

**Daily Operations**

```
1. GET /projects/{id}/monitoring/dashboard → Check overview
2. GET /projects/{id}/alerts?status=open   → Review open alerts
3. POST /alerts/{id}/acknowledge           → Acknowledge alerts
4. POST /alerts/{id}/resolve               → Mark fixed
```

**Troubleshooting**

```
1. GET /monitoring-configs/{id}/runs       → View history
2. GET /monitoring-runs/{id}               → Check specific run
3. POST /monitoring-configs/{id}/run       → Manual test
```

**Reporting**

```
1. GET /monitoring-configs/{id}/runs/export → Download CSV
2. GET /projects/{id}/monitoring/analytics  → Get trends
```
