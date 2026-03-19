# Google Business Hours Updater

> **Date:** 2025-11-14

## Summary

Implemented an event-driven system to sync restaurant business hours from Google Places API to the database and knowledge base. The system uses EventBridge for decoupled processing and internal API endpoints for data updates.

## What Was Built

### Database

- **`projects` table extended** with `google_place_id` column — links each store location to its Google Business Profile
- Business hours stored via existing `store_hours` field (human-readable) and structured update endpoints

### Event Schema

- **`GoogleBusinessHoursUpdateRequested`** event in `events/schema.py` — detail type `integration.google.BusinessHoursUpdateRequested`
- Carries project_id, account_id, google_place_id, namespace for downstream processing

### Internal API Endpoints

- **Discovery endpoint** (`/internal/business-hours-update`): Queries all projects with `google_place_id`, publishes one EventBridge event per project needing updates
- **Project update endpoint** (`/internal/projects/{project_id}/business-hours`): Accepts structured hours data, updates project record and human-readable `store_hours` field

### Architecture Flow

```
EventBridge Scheduler → Discovery Endpoint → Publish events per project
                                                    ↓
                                            EventBridge bus
                                                    ↓
                                        Lambda (fetches Google Places)
                                                    ↓
                                        Internal API (updates DB + KB)
```

## Key Files

| Component | File |
|-----------|------|
| Event schema | `events/schema.py` (GoogleBusinessHoursUpdateRequested) |
| Discovery endpoint | `api/routes/internal/__init__.py` |
| Project update endpoint | `api/routes/internal/projects.py` |
| DB model | `db/tables/projects.py` (google_place_id column) |

## Origin

Plan: `docs/plans/business-updater/google-business-hours.md` (now archived)
