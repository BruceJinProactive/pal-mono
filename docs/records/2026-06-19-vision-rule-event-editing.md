# Vision Rule Event Editing

> **Date:** 2026-06-19

## Summary

Added account-scoped editing for Vision AI rule event timing so operations users
can correct an event's timestamp and duration from the admin console without
deleting and recreating the event.

## What Changed

- Added `PATCH /accounts/{account_name}/rule-events/{event_id}` behind the
  existing `account.write` permission gate.
- Added an update request schema with required `triggered_at` and non-negative
  `duration` fields. `duration` stays in the existing API unit of minutes.
- Updated the repository path to verify the event belongs to the requested
  account before updating it.
- Preserved the event's rule, entity, linked state-change event, severity, and
  metadata during timing edits.

## Notes

`vision_rule_event.triggered_at` is part of the table's partition key, so the
repository first loads the account-owned row and then updates by both `id` and
the current `triggered_at` value.
