# Continuous Monitoring System V1

> **Date:** 2025-12-29

## Summary

Implemented automated, scheduled monitoring of store operations via AI-powered analysis of camera feeds. Monitoring configs define what to check, when, and against what reference — monitoring runs execute checks and store pass/fail results.

## What Was Built

### Database (2 tables + index)

- **`monitoring_configs`**: id, project_id, signal_source_id, name, description, rules (JSONB containing AI analysis rules, scheduling, reference images), enabled, created_at, updated_at
- **`monitoring_runs`**: id, monitoring_config_id, trigger_metadata, started_at, completed_at, evaluation_result (JSONB), error_message. Composite index `ix_monitoring_runs_config_started` on (config_id, started_at DESC).

### Rules JSONB Structure

Contains: AI analysis rules (context/prompt, pass_criteria, fail_criteria), reference images (S3 URLs with pass/fail flags), monitoring time window (start_time, end_time, enabled), structured output fields.

### API Endpoints (12 in `_monitoring.py`)

Configs: create, list, get, update, delete. Runs: trigger, test, list, get, delete, batch_delete, rerun. All scoped to `/operation/projects/{project_id}/monitoring/`.

### Monitoring Service (7 modules)

| Module | Purpose |
|--------|---------|
| `_implementation.py` | Core logic: create/update/delete configs, trigger runs, reference image management |
| `_llm.py` | LLM-driven image/video analysis with prompt construction and structured outputs |
| `_providers.py` | Provider abstraction: Azure OpenAI + Google Gemini, native video support |
| `_video.py` | Video frame extraction and processing utilities |
| `_time_window.py` | Scheduling time window validation and enforcement |
| `_business_hours.py` | Business hours integration for monitoring schedules |
| `__init__.py` | Service facade |

### Reference Images

S3-based upload to `monitoring/reference_images/{project_id}/{config_id}/{uuid}{ext}` with per-image metadata (description, pass/fail flag). Presigned URL generation for frontend display.

### Internal API

`api/routes/internal/monitoring.py` — internal endpoints for monitoring run processing and config discovery (used by scheduled processors).

## Key Files

| Component | File |
|-----------|------|
| DB models | `db/tables/monitoring_configs.py`, `db/tables/monitoring_runs.py` |
| API routes | `api/routes/operation/_monitoring.py` |
| API schemas | `api/schemas/operations/monitoring.py` |
| Service | `services/monitoring_service/` (7 modules) |
| Internal routes | `api/routes/internal/monitoring.py` |

## Origin

Plan: `docs/plans/operations/monitoring/` (PRD + API-v1 + DB-v1 + processor-v1 + camera-health-v1, now archived)
