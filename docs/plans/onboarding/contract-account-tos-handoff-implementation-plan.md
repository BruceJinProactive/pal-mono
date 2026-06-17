# Contract-to-Account Onboarding Implementation Plan

|                  |                                                             |
| ---------------- | ----------------------------------------------------------- |
| **Status**       | Draft                                                       |
| **PRD**          | `docs/plans/onboarding/contract-account-tos-handoff-prd.md` |
| **Last Updated** | 2026-06-17                                                  |

## Implementation Assumption

MVP flow:

1. AE manually creates the DocuSign contract/order form package:
   - SMB: order form + ToS.
   - Enterprise: order form + MSA.
2. AE creates the account in Manage App and sends an invite to the client's
   email.
3. The logged-in AE is attached to the account as owner and should not manually
   accept an invite.
4. Client opens the invite and sees DocuSign first in Admin Console.
5. Client signs DocuSign, then sets a password.
6. After password setup, the client is redirected to the Admin Console
   dashboard.
7. After contract signature, the system saves contract acceptance details,
   updates Folk, creates the dedicated Slack channel, creates the Notion Client
   Master Database entry, adds the FDE as owner, and pings the AE/FDE.

The important dependency is contract signed, followed by password set where
client account activation needs it.

## MVP vs Post-MVP

### MVP: end-to-end working onboarding flow

MVP should prove the new onboarding path works from AE action through client
signature/password setup and internal handoff.

MVP phases:

1. **Manage App AE account creation and lifecycle/activity foundation.**
2. **DocuSign-first Admin Console invite and password setup.**
3. **DocuSign completion handling plus post-signature handoff automation.**
4. **End-to-end hardening, tests, and rollout.**

MVP intentionally avoids:

- Full contract validation against DocuSign templates. AEs own contract creation
  manually for now.
- Full RBAC/location access modeling.
- Rich Manage App sync dashboards and retry consoles.
- Postmark reminder reactivation.
- Slackbot commands.
- Bidirectional Notion/Folk stage sync beyond the required handoff fields.

### Post-MVP: great-to-have improvements

Post-MVP work should make the system more observable, flexible, and scalable
after the core flow is reliable.

- Investigate whether Postmark invite reminders should be restored or replaced.
- Remove any remaining temporary-password dependency if MVP has to reuse an
  existing password reset path.
- Add Manage App visibility for sync status, partial failures, and safe retry
  actions.
- Add Slackbot status commands such as `status <account>`,
  `pending-docusign`, and `sync-errors`.
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
Admin Console, DocuSign, Folk, Slack, and Notion should write to or read from
that lifecycle through APIs, webhooks, and small idempotent background jobs.

Core concepts:

- **Onboarding lifecycle:** one row per client onboarding flow.
- **Onboarding activity:** append-only lifecycle activity for audit and fanout.
  Use "activity" rather than "events" in the model and docs.
- **Integration mapping:** IDs for account, invite, DocuSign envelope/contract,
  Folk records, Slack channel, Notion page, and any source order form/scoping
  artifacts.
- **Sync jobs:** retryable jobs for post-signature artifact creation and
  external updates.

## Lifecycle State

Initial MVP statuses:

- `contract_prepared`
- `account_created`
- `invite_sent`
- `invite_opened`
- `docusign_viewed`
- `docusign_signed`
- `password_set`
- `handoff_created`
- `activation_ready`
- `blocked`
- `cancelled`

Each activity entry should store:

- Onboarding lifecycle ID.
- Previous status and next status, when the activity is a transition.
- Actor type: client, AE, FDE, system, webhook.
- Actor ID or external actor reference.
- Timestamp.
- Source system.
- Relevant payload diff.

## Phase 1: Manage App AE Account Creation and Lifecycle Foundation

Build the MVP account creation entry point in Manage App for AEs.

Flow:

1. AE creates the contract/order form package in DocuSign manually.
2. AE opens Manage App and clicks create account.
3. AE enters or confirms:
   - Account name.
   - Client company name.
   - Signer name and email.
   - Contract type: SMB or Enterprise.
   - DocuSign contract/envelope ID or link.
   - FDE owner.
   - Folk ID, if already known.
   - Scoping document link, if already known.
4. AE submits.
5. Backend creates or links the account without creating project/agent records.
6. Backend attaches the logged-in AE as account owner without invite
   acceptance.
