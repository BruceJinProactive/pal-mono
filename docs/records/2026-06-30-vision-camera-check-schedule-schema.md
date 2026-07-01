# Vision Camera Check Schedule Schema

> **Date:** 2026-06-30

## Summary

Added storage-only scheduling fields to `vision_camera_configuration` so each
camera configuration can later express whether routine checks run daily, weekly,
or not at all, along with the observation window, per-check frequency in minutes,
and weekly observation days.

This PR does not add API, repository, or runtime behavior. It only establishes
the database shape for a follow-up application-layer change.

## What Changed

- Added `check_mode` as a non-null `VARCHAR(10)` with default `daily`.
- Added nullable `check_start_time` and `check_end_time` `TIME` columns with
  defaults of `00:00:00` and `23:59:59.999999`.
- Added `check_frequency_minutes` as a non-null integer minute interval with
  default `1`.
- Added non-null `weekly_observation_days` as a `VARCHAR(9)[]` with all seven
  weekdays as the default.
- Added check constraints for valid `check_mode` values, required time windows
  unless checks are disabled, positive minute frequency, non-empty weekly day
  lists, and valid weekday values.

## Migration

- `b8a16f03f3bf`: add vision camera configuration check schedule fields.

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Default `check_mode` to `daily` | Existing and newly created camera configurations should continue to be observed by default. |
| Store frequency as integer minutes with default `1` | Minute granularity matches the expected scheduler control and gives new rows a one-minute cadence unless configured otherwise. |
| Store weekdays as a constrained text array | The allowed values are simple, stable, and easy for future API schemas to mirror without introducing a PostgreSQL enum. |
| Keep repository/API/runtime wiring out of this PR | DB schema changes are split from non-schema work by CI, so application behavior should land separately. |
