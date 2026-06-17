# Catering Request Phone Lookup Index

Date: 2026-06-12

## Summary

Added a database index to support efficient catering request lookups by project
and requester phone number. The index stores the normalized digit-only contact
phone expression alongside `project_id` and `created_at DESC`, matching the
agent overwrite/prior-request lookup path that needs newest requests first.

## Migration

- `9d7e1f4a6b2c` adds
  `ix_catering_requests_project_phone_digits_created_at` on
  `catering_requests`.

## Notes

The runtime query change is intentionally split into a follow-up PR so the
schema migration can land independently.
