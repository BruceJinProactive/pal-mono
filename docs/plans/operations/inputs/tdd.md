# Signal Sources System - Technical Design Document

## Overview

Signal Sources provide a unified abstraction for data providers that feed into monitoring and operations systems.

**V1 Scope:** Camera devices only (RTSP, Cloud Camera APIs, S3 Recordings)

**Key Principles:**
- Signal sources are decoupled from consumers (Monitoring, Routines)
- Sources are reusable across multiple monitoring configs
- Type-safe configuration using Pydantic discriminated unions

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ACCOUNT                                         │
│  (business account - e.g., restaurant chain)                                │
│                                                                              │
│  Can own ACCOUNT-LEVEL signal sources (shared across all projects)          │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         │ has many (1:N)
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PROJECT                                         │
│  (store location - e.g., "Downtown Store")                                  │
│                                                                              │
│  Can own PROJECT-LEVEL signal sources (specific to this store)              │
│  Cameras are TYPICALLY project-level (physically at the store)              │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         │ owns (1:N)
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SIGNAL SOURCE                                       │
│                                                                              │
│  OWNERSHIP MODEL:                                                           │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  account_id (required) - which account this belongs to             │     │
│  │  project_id (nullable) - if set, owned by project; if NULL, owned  │     │
│  │                          by account and shared across all projects │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│  V1 SIGNAL TYPE: Camera only                                                │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │   Camera (signal_type: "camera")                                │        │
│  │                                                                  │        │
│  │   Subtypes:                                                     │        │
│  │   ├── RTSP/IP Camera (subtype: "rtsp")                         │        │
│  │   ├── Cloud Camera (subtype: "cloud") - Verkada, Rhombus, Ring │        │
│  │   └── S3 Recording (subtype: "s3")                             │        │
│  └─────────────────────────────────────────────────────────────────┘        │
│                                                                              │
│  Each source has type-specific config validated at API layer                │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         │ produces (1:1 in V1)
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SIGNAL FEED                                        │
│                                                                              │
│  - Data stream from source                                                  │
│  - Types: image_snapshot, video_stream                                      │
│  - Capture modes: pull (scheduled), push (event-driven)                     │
│  - Auto-created with source in V1                                           │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         │ referenced by (N:1)
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONSUMERS (defined in other PRDs)                         │
│                                                                              │
│  - Monitoring Configs (continuous checks)                                   │
│  - Routine Tasks (camera auto-verification)                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Table: `signal_sources`

**Ownership Model:**
- `account_id` (required): The account this source belongs to
- `project_id` (nullable):
  - If **NULL** → Account-level source (shared, visible to all projects in account)
  - If **set** → Project-level source (owned by specific project, not visible to others)

**V1:** Cameras are typically project-level (physically at a store).

```sql
CREATE TABLE signal_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- OWNERSHIP
    account_id      UUID NOT NULL,                    -- Always set (for multi-tenant isolation)
    project_id      UUID,                             -- NULL = account-level, SET = project-level

    -- IDENTITY
    signal_type     VARCHAR(50) NOT NULL DEFAULT 'camera',  -- V1: always "camera"
    name            VARCHAR(255) NOT NULL,
    description     TEXT,

    -- STATUS
    status          VARCHAR(50) NOT NULL DEFAULT 'active',  -- enum: active, inactive, error
    status_message  TEXT,                             -- Human-readable status
    last_health_check_at TIMESTAMP WITH TIME ZONE,

    -- TYPE-SPECIFIC CONFIGURATION
    config          JSONB NOT NULL,                   -- Validated by Pydantic

    -- TIMESTAMPS
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX signal_sources_account_id_idx ON signal_sources(account_id);
CREATE INDEX signal_sources_project_id_idx ON signal_sources(project_id);
CREATE INDEX signal_sources_status_idx ON signal_sources(status);
CREATE INDEX signal_sources_visibility_idx ON signal_sources(account_id, project_id);
```

**Visibility Query:**
```sql
-- Get all sources visible to a specific project
SELECT * FROM signal_sources
WHERE account_id = :account_id
  AND (project_id IS NULL OR project_id = :project_id);
```

### Table: `signal_feeds`

```sql
CREATE TABLE signal_feeds (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID NOT NULL,                    -- No FK, managed in code

    feed_type       VARCHAR(50) NOT NULL,             -- enum: image_snapshot, video_stream
    capture_mode    VARCHAR(50) NOT NULL,             -- enum: pull, push

    status          VARCHAR(50) NOT NULL DEFAULT 'active',
    status_message  TEXT,

    last_capture_at TIMESTAMP WITH TIME ZONE,
    capture_count   INTEGER NOT NULL DEFAULT 0,

    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX signal_feeds_source_id_idx ON signal_feeds(source_id);
```

**Note:** No foreign key constraints. Relationship managed in service layer (delete feed when source deleted).

### Capture Storage (V1)

**Captures are stored in S3 only, not in SQL.**

