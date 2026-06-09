# Catering Request Partial-Lead Schema

Date: 2026-06-08

## Summary

Updated the catering request database schema so Palona can persist incomplete
catering inquiries as lead records before every operational detail is known.
This supports future email-forwarding ingestion and similar intake channels
where requester email, event date, or phone number may be missing or discovered
later.

## Implementation Notes

- Added nullable `catering_requests.contact_email`.
- Made `catering_requests.event_date` nullable.
- Made `catering_requests.contact_phone_number` nullable.
- Kept this PR schema-only: runtime repository, API, service, and test adapters
  are intentionally deferred to the follow-up implementation branch.

## Migration

Alembic revision: `4caa090da0f5`.

## Follow-Up

The follow-up implementation should update repository/data-class/API/service
layers to accept the nullable fields, then layer the email-forwarding ingestion
logic on top.
