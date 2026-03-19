# Monitoring Config Restructure

> **Date:** 2026-03-09

## Summary

Restructured the monitoring configuration to use structured criteria instead of free-text prompts. This aligns monitoring configs with the routines pattern and improves AI evaluation consistency.

## What Changed

- **`prompt` → `context`**: Renamed with backward-compatible alias (if only `prompt` provided, it copies to `context`)
- **`pass_criteria` / `fail_criteria`**: New list fields replacing single-line monitoring criteria descriptions
- **`reference_images` made optional**: Were previously required (>= 1), now 0 or more allowed
- **Per-image `flag`**: Each reference image tagged as `pass` or `fail` example (defaults to `pass`)
- **`reference_image_flags`**: New endpoint parameter for upload-time flag assignment

## Key Files

| Layer | File | What |
|-------|------|------|
| Schema | `api/schemas/operations/monitoring.py` | `AIAnalysisRules` with context, pass_criteria, fail_criteria, ReferenceImage with flag |
| Routes | `api/routes/operation/_monitoring.py` | Create/update endpoints accepting new fields + reference_image_flags |
| Service | `services/monitoring_service/_implementation.py` | Config creation/update logic, upload_reference_images with flags |
| Tests | `tests/api/schemas/test_monitoring_config_restructure.py` | Schema-level validation tests |
| Tests | `tests/api/routes/operation/test_monitoring_config_validation.py` | Route-level validation tests |
| Tests | `tests/services/monitoring_service/test_config_restructure.py` | Service-layer tests for flags and criteria |

## Backward Compatibility

- Existing configs with `prompt` but no `context`: backend copies `prompt` → `context`
- Existing configs without criteria: default to `[]`
- Existing reference images without `flag`: default to `"pass"`

## Origin

Plan: `docs/plans/monitoring/2026-03-09-monitoring-config-restructure.md` (now archived)
