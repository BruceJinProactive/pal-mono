# Contract-to-Account Onboarding - PRD

|                   |       |
| ----------------- | ----- |
| **Status**        | Draft |
| **Approver**      |       |
| **Approval Date** |       |

## Summary

This PRD covers the pre-go-live onboarding path after an AE has manually
confirmed a signed DocuSign contract/order form package. The system-owned flow
starts when the AE creates the client account in Manage App.

The corrected MVP flow is:

1. AE manually creates the DocuSign contract/order form package:
   - SMB: order form + ToS.
   - Enterprise: order form + MSA.
2. AE manually monitors DocuSign and verifies that the customer has signed.
   There is no MVP DocuSign API integration, embedded signing, webhook, or
   callback dependency.
3. After signature verification, AE creates the client account in Manage App.
   The form captures signer name/email and DocuSign reference fields for
   recordkeeping.
4. Manage App submit creates or links the account, sends the client invite, and
   starts internal handoff automation.
5. The logged-in AE and selected FDE are added as account owners without
   manually accepting invites.
6. The system saves contract acceptance details, updates Folk, creates the
   dedicated Slack channel, creates the Notion Client Master Database entry, and
   pings the AE/FDE.
7. Client opens the account invite in Admin Console, sets a password, and is
   redirected to the Admin Console dashboard.

DocuSign remains the legal signing system, but in MVP it is upstream of the
system flow. PAL stores DocuSign identifiers and links as references only.

## Problem

Today's pre-go-live onboarding is fragile and manual. AEs, FDEs, and ops must
touch Manage App, Admin Console, DocuSign, Folk, Notion, and Slack to bring on a
single client, and each tool can drift from the others:

- Signed contract context is not reliably connected to Manage App account
  creation.
- AE and FDE account ownership requires manual invite acceptance or follow-up.
- Slack channels, Notion records, and Folk fields are created manually or at
  inconsistent lifecycle points.
- Contract signature details are not consistently saved to Folk and the
  database.
- Client account invite/password setup is mixed with legal-signature concerns
  even though AEs already verify DocuSign manually before account creation.

Deals that should move smoothly from signed contract to onboarding handoff drag
on because every system has to be checked and reconciled manually.

## Goals

- Let an AE create the client account and send the signer invite from Manage
  App after manually verifying DocuSign signature.
- Attach the logged-in AE as account owner without invite acceptance.
- Attach the selected FDE as account owner without invite acceptance.
- Save contract acceptance date/time/person and DocuSign reference metadata to
  the database and Folk.
- Create Slack and Notion handoff artifacts immediately after Manage App
  account creation.
- Keep client Admin Console onboarding focused on password setup and dashboard
  access.
- Avoid blocking internal handoff automation on dashboard access.
- Keep the MVP data model open for future corporate/franchisee/location RBAC.

## Personas

| Persona | Needs |
| ------- | ----- |
| AE | Prepare and verify the DocuSign contract manually, create the account in Manage App, send the signer invite, and become account owner automatically. |
| Client signer | Open the account invite, set a password, and reach the Admin Console dashboard without extra legal-signing steps. |
| FDE | Receive account ownership and a Slack/Notion/Folk handoff when the AE creates the account after signature. |
| Sales/ops leadership | See which clients have accounts created, invites sent, handoffs completed, password setup completed, blocked work, or activation readiness. |
| Additional customer user | Join an already-created account through normal invitation/password setup flows. |

## Success Metrics

| Metric | Target |
| ------ | ------ |
| AE account creation to invite sent | < 5 minutes |
| Manage App submit to Slack/Notion/Folk handoff artifacts | < 2 minutes p95 |
| Invite opened to password setup completion | > 90% within same session |
| Manual engineering/support intervention on account creation or handoff sync | < 10% |
| Duplicate/wrong-account onboarding incidents | 0 after cleanup |

## Product Principles

1. **DocuSign is manual before PAL MVP starts.** AE creates and verifies the
   contract in DocuSign before opening the Manage App account creation form.
2. **Manage App account creation is the system kickoff.** Submit creates or
   links the account, sends the invite, records contract acceptance, and starts
   handoff automation.
3. **DocuSign fields are references, not workflow drivers.** Envelope ID,
   contract ID, and contract URL support recordkeeping and downstream context.
