# Contract-to-Account Onboarding Implementation Plan

|                  |                                                             |
| ---------------- | ----------------------------------------------------------- |
| **Status**       | Draft                                                       |
| **PRD**          | `docs/plans/onboarding/contract-account-tos-handoff-prd.md` |
| **Last Updated** | 2026-06-25                                                  |

## Implementation Assumption

MVP flow:

1. AE manually creates the DocuSign contract/order form package:
   - SMB: order form + ToS.
   - Enterprise: order form + MSA.
2. AE waits for the customer to sign in DocuSign and manually verifies the
   signature. There is no MVP DocuSign API integration, embedded signing,
   webhook, or callback.
3. Once signature is verified, AE creates the account in Manage App. The form
   captures signer name/email and DocuSign envelope/contract/link references
   for records.
4. Manage App submit creates or links the account, sends the client invite, and
   starts handoff automation.
5. The logged-in AE and selected FDE are added as account owners without
   manually accepting invites.
6. The system saves contract acceptance details, updates Folk, creates the
   dedicated Slack channel, creates the Notion Client Master Database entry,
   and pings AE/FDE.
7. Client opens the account invite in Admin Console, sets a password, and is
   redirected to the Admin Console dashboard.

The system kickoff is Manage App account creation. Dashboard access is useful
telemetry, but it is not a dependency for handoff automation.

## MVP vs Post-MVP

### MVP: end-to-end working onboarding flow

MVP should prove the new onboarding path works from AE account creation through
client password setup and internal handoff.

MVP phases:

1. **Manage App AE account creation and lifecycle/activity foundation.**
2. **Immediate contract-accepted handoff automation.**
3. **Admin Console invite password setup.**
4. **End-to-end hardening, tests, and rollout.**

MVP intentionally avoids:

- DocuSign API integration.
- Embedded DocuSign in Admin Console.
- DocuSign webhook/callback completion reconciliation.
- Full contract validation against DocuSign templates. AEs own contract
  creation and signature verification manually for now.
- Full RBAC/location access modeling.
- Rich Manage App sync dashboards and retry consoles.
- Postmark reminder reactivation.
- Slackbot commands.
- Bidirectional Notion/Folk stage sync beyond the required handoff fields.

### Post-MVP: great-to-have improvements

Post-MVP work should make the system more observable, flexible, and scalable
after the core flow is reliable.

- Investigate whether DocuSign API/webhook integration should replace manual AE
  monitoring.
- Add embedded or linked DocuSign signing if PAL later owns legal signing
  in-app.
- Investigate whether Postmark invite reminders should be restored or replaced.
- Remove any remaining temporary-password dependency if MVP has to reuse an
  existing password reset path.
- Add Manage App visibility for sync status, partial failures, and safe retry
  actions.
- Add Slackbot status commands such as `status <account>`, `pending-invites`,
  and `sync-errors`.
- Add richer bidirectional Notion/Folk stage sync.
- Add full RBAC and location/franchisee-aware contract coverage.
- Add additional customer-user invite flows after the legal signer completes
  onboarding.
- Add automated DocuSign contract validation once templates and envelope
  patterns are stable.
- Track dashboard first access as an analytics signal.
- Build deeper admin repair tooling for re-linking Slack, Notion, Folk, and
  DocuSign artifacts.

## Architecture Shape

Use the database as the canonical onboarding lifecycle coordinator. Manage App,
Admin Console, Folk, Slack, and Notion should write to or read from that
lifecycle through APIs and small idempotent background jobs. DocuSign is an
external manual system in MVP; PAL stores DocuSign identifiers as references.

Core concepts:

- **Onboarding lifecycle:** one row per client onboarding flow.
- **Onboarding activity:** append-only lifecycle activity for audit and fanout.
  Use "activity" rather than "events" in the model and docs.
- **Integration mapping:** IDs for account, invite, DocuSign envelope/contract,
  Folk records, Slack channel, Notion page, and any source order form/scoping
  artifacts.
- **Sync jobs:** retryable jobs for account-owner assignment, handoff artifact
  creation, and external updates.

## Lifecycle State

Initial MVP statuses:

- `contract_prepared`
- `account_created`
- `docusign_signed`
- `invite_sent`
- `invite_opened`
- `password_set`
- `handoff_created`
- `activation_ready`
- `blocked`
- `cancelled`

`docusign_signed` means "AE has manually verified the signed DocuSign contract
and submitted the Manage App account creation form." It is not written by a
DocuSign webhook in MVP.

Each activity entry should store:

- Onboarding lifecycle ID.
- Previous status and next status, when the activity is a transition.
- Actor type: client, AE, FDE, system.
- Actor ID or external actor reference.
- Timestamp.
- Source system.
- Relevant payload diff.

## Phase 1: Manage App AE Account Creation and Lifecycle Foundation

Build the MVP account creation entry point in Manage App for AEs.

Flow:

1. AE creates the contract/order form package in DocuSign manually.
2. AE waits for customer signature and manually verifies signature in DocuSign.
3. AE opens Manage App and clicks create account.
4. AE enters or confirms:
   - Account name.
   - Client company name.
   - Signer name and email.
   - Contract type: SMB or Enterprise.
   - DocuSign contract/envelope ID or link.
   - FDE owner.
   - Existing Folk company ID, if available.
   - Scoping document link, if already known.
5. AE submits.
6. Backend creates or links the account without creating project/agent records.
7. Backend attaches the logged-in AE as account owner without invite acceptance.
8. Backend attaches the selected FDE as account owner without invite acceptance.
9. Backend creates the onboarding lifecycle and activity rows.
10. Backend records contract acceptance details because submit means AE has
    verified signature.
11. Backend creates and sends the client signer invite.

Backend responsibilities:

- Require the minimum fields needed to create the account and invite signer.
- Keep DocuSign fields as record metadata; do not call DocuSign in MVP.
- Do not validate contract contents against DocuSign templates in MVP; the AE
  owns contract preparation and signature verification manually.
- Prevent duplicate active lifecycles for the same account, signer, or
  DocuSign contract.
- Emit activity for `account_created`, manual `docusign_signed`, and
  `invite_sent`.
- Store the FDE owner for account ownership and handoff messaging.
- Keep the Folk company reference optional; onboarding updates Folk when linked
  but does not create sales-pipeline companies.
- Keep project/agent creation out of this flow.

Data model notes:

- Recommended lifecycle model: `client_onboarding_lifecycles`.
- Recommended activity model: `client_onboarding_activity`.
- Recommended sync model: `client_onboarding_sync_jobs`.
- Store:
  - `account_id`
  - `manage_app_account_name`
  - `client_company_name`
  - `signer_name`
  - `signer_email`
  - `contract_type`
  - `docusign_contract_id`
  - `docusign_envelope_id`
  - `docusign_contract_url`
  - `invite_id`
  - `ae_owner_user_id`
  - `fde_owner_user_id`
  - `folk_company_id`
  - `folk_contact_id`
  - `slack_channel_id`
  - `notion_page_id`
  - `scoping_doc_url`
  - `status`
  - `status_reason`
  - timestamps for account created, DocuSign signed/manual verified, invite
    sent, invite opened, password set, handoff created, activation ready

Future-proofing guardrail:

- Do not bake in the assumption that the signer always represents the entire
  account. The MVP can treat the signer as account-level, but names and model
  shape should leave room for future corporate/franchisee/location scopes.

Acceptance criteria:

- AE can create an account and send a signer invite from Manage App after
  manually verifying DocuSign signature.
- The logged-in AE becomes owner without accepting an invite.
- The selected FDE becomes owner without accepting an invite.
- No project or agent is automatically created.
- Lifecycle and activity records are durable before invite send side effects.
- DocuSign references are stored for recordkeeping.

## Phase 2: Immediate Handoff Automation

Create internal handoff artifacts from the Manage App account creation flow.
This phase is the MVP automation boundary.

Trigger:

- Primary trigger: successful Manage App client account creation after AE has
  manually verified DocuSign signature.
- `password_set` does not trigger Slack, Notion, Folk, or owner handoff fanout.
  It only updates client activation readiness after the already-started handoff
  pass has completed.

Database and Folk:

- Save contract acceptance date/time/person to the database.
- Save DocuSign contract/envelope ID or link to the linked Folk company when
  present.
- Save Manage App account ID/name to the linked Folk company when present.
- Save signer, AE owner, FDE owner, and contract type where supported.

Slack:

- Create the dedicated Slack channel after account creation.
- Use a normalized account/client channel name.
- Add or ping the AE and FDE.
- Post a contract acceptance handoff message.
- Include links to Manage App, DocuSign, Folk, and Notion when available.

Notion:

- Create the Notion Client Master Database entry after account creation.
- Populate from Folk and lifecycle data:
  - DocuSign/order form link.
  - Scoping document link.
  - Main owner.
  - Tier/segment.
  - Product.
  - Vendors.
  - Folk ID.
  - Manage App account ID/name.
  - Stage.
  - Meeting record link.
  - Slack channel.

Manage App:

- Add the logged-in AE to the account as owner during account creation.
- Add the selected FDE to the account as owner during account creation or the
  immediate handoff job.
- Mark handoff artifact creation with `handoff_created`.

Acceptance criteria:

- Slack, Notion, Folk, database, and Manage App are updated from the Manage App
  account creation point.
- Retrying the automation updates existing artifacts instead of creating
  duplicates.
- FDE and AE receive the Slack handoff message.
- Folk contains the DocuSign contract ID/link and Manage App account name/ID.
- Notion CMD entry is created after AE submits the account creation form.

## Phase 3: Admin Console Invite Password Setup

Keep the client account invite focused on password setup.

Flow:

1. Client clicks the invite email.
2. Admin Console validates invite token.
3. Client sets a password through the existing invite/password setup path.
4. Lifecycle moves to `password_set`.
5. Client is redirected to the Admin Console dashboard.

Password strategy:

- Target UX: the invite token takes the signer directly to password setup
  without asking the client to manually type a temporary password.