For 20-50 cameras capturing every 30 seconds, we avoid table bloat by:
- Storing images directly in S3: `s3://bucket/captures/{source_id}/{timestamp}.jpg`
- Updating `signal_feeds.last_capture_at` on each capture (single row UPDATE)
- No `signal_feed_captures` table in V1

**Camera online detection:**
```sql
-- Camera is online if captured within last 2 minutes
SELECT * FROM signal_feeds
WHERE last_capture_at > NOW() - INTERVAL '2 minutes'
```

**Autovacuum tuning (optional for frequent updates):**
```sql
ALTER TABLE signal_feeds SET (
  autovacuum_vacuum_scale_factor = 0.1,
  autovacuum_analyze_scale_factor = 0.05
);
```

**Future scale (500+ cameras):** Consider Redis for heartbeats with TTL.

---

## Enums

Location: `db/tables/types.py`

```python
import enum

class SignalType(str, enum.Enum):
    """Type of signal source (V1: camera only)"""
    camera = "camera"

class CameraSubtype(str, enum.Enum):
    """Subtype for camera signals"""
    rtsp = "rtsp"
    cloud = "cloud"
    s3 = "s3"

class CloudCameraProvider(str, enum.Enum):
    """Supported cloud camera providers"""
    verkada = "verkada"
    rhombus = "rhombus"
    ring = "ring"

class SignalSourceStatus(str, enum.Enum):
    """Status of a signal source"""
    active = "active"
    inactive = "inactive"
    error = "error"

class SignalFeedStatus(str, enum.Enum):
    """Status of a signal feed"""
    active = "active"
    paused = "paused"
    error = "error"

class FeedType(str, enum.Enum):
    """Type of data produced by a feed"""
    image_snapshot = "image_snapshot"
    video_stream = "video_stream"

class CaptureMode(str, enum.Enum):
    """How feed data is obtained"""
    pull = "pull"
    push = "push"
```

---

## Configuration Schemas

### V1: Camera Only

Different camera subtypes require different configuration fields. Pydantic discriminated unions ensure type-safe validation.

```python
from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, Field

# ============================================================================
# CAMERA SUBTYPE CONFIGS
# ============================================================================

class RTSPCameraConfig(BaseModel):
    """Configuration for RTSP/IP cameras"""
    subtype: Literal["rtsp"] = "rtsp"

    rtsp_url: str = Field(..., description="RTSP stream URL")
    username: Optional[str] = None
    password: Optional[str] = None  # Stored encrypted
    snapshot_url: Optional[str] = None
    snapshot_interval: int = Field(300, ge=10, le=3600)


class CloudCameraConfig(BaseModel):
    """Configuration for cloud camera APIs"""
    subtype: Literal["cloud"] = "cloud"

    provider: CloudCameraProvider
    api_key: str  # Stored encrypted
    device_id: str
    location_id: Optional[str] = None


class S3RecordingConfig(BaseModel):
    """Configuration for S3 uploaded recordings"""
    subtype: Literal["s3"] = "s3"

    bucket: str
    prefix: str
    file_pattern: str = "*.mp4"
    polling_interval: int = Field(60, ge=30, le=3600)
    region: Optional[str] = None


# Discriminated union for camera subtypes
CameraConfigDetails = Annotated[
    Union[RTSPCameraConfig, CloudCameraConfig, S3RecordingConfig],
    Field(discriminator="subtype")
]


# ============================================================================
# SIGNAL SOURCE CONFIG (V1: Camera only)
# ============================================================================

class CameraSignalConfig(BaseModel):
    """Configuration for camera signal sources"""
    signal_type: Literal["camera"] = "camera"
    camera: CameraConfigDetails


# V1: Only camera supported
# Future: SignalSourceConfig = Union[CameraSignalConfig, WeatherSignalConfig, ...]
SignalSourceConfig = CameraSignalConfig
```

### Config Structure

```json
{
  "config": {
    "signal_type": "camera",
    "camera": {
      "subtype": "rtsp",
      "rtsp_url": "rtsp://192.168.1.100:554/stream",
      "snapshot_interval": 300
    }
  }
}
```

### Validation Flow

```
API Request
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Pydantic Validation                                             │
│                                                                  │
│  1. config.signal_type = "camera" → CameraSignalConfig          │
│  2. config.camera.subtype = "rtsp" → RTSPCameraConfig           │
│  3. Validate required fields (rtsp_url present, etc.)           │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
Service Layer (type-safe config object)
    │
    ▼
Database (store as JSONB)
```

**Error case:**
```json
{
  "config": {
    "signal_type": "camera",
    "camera": {
      "subtype": "rtsp",
      "bucket": "my-bucket"  // Wrong field for RTSP!
    }
  }
}
// → 422: "rtsp_url is required"
```

---

## API Endpoints

### Base Path: `/v1/operations/signal-sources`