4. **Internal owners do not accept customer invites.** The logged-in AE and
   selected FDE become account owners as part of onboarding automation.
5. **Client invite means password setup.** Admin Console should not show an
   embedded DocuSign step in MVP.
6. **Dashboard access is telemetry.** Dashboard first access can be tracked, but
   it must not block Slack, Notion, Folk, or owner handoff automation.
7. **Activity is observable.** Users should see who created the account, who was
   invited, what contract references were recorded, which handoff syncs ran,
   and what is blocked.
8. **Future RBAC should not be boxed out.** MVP can treat the signer as
   account-level, but model names and ownership assumptions should leave room
   for corporate, franchisee, and location-scoped signing later.

## Scope

### MVP: Manual DocuSign signoff, Manage App kickoff, and immediate handoff

MVP supports:

- AE-created and AE-verified DocuSign contract/order form package.
- AE-created Manage App account.
- Account creation without automatically creating a project or agent.
- DocuSign envelope/contract/link fields saved as metadata.
- Client signer invite sent automatically from Manage App submit.
- Logged-in AE auto-ownership without invite acceptance.
- Selected FDE auto-ownership without invite acceptance.
- Contract acceptance recording at account creation time:
  - signer name/email
  - AE owner
  - FDE owner
  - contract type
  - DocuSign envelope/contract/link
  - acceptance timestamp based on Manage App submission time
- Immediate handoff automation:
  - Save contract acceptance details to database and Folk.
  - Save Manage App account ID/name to Folk.
  - Create dedicated Slack channel.
  - Ping AE and FDE with the handoff message.
  - Create Notion Client Master Database entry.
- Admin Console invite route for client password setup and dashboard redirect.
- Activity tracking for lifecycle transitions and sync outcomes.

MVP avoids:

- DocuSign API integration.
- Embedded DocuSign in Admin Console.
- DocuSign webhooks/callbacks/completion reconciliation.
- Automated validation of DocuSign contract contents/templates.
- Full Manage App sync dashboard/retry UI.
- Postmark invite-reminder changes.
- Full RBAC/location/franchisee legal coverage.
- Slackbot commands.
- Bidirectional Notion/Folk stage sync beyond required handoff fields.

### Post-MVP: visibility, reminders, DocuSign automation, RBAC, and richer sync

Post-MVP adds:

- DocuSign API/webhook integration if manual AE monitoring becomes a bottleneck.
- Embedded or linked DocuSign signing experiences if product decides to own
  legal signing in-app.
- Postmark invite-reminder investigation or replacement.
- Full Manage App visibility for sync state and retry actions.
- Slackbot status commands.
- Additional customer-user invite flows.
- Per-location ToS and legal coverage.
- MSA-level `covers_franchisees` logic.
- Corporate/franchisee/location-scoped signing.
- Richer bidirectional Notion/Folk stage sync.
- Automated contract validation once DocuSign templates stabilize.
- Dashboard first-access analytics.

## Requirements

### Manual DocuSign signoff

- AE manually creates the DocuSign contract/order form package before creating
  the account.
- AE manually verifies that the customer signed before submitting the Manage App
  client account creation form.
- MVP stores DocuSign contract/envelope ID or link, but does not validate
  contract contents, template correctness, or live DocuSign status.
- At least one DocuSign reference is required for every MVP onboarding:
  envelope ID, contract ID, or contract URL.

### Manage App account creation

- AE can create a client account from Manage App.
- AE provides account name, client company name, signer name/email, contract
  type, DocuSign contract/envelope reference, FDE owner, and optional existing
  Folk company or scoping doc references.
- Account is created without automatically creating a project or agent.
- Logged-in AE is associated as account owner without receiving or accepting a
  customer invite.
- Selected FDE is associated as account owner without receiving or accepting a
  customer invite.
- Signer invite email is sent to the client automatically.
- Database lifecycle/activity state records account creation, contract signed
  metadata, invite send, handoff syncs, password setup, and activation readiness.

### Client invite onboarding

- Client opens the email invite and lands in Admin Console.
- Client sets a password through the account invite flow.
- Client is redirected to the Admin Console dashboard after password setup.
- Admin Console does not render embedded DocuSign in MVP.
- Dashboard access may be recorded as analytics, not as a blocking lifecycle
  dependency.

### Handoff automation