- If removing the temporary password dependency is too large for MVP, use the
  smallest existing password-reset/setup path.

Security and consistency:

- Gate active user/account access on password completion.
- Do not gate handoff automation on dashboard access.
- Expired or revoked invite tokens should show a recoverable error state and
  notify internal owners where appropriate.

Acceptance criteria:

- Invite opens to password setup.
- No DocuSign step is shown in Admin Console for MVP.
- The client is redirected to the dashboard after password setup.
- Dashboard access is not required for Slack/Notion/Folk handoff automation.

## Phase 4: End-to-End Hardening, Tests, and Rollout

Make the MVP safe enough to pilot.

Hardening:

- Add idempotency around account creation, invite send, Slack channel creation,
  Folk update, Notion creation, and owner adds.
- Keep any sync failure visible in logs and activity, even if full Manage App
  retry UI is post-MVP.
- Ensure normal team invites still work after Admin Console invite
  simplification.
- Ensure Manage App copy makes it clear that account creation means AE has
  manually verified DocuSign signature.

Rollout:

1. Ship behind an internal feature flag for test accounts if needed.
2. Pilot with one AE and one FDE.
3. Monitor duplicate creation, invite/password setup, and handoff artifact
   creation.
4. Expand to more AE-led onboardings after success criteria are met.

Acceptance criteria:

- One AE can complete the full flow for a real pilot client.
- Account creation, invite send, password setup, and handoff automation work in
  order.
- Slack, Notion, Folk, database, and Manage App handoff artifacts appear after
  Manage App submit.
- Duplicate/retry paths do not create duplicate accounts, channels, pages, or
  CRM entries.

## Post-MVP Phase A: Visibility, Reminders, and Repair

These are useful but not required for the first working onboarding path.

- Investigate whether Postmark invite reminders should be restored or replaced.
- Add Manage App sync status for Slack, Notion, Folk, Admin Console, and
  database projections.
- Add safe retry actions for failed sync jobs.
- Add Slackbot visibility commands:
  - `status <account>`
  - `pending-invites`
  - `sync-errors`
- Add dashboard first-access tracking as analytics.
- Add admin tools to resend invite, revoke invite, re-link external artifacts,
  and mark lifecycle blocked/cancelled with a reason.

## Post-MVP Phase B: Contract Coverage, DocuSign Automation, RBAC, and Additional Users

Post-MVP expands contract coverage, signing automation, and access control
beyond the MVP account-level signer model.

- Add DocuSign webhook/callback reconciliation if manual AE verification is no
  longer sufficient.
- Add embedded DocuSign signing only if product chooses to own legal signing in
  Admin Console.
- Add contract coverage scope:
  - Entire corporate account.
  - Multiple franchisee locations.
  - Single franchisee location.
  - Specific location set.
- Add per-location ToS and legal coverage where required.
- Add MSA-level `covers_franchisees` logic.
- Add additional customer-user invite workflows after the legal signer
  completes onboarding.
- Add role and location access controls for customer users.
- Add automated contract validation once DocuSign templates and contract
  package conventions stabilize.

## Sync Map

| State or value | Canonical writer | MVP fanout |
| -------------- | ---------------- | ---------- |
| Contract signed/manual verified | Manage App/API, from AE submit | Database lifecycle, activity, Folk |
| Account created | Manage App/API | Database lifecycle, activity |
| AE/FDE owners added | Manage App/API or immediate sync job | Manage App account membership/roles |
| Invite sent | Manage App/API | Admin Console invite, activity |
| Invite opened | Admin Console | Database activity |
| Password set | Admin Console/Auth | Database, Manage App user/account state |
| Handoff created | Immediate handoff automation | Slack, Notion, Folk, Manage App |
| Dashboard first accessed | Admin Console | Analytics only |

## Test Plan

Unit tests:

- Lifecycle transition validation.
- Activity write behavior.
- Idempotency key behavior.
- Password setup marker.
- Immediate handoff automation trigger rules.

Integration tests:

- Manage App AE account creation creates account, lifecycle, activity, AE owner,
  FDE owner, contract-signed metadata, and invite.
- Invite opens password setup without DocuSign UI.
- Password setup activates the user and redirects to dashboard.
- Immediate handoff automation creates/updates Slack, Notion, Folk, DB, and
  owner state.
- Retry of handoff automation does not duplicate external artifacts.

End-to-end tests:

- Happy path from AE manual DocuSign verification through Manage App account
  creation, invite, password setup, and handoff artifact creation.
- Duplicate submission/retry path.
- Normal non-onboarding team invite path.

## Completion Criteria

- AE can create an account and send a signer invite from Manage App after
  manually verifying DocuSign signature.
- AE is account owner without manually accepting an invite.
- FDE is account owner without manually accepting an invite.
- No project or agent is automatically created.
- Client invite opens to password setup, not DocuSign.
- Client sets password and reaches the Admin Console dashboard.
- Contract signature metadata saves to database and Folk.
- Slack channel and Notion CMD entry are created after Manage App submit.
- MVP values sync across Slack, Notion, Folk, Manage App, Admin Console, and the
  database.
