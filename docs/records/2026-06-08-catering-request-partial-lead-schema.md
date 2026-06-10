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
- 2026-06-10 follow-up: repository DTOs, API schemas, service methods, public
  detail DTOs, and agent catering persistence now accept and return missing
  event dates, missing requester phone numbers, and optional requester email.
- Date/phone-dependent notification paths guard partial leads instead of
  fabricating placeholder dates or phone numbers.

## Migration

Alembic revision: `4caa090da0f5`.

## Follow-Up

Email-forwarding ingestion can now build on the nullable runtime adapters.
