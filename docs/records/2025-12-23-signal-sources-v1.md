# Signal Sources (Input Sources) System V1

> **Date:** 2025-12-23

## Summary

Implemented a unified abstraction for data providers (signal sources) that feed into monitoring and operations systems. V1 focuses on camera devices with three subtypes: RTSP/IP cameras, cloud camera APIs, and S3 recordings.

## What Was Built

### Database (2 tables)

- **`signal_sources`**: id, account_id, project_id (nullable for account-level scope), signal_type enum, name, description, status enum, status_message, config (JSONB for type-specific settings), created_at, updated_at
- **`signal_feeds`**: id, source_id, feed_type enum, capture_mode enum, status enum, status_message, last_capture_at, last_capture_url, capture_count, created_at, updated_at

### Enums (`db/tables/types.py`)

- `SignalType`: camera (extensible for weather, data_feed, observation)
- `CameraSubtype`: rtsp, cloud, s3
- `CloudCameraProvider`: verkada, rhombus, ring
- `SignalSourceStatus`: active, inactive, error
- `SignalFeedStatus`: active, paused, error
- `FeedType`: image_snapshot, video_stream, numeric_reading
- `CaptureMode`: pull, push, continuous

### API Endpoints (`api/routes/operation/_signal_sources.py`)

Full CRUD: create, list, get, update, delete signal sources + `get_by_camera_id` helper. Presigned URL generation for S3 feed URLs. Video upload at `/cameras/{camera_id}/upload-video`.

### Schemas (`api/schemas/operations/signal_source.py`)

Pydantic discriminated union for camera config: `RTSPCameraConfig`, `CloudCameraConfig`, `S3RecordingConfig` — each with type-specific fields matching the PRD.

### Scoping

- Account-level sources: `project_id = NULL` (shared across all projects)
- Project-level sources: `project_id` set (specific to one store)
- Resolution: projects see their own sources + parent account sources

### Repository (`db/repositories/signal_source_repository.py`)

Async repository: create, get_by_id, get_by_account, update, delete, get_by_camera_id, camera_id_exists, get_cameras_with_feeds_by_account_names.

## Key Files

| Component | File |
|-----------|------|
| DB model (sources) | `db/tables/signal_sources.py` |
| DB model (feeds) | `db/tables/signal_feeds.py` |
| Enums | `db/tables/types.py` |
| API routes | `api/routes/operation/_signal_sources.py` |
| API schemas | `api/schemas/operations/signal_source.py` |
| Repository | `db/repositories/signal_source_repository.py` |
| Video upload | `api/routes/operation/_video_upload.py` |

## Origin

Plan: `docs/plans/operations/inputs/` (PRD + TDD, now archived)
