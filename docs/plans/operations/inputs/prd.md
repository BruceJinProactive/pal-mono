# Input Sources System - Product Requirements Document

## Overview

Input Sources provide a unified abstraction for data providers that feed into the monitoring and operations systems. An input source represents any device, service, or data stream that can be captured, analyzed, or monitored. This document defines V1 with a focus on **camera devices**.

Input Sources are decoupled from their consumers (Monitoring, Routines, etc.) - they simply provide data that other systems can reference and use.

---

## Core Concepts

### Input Source

An **Input Source** represents a physical or virtual data provider registered with the system.

| Property | Description |
|----------|-------------|
| Type | Category of source (Device, Weather Feed, Data Feed, Observation) |
| Subtype | Specific kind within type (Camera, Temperature Sensor, etc.) |
| Scope | Account-level (shared) or Project-level (store-specific) |
| Status | Connection/health state (active, inactive, error) |
| Configuration | Type-specific settings (credentials, URLs, etc.) |

**Key Properties:**
- Sources can be **account-level** (shared across all projects in an account) or **project-level** (specific to one store)
- A source is **reusable** - multiple monitoring configs or routines can reference the same source
- Sources are **input-agnostic** to consumers - they just provide data

### Feed

A **Feed** represents a data stream produced by an input source.

| Property | Description |
|----------|-------------|
| Source | The input source that produces this feed |
| Type | Kind of data (image_snapshot, video_stream, numeric_reading) |
| Capture Mode | How data is obtained (pull/scheduled, push/event-driven, continuous) |
| Status | Current feed state (active, paused, error) |

**V1 Scope:** One feed per source (1:1 relationship). The system is designed for future extensibility to support multiple feeds per source (e.g., a camera providing both live stream and periodic snapshots as separate feeds).

### Source Types

| Type | Description | V1 Status |
|------|-------------|-----------|
| Device | Physical devices at the store | **Included** (cameras only) |
| Weather Feed | Weather data for location | Future |
| Data Feed | External API integrations | Future |
| Observation | Staff-submitted reports | Future |

---

## V1: Camera Device Types

V1 focuses exclusively on camera devices with three integration approaches:

### RTSP/IP Camera

Standard network cameras accessible via RTSP protocol.

| Configuration | Description | Required |
|---------------|-------------|----------|
| `rtsp_url` | RTSP stream URL | Yes |
| `username` | Authentication username | No |
| `password` | Authentication password | No |
| `snapshot_url` | HTTP URL for still image capture | No |
| `snapshot_interval` | Seconds between captures | No (default: 300) |

**Use Cases:** On-premise IP cameras, NVR systems, generic network cameras

### Cloud Camera API

Integration with managed camera service providers.

| Configuration | Description | Required |
|---------------|-------------|----------|
| `provider` | Service provider (verkada, rhombus, ring, etc.) | Yes |
| `api_key` | Provider API key/token | Yes |
| `device_id` | Camera identifier in provider system | Yes |
| `location_id` | Location/site ID if required by provider | No |

**Supported Providers (V1):**
- Verkada
- Rhombus
- Ring (Business)
- Additional providers added based on demand

### S3 Recording

Video recordings uploaded to S3 storage for analysis.

| Configuration | Description | Required |
|---------------|-------------|----------|
| `bucket` | S3 bucket name | Yes |
| `prefix` | Object key prefix for this source | Yes |
| `file_pattern` | Glob pattern for matching files | No (default: `*.mp4`) |
| `polling_interval` | Seconds between checks for new files | No (default: 60) |
| `region` | AWS region | No (uses default) |

**Use Cases:** Uploaded surveillance footage, body cam recordings, VM exports from local systems

---

## Entity Relationships

```
┌─────────────────────────────────────────────────────────────────┐
│                         ACCOUNT                                 │
│  (business account - e.g., restaurant chain)                   │
└─────────────────────────────────────────────────────────────────┘
         │
         │ owns (1:N)
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      INPUT SOURCE                               │
│  - Can be account-level OR project-level                       │
│  - Type: Device (V1: Camera), Weather, Data Feed, Observation  │
│  - Stores connection config and credentials                    │
│  - Tracks health/connectivity status                           │
└─────────────────────────────────────────────────────────────────┘
         │
         │ produces (1:1 in V1, 1:N future)
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                         FEED                                    │
│  - Data stream from source                                     │
│  - Type: image_snapshot, video_stream, numeric_reading         │
│  - Capture mode: pull (scheduled) or push (event-driven)       │
│  - Auto-created with source in V1                              │
└─────────────────────────────────────────────────────────────────┘
         │
         │ referenced by (N:1)
         ▼
┌─────────────────────────────────────────────────────────────────┐
│              MONITORING CONFIG / ROUTINE TASK                   │
│  (consumers of feed data - defined in other PRDs)              │
└─────────────────────────────────────────────────────────────────┘
```

