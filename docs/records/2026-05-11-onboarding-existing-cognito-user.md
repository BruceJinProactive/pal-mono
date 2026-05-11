# Onboarding: attach existing Cognito users instead of failing

**Date:** 2026-05-11
**Ticket:** PAL-10487 (phase 2)
**Scope:** `services/admin_service/_implementation.py::create_account_user`

## Problem

`POST /onboarding` (pal-manage-app "New Account" dialog) failed with
`UsernameExistsException` whenever the client email was already present in the
admin Cognito user pool — even if the user was a member of a completely
different account. Operators saw a hard *"Failed to create account"* error and
no new account was created (the service wrapped the exception in
`ValueError(...)` and rolled back the transaction).

Observed in production Loki (2026-05-11 19:46 UTC) during an internal invite
test — the affected email was already present in the Cognito pool from a
prior test, but not attached to the target account.

## Change

`create_account_user` now handles three paths:

1. **New Cognito user** — `admin_create_user` succeeds → create `account_user`
   row → send welcome email with the temporary password (unchanged behaviour).
2. **Existing Cognito user** — `admin_create_user` raises
   `UsernameExistsException` → look up the existing `sub` via `admin_get_user`
   → create the `account_user` row pointing at that `sub` → **skip the
   welcome-with-temp-password email** (they already have credentials).
3. **Already a member of this account** — `account_user_repo.get_by_email_and_account`
   returns a row → no new row, no email (idempotent).

The function was split into three helpers to keep each path readable:

- `_get_cognito_user_sub(cognito_client, email)`
- `_attach_user_to_account(session, account_name, email, name, sub)`
- `_send_welcome_email(email, name, account_name, password)`

Unrelated `ClientError` codes still raise as before.

**Behaviour change — attachment failures now propagate.** The previous
implementation wrapped the DB attachment step in a broad `except Exception`
and set `newly_attached = False` on any failure, so the function could return
`CognitoUser(...)` successfully even though the membership row was never
written. That was wrong: a user who isn't attached can't access the account,
and the caller has no way to tell. After this PR, any exception from
`_attach_user_to_account` (DB error, constraint violation, account-not-found)
propagates to the caller so onboarding either succeeds completely or fails
loudly.

## Rationale

The previous code raised on *any* `ClientError` from `admin_create_user`,
conflating "user pool rejected bad input" with "user already exists globally".
The latter is a legitimate state: a user can belong to multiple accounts. The
newer `team_service.create_invitation` flow already handled this
([services/team_service/_implementation.py L263-278](../../services/team_service/_implementation.py));
this change brings the onboarding path in line.

The welcome email is suppressed for existing users because it contains a fresh
temporary password that would be invalid (the user already has their own).
Sending it would be confusing at best and a credential-exposure risk at worst.

## Non-goals / follow-ups

- We do **not** send an alternative "you've been added to account X" email to
  existing users. The operator creating the account is expected to notify them
  out-of-band, or the frontend can surface the account's URL. If this becomes a
  recurring ask, introduce a second Postmark template.
- No role assignment is done here. The pal-manage-app frontend was updated in
  phase 1 (PAL-10487, PR #633) to call `PATCH /accounts/{name}/team/{email}`
  after onboarding to set the Owner role.

## Tests

`tests/services/admin_service/test_create_account_user.py` — 6 tests:

- new Cognito user → row created + welcome email sent
- **existing Cognito user → row created, welcome email NOT sent** (regression test for this ticket)
- already a member → no row, no email (idempotent)
- unknown Cognito `ClientError` code → still raises `ValueError`
- account not found → raises `ValueError("...not found")`
- missing `sub` in Cognito response → raises `ValueError`

All pass. `./scripts/validate.sh` clean on the touched files (the pre-existing
E402 in `services/realtime_service/_implementation.py` is unrelated).