After AE submits the Manage App form:

- Save contract acceptance date/time/person to the database.
- Update the existing Folk company with DocuSign contract ID/link and Manage
  App account ID/name when a Folk company is linked. MVP onboarding does not
  create Folk companies; missing Folk links skip the Folk update.
- Create the dedicated Slack channel.
- Add or ping AE and FDE in Slack.
- Post the contract acceptance handoff message.
- Create the Notion Client Master Database entry.
- Populate Notion from Folk/lifecycle values:
  - DocuSign/order form link.
  - Scoping doc link.
  - Main owner.
  - Tier/segment.
  - Product.
  - Vendors.
  - Folk ID.
  - Manage App account ID/name.
  - Stage.
  - Meeting record link.
  - Slack channel.
- Add the logged-in AE and selected FDE as account owners in Manage App.

### Sync and status consistency

- The PAL database stores canonical onboarding status, activity, timestamps,
  actors, and integration IDs.
- Sync operations are idempotent and retryable.
- Slack, Notion, Folk, Manage App, Admin Console, and the database should not
  show conflicting terminal states.
- Sync failure should be visible in logs/activity in MVP; richer Manage App
  retry controls are post-MVP.

### Additional customer users

After the legal signer completes password setup, AE/FDE users can add
additional customer users:

- User clicks invite link.
- User lands on a focused Admin Console page to set a password.
- Additional users do not see any DocuSign step in MVP.

## Data and State Model Implications

- Account creation must not imply project or agent creation.
- Use an onboarding lifecycle model for canonical status and integration IDs.
- Use onboarding activity, not onboarding events, for append-only audit/fanout.
- Contract state must include DocuSign contract/envelope ID, signer name, signer
  email, signed timestamp, signed-by actor, and manual-source metadata.
- Invite state must include invite sent timestamp, opened timestamp, password
  set timestamp, expiry/revocation state, and optional dashboard first-access
  timestamp.
- Folk, Notion, Slack, and DocuSign identifiers should be idempotency keys where
  possible.
- MVP should not hard-code the signer as permanently whole-account-only. Leave
  room for future corporate/franchisee/location scope.

## Risks and Mitigations

| Risk | Mitigation |
| ---- | ---------- |
| AE creates an account before the contract is truly signed | Make the form/copy explicit that submission means AE has verified signature; add later DocuSign integration if this becomes risky. |
| Manual DocuSign status drifts from PAL records | Store references and signer metadata; keep audit activity showing AE as the verifier. |
| External sync creates duplicates | Use account, DocuSign, Folk, Notion, and Slack IDs as idempotency keys. |
| Contract validation is manual in MVP | Make AE ownership explicit and defer automated validation until templates stabilize. |
| Future RBAC/location needs are boxed out | Keep model names and signer scope open for corporate/franchisee/location coverage. |
| Dashboard access is mistaken as a handoff dependency | Keep dashboard first access as analytics only. |

## Fixed Decisions

- MVP account creation entry point is Manage App.
- AE verifies DocuSign signature manually before creating the account.
- There is no MVP DocuSign API, embedded signing, webhook, or callback
  integration.
- AE creates the account and sends the client invite through one Manage App
  submit.
- Logged-in AE becomes account owner without invite acceptance.
- Selected FDE becomes account owner without invite acceptance.
- Client invite opens Admin Console for password setup only.
- Slack, Notion, Folk, and owner handoff happen after Manage App submit because
  submit means AE has verified contract signature.
- Dashboard access is not a dependency for handoff automation.
- Activity terminology replaces event terminology in the plan.

## Out of Scope

- Billing logic, invoicing cadence, payment terms, and credit-card vs invoice
  flows.
- Full RBAC/privacy redesign beyond MVP future-proofing.
- Folk integration with WeChat or SMS.
- Postmark reminder changes in MVP.
- Full automated DocuSign contract validation in MVP.
- Embedded DocuSign or DocuSign webhook reconciliation in MVP.

## Referenced Artifacts

The source draft referenced supporting artifacts that are not stored in this
repository yet:

- MSA vs ToS franchisor/franchisee structure diagram from 2026-05-18.
- Proposed solution walkthrough screen recording from 2026-05-19.
- Backend walkthrough recording.
- Create Account modal screenshots.
- Subscription clarification screenshot from 2026-06-08.