### Project-Level Sources

```
┌─────────────────────────────────────────────────────────────────┐
│                         PROJECT                                 │
│  (store location - belongs to one account)                     │
└─────────────────────────────────────────────────────────────────┘
         │
         │ owns (1:N)
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   INPUT SOURCE (project-level)                  │
│  - Specific to this store only                                 │
│  - Not visible to other projects in account                    │
└─────────────────────────────────────────────────────────────────┘
```

### Scoping Rules

| Scope | Visible To | Managed By | Use Case |
|-------|------------|------------|----------|
| Account-level | All projects in account | Account admins | Shared cameras, corporate standards |
| Project-level | Single project only | Project managers | Store-specific cameras |

**Resolution:** When a project looks for available sources, it sees:
1. All account-level sources for its parent account
2. All project-level sources registered to itself

---

## Features

### 1. Source Management

**Who:** Account admins, Project managers

**Capabilities:**
- Register new input sources (camera devices in V1)
- Configure source-specific settings (URLs, credentials, etc.)
- Set source scope (account-level or project-level)
- View source status and health
- Test source connectivity
- Update source configuration
- Deactivate/reactivate sources
- Delete sources (with safeguard if referenced by active configs)

### 2. Feed Management

**V1 Behavior:** Feeds are auto-created 1:1 with sources. No separate feed management UI.

**Capabilities:**
- View feed status and last capture time
- View feed capture history
- Manually trigger feed capture (for testing)
- View feed error logs

### 3. Camera-Specific Features

**RTSP Cameras:**
- Connection test with preview image
- Credential validation
- Stream format detection (H.264, H.265)

**Cloud Cameras:**
- OAuth/API key validation
- Device discovery (list available cameras from provider)
- Provider-specific capabilities detection

**S3 Recordings:**
- Bucket access validation
- File pattern testing with sample matches
- New file detection preview

### 4. Health Monitoring

**Capabilities:**
- Automatic periodic health checks
- Connection failure detection and alerting
- Stale feed detection (no new data)
- Health history and uptime tracking

---

## User Flows

### Manager Registers an RTSP Camera

1. Manager navigates to Input Sources
2. Selects "Add Source" → "Camera" → "RTSP/IP Camera"
3. Enters camera name and description
4. Enters RTSP URL and optional credentials
5. Chooses scope: account-level or project-level
6. Clicks "Test Connection" - sees preview image
7. Saves source
8. Feed is auto-created and begins capturing

### Manager Connects Cloud Camera Service

1. Manager navigates to Input Sources
2. Selects "Add Source" → "Camera" → "Cloud Camera"
3. Selects provider (Verkada, Rhombus, etc.)
4. Enters API credentials
5. System fetches available cameras from provider
6. Manager selects camera(s) to register
7. Chooses scope for each camera
8. Sources and feeds are created

### Manager Configures S3 Recording Source

1. Manager navigates to Input Sources
2. Selects "Add Source" → "Camera" → "S3 Recording"
3. Enters S3 bucket and prefix
4. Configures file pattern (e.g., `*.mp4`)
5. System validates bucket access and shows sample matching files
6. Chooses scope and polling interval
7. Saves source
8. Feed begins monitoring for new files

### System Captures Feed Data

1. Scheduled capture time arrives (or new S3 file detected)
2. System connects to source based on type
3. Captures data (snapshot, video clip, or file reference)
4. Stores capture with timestamp and metadata
5. Updates feed status and last_capture_at
6. Data is now available for monitoring configs to analyze

---

## MVP Scope

### Included in V1

**Source Types:**
- Device type only (cameras)

**Camera Subtypes:**
- RTSP/IP cameras
- Cloud camera APIs (Verkada, Rhombus, Ring)
- S3 uploaded recordings

**Scoping:**
- Account-level sources
- Project-level sources

**Feed Model:**
- Single feed per source (1:1)
- Image snapshot capture mode
- Scheduled (pull) capture

**Features:**
- Full source CRUD
- Connection testing
- Health monitoring
- Capture history

### Future Phases

**Source Types:**
- Weather Feed sources
- Data Feed sources (external APIs)
- Observation sources (staff-submitted)

**Feed Model:**
- Multiple feeds per source (1:N)
- Video stream feeds
- Push/event-driven capture
- Feed aggregation (combine multiple feeds)

**Camera Enhancements:**
- Additional cloud providers
- Motion-triggered capture
- Video clip extraction
- PTZ camera control

**Advanced Features:**
- Source templates (pre-configured settings)
- Bulk source import
- Source groups/tags

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Source connectivity uptime | >99% |
| Feed capture success rate | >98% |
| Connection test response time | <5 seconds |
| Time to register new source | <2 minutes |
| Health check detection latency | <5 minutes |
| Source configuration errors | <5% of registrations |
