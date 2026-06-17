# Contract-to-Account Onboarding - PRD

|                   |       |
| ----------------- | ----- |
| **Status**        | Draft |
| **Approver**      |       |
| **Approval Date** |       |

## Summary

This PRD covers the pre-go-live onboarding path from an AE-prepared DocuSign
contract through Manage App account creation, client invite, DocuSign-first
Admin Console onboarding, password setup, and post-signature internal handoff.

The MVP target flow is:

1. AE manually creates the DocuSign contract/order form package:
   - SMB: order form + ToS.
   - Enterprise: order form + MSA.
2. AE creates the client account in Manage App and sends an invite to the
   client's email.
3. The logged-in AE becomes account owner without manually accepting an invite.
4. Client opens the invite and sees DocuSign first in Admin Console.
5. Client signs DocuSign, then sets a password.
6. Client is redirected to the Admin Console dashboard after password setup.
7. Contract acceptance date/time/person is saved to the database and Folk.
8. After contract signature, the system creates the dedicated Slack channel,
   creates the Notion Client Master Database entry, adds the FDE as owner, and
   pings AE/FDE with the contract acceptance handoff.

Dashboard access is useful telemetry, but it is not a dependency for the
post-signature handoff automations.

## Problem

Today's pre-go-live onboarding is fragile and manual. AEs, FDEs, and ops must
touch Manage App, Admin Console, DocuSign, Folk, Notion, and Slack to bring on a
single client, and each tool can drift from the others:

- Contract/order form context is not reliably connected to Manage App account
  creation.
- AE account ownership requires manual invite acceptance or follow-up.
- Customers can hit password setup or Admin Console flows before the required
  DocuSign step is complete.
- Slack channels, Notion records, and Folk fields are created manually or at
  the wrong lifecycle point.
- Contract signature details are not consistently saved to Folk and the
  database.
- FDE handoff is inconsistent because ownership, Slack, Notion, and CRM state
  are stitched together by hand.

Deals that should move smoothly from signed contract to onboarding handoff drag
on because every system has to be checked and reconciled manually.

## Goals

- Let an AE create the client account and send the signer invite from Manage
  App.
- Attach the logged-in AE as account owner without invite acceptance.
- Make the client invite DocuSign-first: embedded signing before password setup
  and dashboard access.
- Save contract acceptance date/time/person to the database and Folk.
- Create Slack, Notion, and FDE ownership after contract signature is confirmed.
- Avoid blocking handoff automation on dashboard access.
- Keep the MVP data model open for future corporate/franchisee/location RBAC.

## Personas

| Persona | Needs |
| ------- | ----- |
| AE | Create the DocuSign contract manually, create the account in Manage App, send the signer invite, and become account owner automatically. |
| Client signer | Open the invite, sign DocuSign first, set a password, and reach the Admin Console dashboard without extra navigation. |
| FDE | Receive ownership and a Slack/Notion/Folk handoff after contract signature. |
| Sales/ops leadership | See which clients are invited, unsigned, password-ready, handoff-created, blocked, or ready for activation. |
| Additional customer user | Join an already-created account after the legal signer completes onboarding. |

## Success Metrics

| Metric | Target |
| ------ | ------ |
| AE account creation to invite sent | < 5 minutes |
| Invite opened to DocuSign completion | > 80% within 48 hours |
| DocuSign completion to password setup completion | > 90% within same session |
| DocuSign completion to Slack/Notion/Folk handoff artifacts | < 2 minutes p95 |
| Manual engineering/support intervention on account creation or handoff sync | < 10% |
| Duplicate/wrong-account onboarding incidents | 0 after cleanup |

## Product Principles

1. **AE creates the account in Manage App.** Manage App is the MVP entry point
   for account creation and signer invite send.
2. **DocuSign comes first for the client.** The invite opens an Admin Console
   onboarding page where the embedded DocuSign document is the first required
   action.
3. **Password follows signature.** The client sets their password only after
   DocuSign completion is confirmed.
4. **Handoff artifacts follow signature.** Slack channel creation, Notion CMD
   creation, Folk updates, and FDE ownership happen after the contract is
   confirmed signed.
5. **Dashboard access is telemetry.** Dashboard first access can be tracked, but
   it must not block Slack, Notion, Folk, or FDE handoff automation.
6. **Activity is observable.** For every client, users should see who created
   the account, who was invited, who opened the invite, DocuSign status,
   password status, handoff status, and what is blocked.
7. **Future RBAC should not be boxed out.** MVP can treat the signer as
   account-level, but model names and ownership assumptions should leave room
   for corporate, franchisee, and location-scoped signing later.

## Scope

### MVP: AE-led account creation, DocuSign-first signup, and post-signature handoff

MVP supports:

- AE-created DocuSign contract/order form package.
- AE-created Manage App account.
- AE auto-ownership without invite acceptance.
- Account creation without automatically creating a project or agent.
- Client signer invite.
- Admin Console invite route that shows DocuSign before password setup.
- DocuSign completion reconciliation from embedded signing, callback, or
  webhook.
- Password setup after `docusign_signed`.
- Post-signature automation:
  - Save contract acceptance date/time/person to database and Folk.
  - Save DocuSign contract/envelope ID or link to Folk.
  - Save Manage App account ID/name to Folk.
  - Create dedicated Slack channel.
  - Ping AE and FDE with a contract acceptance message.
  - Create Notion Client Master Database entry.
  - Add FDE as account owner.
