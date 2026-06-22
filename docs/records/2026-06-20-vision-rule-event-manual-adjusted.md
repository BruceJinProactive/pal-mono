# Vision Rule Event Manual Adjustment Schema

Date: 2026-06-20

## Summary

Added the `vision_rule_event.manually_adjusted` storage column as a non-null
boolean with default `false` so downstream analytics and review workflows can
distinguish generated rule events from rows corrected or created by a human.

## Scope

- This schema-only change adds the column to the SQLAlchemy table model and
  Alembic migration.
- Existing and newly generated rows default to `manually_adjusted=false` until
  the follow-up implementation starts writing human-adjustment state.
- API schemas, repositories, service behavior, and Admin Console payload wiring
  are intentionally excluded from this PR because DB schema changes must ship in
  a separate pal-mono PR.

## Migration

`3fa8e1aa036a` adds the column to `vision_rule_event` and merges the two current
main migration heads (`a91c4f2e8b7d`, `128e03e17ca5`) into one head.