**V1 Endpoints (CRUD only):**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/signal-sources` | Create camera source |
| `GET` | `/signal-sources` | List sources |
| `GET` | `/signal-sources/{id}` | Get source details |
| `PATCH` | `/signal-sources/{id}` | Update source |
| `DELETE` | `/signal-sources/{id}` | Delete source |

---

### Create Signal Source

```
POST /v1/operations/signal-sources
```

**Request:**
```json
{
  "name": "Front Door Camera",
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "config": {
    "signal_type": "camera",
    "camera": {
      "subtype": "rtsp",
      "rtsp_url": "rtsp://192.168.1.100:554/stream",
      "snapshot_interval": 300
    }
  }
}
```

**Response:** `201 Created` - See response schema below.

---

### List Signal Sources

```
GET /v1/operations/signal-sources?project_id={uuid}
```

Returns project-level sources + account-level sources visible to the project.

**Response:** `200 OK`
```json
{
  "items": [ /* SignalSourceResponse[] */ ],
  "total": 10,
  "page": 1,
  "page_size": 20
}
```

---

### Get Signal Source

```
GET /v1/operations/signal-sources/{source_id}
```

**Response:** `200 OK` - See response schema below.

---

### Update Signal Source

```
PATCH /v1/operations/signal-sources/{source_id}
```

**Request:**
```json
{
  "name": "Updated Name",
  "config": { ... }
}
```

**Rules:**
- Cannot change `signal_type`
- Cannot change `project_id`

**Response:** `200 OK` - See response schema below.

---

### Delete Signal Source

```
DELETE /v1/operations/signal-sources/{source_id}
```

**Response:** `204 No Content`

**Rules:**
- Returns `409 Conflict` if referenced by monitoring configs or routines

---

### Response Schema

```json
{
  "id": "uuid",
  "account_id": "uuid",
  "project_id": "uuid",
  "name": "Front Door Camera",
  "signal_type": "camera",
  "status": "active",
  "status_message": null,
  "config": {
    "signal_type": "camera",
    "camera": {
      "subtype": "rtsp",
      "rtsp_url": "rtsp://192.168.1.100:554/stream",
      "snapshot_interval": 300
    }
  },
  "last_capture_at": "2024-01-15T10:30:00Z",
  "created_at": "2024-01-15T09:00:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

**Online detection:**
- `last_capture_at` within 2 minutes → camera is online
- `last_capture_at` > 2 min ago or `null` → camera is offline

---

## Service Layer

Location: `services/signal_source_service/`

```python
class SignalSourceService:
    async def create_source(session, account_id, request) -> SignalSource
    async def get_sources(session, account_id, project_id=None) -> List[SignalSource]
    async def get_source(session, account_id, source_id) -> SignalSource
    async def update_source(session, account_id, source_id, request) -> SignalSource
    async def delete_source(session, account_id, source_id) -> None
```

---

## Repository Layer

Location: `db/repositories/`

```python
class SignalSourceRepositoryAsync:
    async def create(source) -> SignalSource
    async def get_by_id(source_id) -> SignalSource
    async def get_by_account(account_id, project_id=None) -> List[SignalSource]
    async def update(source) -> SignalSource
    async def delete(source_id) -> bool

class SignalFeedRepositoryAsync:
    async def create(feed) -> SignalFeed
    async def get_by_source_id(source_id) -> SignalFeed
    async def update_last_capture(feed_id, captured_at) -> None
```

---

## Security

### Credential Storage

Sensitive fields (passwords, API keys) are encrypted before storage or stored in AWS Secrets Manager.

### Multi-Tenant Isolation

All queries filter by `account_id`.

---

## Integration

### Monitoring System

```python
# monitoring_configs table references signal_sources
signal_source_id: UUID
```

### Routines System

```python
# routine_items can reference signal sources for camera verification
verification_source_id: UUID
```

---

## Implementation Phases

### Phase 1: Database & CRUD (V1)
- Tables: `signal_sources`, `signal_feeds`
- Enums in `db/tables/types.py`
- Repositories
- Service layer (5 methods)
- API endpoints (5 CRUD endpoints)

### Phase 2: Capture Worker (V1)
- Scheduled capture to S3 (`s3://bucket/captures/{source_id}/{timestamp}.jpg`)
- Update `signal_feeds.last_capture_at` on each capture

### Future Phases
- Connection testing endpoint
- Health check history
- Notifications on camera offline

---

## Files to Create (V1)

| Layer | File |
|-------|------|
| Tables | `db/tables/signal_sources.py` |
| Tables | `db/tables/signal_feeds.py` |
| Enums | `db/tables/types.py` (add enums) |
| Repository | `db/repositories/signal_source_repository.py` |
| Repository | `db/repositories/signal_feed_repository.py` |
| Service | `services/signal_source_service/` |
| API | `api/routes/operations/signal_sources.py` |

**V1 Notes:**
- No `signal_feed_captures` table - captures stored in S3 only
- No `signal_source_health_checks` table - use `last_capture_at` for online status