- Activity tracking for lifecycle transitions.

MVP avoids:

- Automated validation of DocuSign contract contents/templates.
- Full Manage App sync dashboard/retry UI.
- Postmark invite-reminder changes.
- Full RBAC/location/franchisee legal coverage.
- Slackbot commands.
- Bidirectional Notion/Folk stage sync beyond required handoff fields.

### Post-MVP: visibility, reminders, RBAC, and richer sync

Post-MVP adds:

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

### DocuSign contract preparation

- AE manually creates the DocuSign contract/order form package before creating
  the account.
- MVP stores DocuSign contract/envelope ID or link, but does not validate
  contract contents or template correctness.
- DocuSign completion must be reconciled by envelope/contract ID and signer
  email where available.

### Manage App account creation

- AE can create a client account from Manage App.
- AE provides account name, client company name, signer name/email, contract
  type, DocuSign contract/envelope reference, FDE owner, and optional Folk or
  scoping doc references.
- Account is created without automatically creating a project or agent.
- Logged-in AE is associated as account owner without receiving or accepting a
  customer invite.
- FDE owner is stored for post-signature ownership assignment.
- Signer invite email is sent to the client.
- Database lifecycle/activity state records account creation and invite send.

### Client invite onboarding

- Client opens the email invite and lands in Admin Console.
- The first required action is embedded DocuSign when the contract is not
  already signed.
- `docusign_viewed` is recorded only after the signer-visible embed loads.
- If the signer has already signed through DocuSign email, Admin Console should
  detect `docusign_signed` and continue to password setup.
- The client cannot set a password until DocuSign completion is confirmed.
- After password setup succeeds, the user account is activated and the client is
  redirected to the Admin Console dashboard.
- Dashboard access may be recorded as analytics, not as a blocking lifecycle
  dependency.

If embedded DocuSign cannot load, Admin Console should tell the signer to check
their email for a contract from the AE via DocuSign, and the webhook path should
still advance the lifecycle when signing completes.

### Post-signature handoff automation

After contract signature is confirmed:

- Save contract acceptance date/time/person to the database.
- Update Folk with DocuSign contract ID/link and Manage App account ID/name.
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
- Add the selected FDE as account owner in Manage App.

### Sync and status consistency

- The PAL database stores canonical onboarding status, activity, timestamps,
  actors, and integration IDs.
- Sync operations are idempotent and retryable.
- DocuSign webhooks reconcile into the canonical lifecycle before fanout.
- Slack, Notion, Folk, Manage App, Admin Console, database, and DocuSign should
  not show conflicting terminal states.
- Sync failure should be visible in logs/activity in MVP; richer Manage App
  retry controls are post-MVP.

### Additional customer users

After the legal signer completes onboarding, AE/FDE users can add additional
customer users:

- User clicks invite link.
- User lands on a focused Admin Console page to set a password.
- Additional users do not see the first-signature DocuSign step unless later
  location or contract rules require it.

## Data and State Model Implications

- Account creation must not imply project or agent creation.
- Use an onboarding lifecycle model for canonical status and integration IDs.
- Use onboarding activity, not onboarding events, for append-only audit/fanout.
- Contract state must include DocuSign contract/envelope ID, signer name, signer
  email, viewed status, signed status, signed timestamp, and source.
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
| Embedded DocuSign is not reliable because of iframe, CORS, or API limits | Ship explicit DocuSign-email fallback with the same webhook status tracking. |
| Client signs in DocuSign email before opening Admin Console | Reconcile webhooks and skip directly to password setup when already signed. |
| External sync creates duplicates | Use account, DocuSign, Folk, Notion, and Slack IDs as idempotency keys. |
| Contract validation is manual in MVP | Make AE ownership explicit and defer automated validation until templates stabilize. |
| Future RBAC/location needs are boxed out | Keep model names and signer scope open for corporate/franchisee/location coverage. |
| Dashboard access is mistaken as a handoff dependency | Keep dashboard first access as analytics only. |

## Fixed Decisions

- MVP account creation entry point is Manage App.
- AE creates the account and sends the client invite.
- Logged-in AE becomes account owner without invite acceptance.
- Client invite opens Admin Console to embedded DocuSign first.
- Password setup happens after DocuSign completion.
- Slack, Notion, Folk, and FDE ownership happen after contract signature, not at
  invite send.
- Dashboard access is not a dependency for handoff automation.
- Activity terminology replaces event terminology in the plan.

## Out of Scope

- Billing logic, invoicing cadence, payment terms, and credit-card vs invoice
  flows.
- Full RBAC/privacy redesign beyond MVP future-proofing.
- Folk integration with WeChat or SMS.
- Postmark reminder changes in MVP.
- Full automated DocuSign contract validation in MVP.

## Referenced Artifacts

The source draft referenced supporting artifacts that are not stored in this
repository yet:

- MSA vs ToS franchisor/franchisee structure diagram from 2026-05-18.
- Proposed solution walkthrough screen recording from 2026-05-19.
- Backend walkthrough recording.
- Create Account modal screenshots.
- Subscription clarification screenshot from 2026-06-08.
