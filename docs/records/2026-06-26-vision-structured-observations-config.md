# Vision Structured Observations Config Schema

## Summary

Added `vision_camera_configuration.structured_observations_enabled`, a boolean camera
configuration flag that defaults to `false`.

The flag is storage-only in this schema change. Runtime Vision observation code
can use it to opt specific camera configurations into structured observations
before final state selection, while existing camera
configurations continue to use the current state-only output contract by
default.

## Migration

- `8b7c6d5e4f3a`: add `structured_observations_enabled` to
  `vision_camera_configuration`.

## Compatibility

Existing rows backfill to `false` through the non-null server default. Keeping
the default off preserves the current Vision observation schema and prompt for
all existing use cases until a camera configuration explicitly opts in.