7. Backend creates the onboarding lifecycle and activity rows.
8. Backend creates and sends the client signer invite.

Backend responsibilities:

- Require the minimum fields needed to create the account and invite signer.
- Do not validate contract contents against DocuSign templates in MVP; the AE
  owns contract preparation manually.
- Prevent duplicate active lifecycles for the same account, signer, or DocuSign
  contract where practical.
- Emit `account_created` and `invite_sent` activity.
- Store the FDE owner for later post-signature ownership assignment.
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
  - timestamps for account created, invite sent, invite opened, DocuSign
    viewed, DocuSign signed, password set, handoff created, activation ready

Future-proofing guardrail:

- Do not bake in the assumption that the signer always represents the entire
  account. The MVP can treat the signer as account-level, but names and model
  shape should leave room for future corporate/franchisee/location scopes.

Acceptance criteria:

- AE can create an account and send a signer invite from Manage App.
- The logged-in AE becomes owner without accepting an invite.
- No project or agent is automatically created.
- Lifecycle and activity records are durable before invite send side effects.
- FDE owner is stored for post-signature account ownership.

## Phase 2: DocuSign-First Admin Console Invite and Password Setup

Replace the legal signer invite path with a DocuSign-first Admin Console flow.

Flow:

1. Client clicks the invite email.
2. Admin Console validates invite token and lifecycle state.
3. Lifecycle moves to `invite_opened`.
4. If DocuSign is already complete, Admin Console skips signing and moves to
   password setup.
5. Otherwise, Admin Console renders embedded DocuSign as the first required
   action.
6. Lifecycle moves to `docusign_viewed` only after the signer-visible DocuSign
   embed successfully loads. Creating an embedded signing session or URL alone
   must not advance this state.
7. DocuSign completion webhook or verified return callback moves lifecycle to
   `docusign_signed`.
8. Password setup becomes available.
9. Client sets password.
10. Lifecycle moves to `password_set`.
11. Client is redirected to the Admin Console dashboard.

Password strategy:

- Target UX: the invite token takes the signer directly to DocuSign-first
  onboarding and then password setup, without asking for a temporary password.
- If removing the temporary password dependency is too large for MVP, use the
  smallest existing password-reset/setup path that preserves the order:
  DocuSign first, then password.

Security and consistency:

- Do not trust only the browser return from DocuSign. Confirm envelope
  completion through DocuSign state or webhook reconciliation.
- Gate password setup on canonical `docusign_signed`.
- Gate active user/account access on password completion.
- Do not gate post-signature handoff automation on dashboard access.
- Expired or revoked invite tokens should show a recoverable error state and
  notify internal owners where appropriate.

Fallback:

- If embedded DocuSign cannot be loaded, show an explicit message:
  "Please check your email for a contract from [AE name] via DocuSign."
- Continue syncing status from DocuSign webhooks.
- If the signer signs directly in DocuSign before returning to Admin Console,
  the webhook/reconciliation path should advance the lifecycle to
  `docusign_signed`.
- Do not unlock password setup until signing is confirmed.

Acceptance criteria:

- Invite opens to DocuSign-first onboarding.
- A signer who already signed via DocuSign email can continue to password setup.
- Password setup is inaccessible before confirmed signature.
- The client is redirected to the dashboard after password setup.
- Dashboard access is not required for Slack/Notion/Folk handoff automation.

## Phase 3: DocuSign Completion and Post-Signature Handoff Automation

Create the internal handoff artifacts only after the contract is confirmed
signed. This phase is the MVP automation boundary.

Trigger:

- Primary trigger: lifecycle reaches `docusign_signed`.
- Secondary trigger: lifecycle reaches `password_set` for user activation state.

Database and Folk:

- Save contract acceptance date/time/person to the database.
- Save DocuSign contract/envelope ID or link to Folk.
- Save Manage App account ID/name to Folk.
- Save signer, AE owner, FDE owner, and contract type where supported.

Slack:

- Create the dedicated Slack channel after contract signature is confirmed.
- Use a normalized account/client channel name.
- Add or ping the AE and FDE.
- Post a contract acceptance message.
- Include links to Manage App, DocuSign, Folk, and Notion when available.

Notion:

- Create the Notion Client Master Database entry after contract signature is
  confirmed.
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

- Add the selected FDE to the account as owner after contract signature.
- Keep the AE as owner.
- Mark handoff artifact creation with `handoff_created`.

Acceptance criteria:

- Slack, Notion, Folk, database, and Manage App are updated from the
  post-signature lifecycle point.
- Retrying the automation updates existing artifacts instead of creating
  duplicates.
- FDE and AE receive the Slack handoff message.
- Folk contains the DocuSign contract ID/link and Manage App account name/ID.
- Notion CMD entry is created only after contract signature.

## Phase 4: End-to-End Hardening, Tests, and Rollout

Make the MVP safe enough to pilot.

Hardening:

- Add idempotency around account creation, invite send, DocuSign completion,
  Slack channel creation, Folk update, Notion creation, and FDE owner add.
- Reconcile DocuSign webhooks by envelope/contract ID and signer email.
- Handle duplicate webhook deliveries.
- Handle signer flows that start in DocuSign email and later return to Admin
  Console.
- Keep any sync failure visible in logs and activity, even if full Manage App
  retry UI is post-MVP.

Rollout:

1. Ship behind an internal feature flag for test accounts.
2. Run sandbox DocuSign end-to-end tests.
3. Pilot with one AE and one FDE.
4. Monitor duplicate creation, signature completion, password setup, and
   handoff artifact creation.
5. Expand to more AE-led onboardings after success criteria are met.

Acceptance criteria:

- One AE can complete the full flow for a real pilot client.
- Contract signature and password setup work in order.
- Slack, Notion, Folk, database, and Manage App handoff artifacts appear after
  signature.
- Duplicate/retry paths do not create duplicate accounts, channels, pages, or
  CRM entries.

## Post-MVP Phase A: Visibility, Reminders, and Repair

These are useful but not required for the first working onboarding path.

- Investigate whether Postmark invite reminders should be restored or replaced.
- Add Manage App sync status for Slack, Notion, Folk, DocuSign, Admin Console,
  and database projections.
- Add safe retry actions for failed sync jobs.
- Add Slackbot visibility commands:
  - `status <account>`
  - `pending-docusign`
  - `pending-invites`
  - `sync-errors`
- Add dashboard first-access tracking as analytics.
- Add admin tools to resend invite, revoke invite, re-link external artifacts,
  and mark lifecycle blocked/cancelled with a reason.

## Post-MVP Phase B: Contract Coverage, RBAC, and Additional Users

Post-MVP expands contract coverage and access control beyond the MVP account-level signer model.

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
| Account created | Manage App/API | Database lifecycle, activity |
| Invite sent | Manage App/API | Admin Console invite, activity |
| Invite opened | Admin Console | Database activity |
| DocuSign viewed | Admin Console visible embed load | Database activity |
| DocuSign signed | DocuSign webhook or verified callback | Database, Folk, Slack, Notion, Manage App |
| Password set | Admin Console/Auth | Database, Manage App user/account state |
| Handoff created | Post-signature automation | Slack, Notion, Folk, Manage App |
| Dashboard first accessed | Admin Console | Analytics only |

## Test Plan

Unit tests:

- Lifecycle transition validation.
- Activity write behavior.
- Idempotency key behavior.
- DocuSign webhook reconciliation.
- Password gate checks.
- Post-signature automation trigger rules.

Integration tests:

- Manage App AE account creation creates account, lifecycle, activity, owner,
  and invite.
- Invite opens DocuSign-first page.
- DocuSign completion unlocks password setup.
- Direct DocuSign-email signing advances lifecycle to `docusign_signed`.
- Password setup activates the user and redirects to dashboard.
- Post-signature automation creates/updates Slack, Notion, Folk, DB, and FDE
  owner state.
- Retry of handoff automation does not duplicate external artifacts.

End-to-end tests:

- Happy path from AE DocuSign contract creation reference through Manage App
  account creation, invite, embedded signing, password setup, and handoff
  artifact creation.
- Embedded DocuSign fallback path with email-signing reconciliation.
- Duplicate submission/retry path.

## Completion Criteria

- AE can create an account and send a signer invite from Manage App.
- AE is account owner without manually accepting an invite.
- No project or agent is automatically created.
- Client invite opens to DocuSign-first onboarding.
- Client signs, sets password, and reaches the Admin Console dashboard.
- Contract signature saves acceptance details to database and Folk.
- FDE is added as account owner after contract signature.
- Slack channel and Notion CMD entry are created only after contract signature.
- Post-signature values sync across Slack, Notion, Folk, Manage App, Admin
  Console, the database, and DocuSign.
