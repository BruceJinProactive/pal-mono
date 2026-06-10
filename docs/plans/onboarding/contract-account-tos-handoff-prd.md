# Contract-to-Account Onboarding - PRD

|                   |       |
| ----------------- | ----- |
| **Status**        | Draft |
| **Approver**      |       |
| **Approval Date** |       |

## Summary

This PRD covers the pre-go-live onboarding path from verbal yes to signed
contract, provisioned account, ToS acceptance, and FDE handoff. It is focused on
the account-level onboarding surface and the supporting integrations across
Manage App, Admin Console, DocuSign, Folk, Notion, and Slack.

The north star is that an AE should be able to take a willing customer from
"verbal yes" to a fully provisioned account with a signed contract in a single
phone call.

## Problem

Today's pre-go-live onboarding is fragile and manual. Sales must touch Manage
App, Admin Console, DocuSign, Folk, Notion, and Slack to bring on a single
client, and each tool has its own quirks:

- Deactivated invites after acceptance.
- New invitees defaulting to viewer instead of owner.
- Duplicate accounts from the v3 migration.
- No clean separation between account creation and project/agent creation.
- ToS acceptance hidden behind multiple login and navigation steps.

Deals that should close in minutes drag on, FDE handoffs are inconsistent, and
AEs lose confidence in the system at the moment they need to project competence
to a customer.

## Goals

- Reduce time from verbal yes to account created to under 5 minutes.
- Drive ToS acceptance within 48 hours above 80%.
- Keep manual engineering/support intervention on account creation below 10%.
- Remove manual invite-acceptance steps for internal AE/FDE users.
- Give AEs and FDEs one observable place to understand contract, invite, ToS,
  account, and handoff state.

## Personas

| Persona | Needs |
| ------- | ----- |
| AE | Create the account, send the contract/signup link, and see status without juggling six tools. |
| Contract signer | Sign the relevant contract/order form and accept ToS with minimal friction. |
| Additional customer user | Join an already-created account without being forced through legal-signer steps. |
| FDE | Receive a complete handoff with account, signer, contract, Folk, and onboarding context. |
| Sales/ops leadership | See which accounts are blocked, unsigned, overdue, or ready for handoff. |

## Success Metrics

| Metric | Target |
| ------ | ------ |
| Verbal yes to account created | < 5 minutes |
| ToS acceptance within 48 hours | > 80% |
| Manual engineering/support intervention on account creation | < 10% |
| Internal AE/FDE invite-acceptance steps | 0 |
| Duplicate/wrong-account incidents during onboarding | 0 after cleanup |

## Core Pain Points

### High-friction account creation for Sales

AEs juggle six tools and a pile of Manage App gotchas to start one client:

- AEs must touch Manage App, Admin Console, DocuSign, Folk, Notion, and Slack.
- Manage App feels risky to AEs because they are afraid of "breaking the AI."
- Account creation currently creates a project and agent, even when onboarding
  only needs an account and legal signer.
- AEs manually add themselves and the FDE to accounts they just created.
- A false "Failed to create account" error can appear even when the invite sent.
- New invitees default to viewer, so the AE must manually flip them to owner
  before ToS is possible.
- v3-migration duplicate accounts cause AEs to land on the wrong record.
- Account/project setup varies by AE and customer because there is no standard
  process.

### High-friction acceptance for external users

Customers are forced through a five-step, desktop-shaped acceptance chain:

1. Receive temp password.
2. Set new password.
3. Log in.
4. Navigate to Admin Console.
5. Accept ToS.

This breaks frequently for SMB operators who are mobile-first, do not reliably
read long emails, and may only respond to text links. Emails also land in spam,
and multi-owner stores often share passwords that later get reset and not
re-shared.

### Fuzzy MSA and ToS application logic

The system cannot express which locations a contract covers:

- Some MSAs cover franchisees; some do not.
- ToS is treated as account-level only, but enterprise/franchisee deals need
  location-aware contract coverage.
- ToS signer identity is collected manually instead of being read from the
  DocuSign envelope.
- ToS click-throughs, LOIs, MNDAs, MSAs, and order forms have no unified state.

### Fragmented source of truth

Account state is scattered across Folk, Notion, Manage App, Admin Console,
Slack, and DocuSign. AEs disagree on the source of truth, sales-stage changes do
not reliably sync between Notion and Folk, and WeChat/SMS conversations are
off-platform and manually logged at best.

### Missing automation and visibility

Slack client channels, Notion handoff tickets, role assignments, and many stage
updates are created manually. AEs cannot programmatically answer "who has not
signed ToS yet?" without clicking through accounts one by one.

## Product Principles

1. **Sales lives in Slack.** AEs should not need to open Manage App for routine
   contract/account onboarding. Account creation, invitations, and contract
   status should surface through Slack and Slack notifications.
2. **One step per screen, one screen if possible.** Replace invite, reset
   password, login, Admin Console navigation, and ToS acceptance with a single
   page for password creation and contract/ToS acceptance.
3. **Internal users are not customers.** AE/FDE users should be auto-provisioned
   by trusted email domain. No invite email, manual acceptance, or forgotten
   self-add step.
4. **State is observable.** For every account, users should see who was invited,
   who accepted, who signed, what stage it is in, and what is overdue.
5. **Folk and Notion are bidirectional.** Either side can update; the other
   reflects the update and pushes relevant status into Slack.
6. **Velocity is the tiebreaker.** When two designs are otherwise correct, ship
   the one that gets a willing customer signed faster.

## Scope

### v1: Account creation, contract acceptance, and handoff

v1 supports SMB and enterprise accounts from day one.

Must have:

- Account creation flow that collects:
  - Account name.
  - Folk ID.
  - DocuSign envelope ID.
  - Contract signer name and email.
  - Contract type: SMB or Enterprise.
  - If Enterprise, an `MSA covers franchisee locations` checkbox collected for
    v2 forward compatibility.
- Account creation without auto-creating a project or agent.
- AE auto-provisioned as account owner at account creation by email domain.
- Assigned FDE auto-provisioned as account owner after customer contract
  acceptance.
- Contract signer invited with one link to set password and complete required
  contract/ToS actions.
- Slack channel `#client-<name>` auto-created on contract acceptance, with AE,
  FDE, Ali, and Maria added.
- Notion onboarding ticket auto-created and pre-filled from Folk.
- Slack notifications for invitation accepted/account created, contract signed,
  and stage change.
- ToS logic for SMB and enterprise:
  - SMB: owner accepts order form and ToS at account level, covering all their
    stores.
  - Enterprise: corporate signer signs MSA and order form through DocuSign. In
    v1, the MSA covers corporate-owned stores only; franchisee-owned stores
    still require ToS.
- `location_type` model support for `corporate_owned` and `franchisee_owned`.
- Stage 7b: Store Activation formalized in Notion and Folk schemas.

v1 should avoid inviting non-signers during the initial legal-signing flow. The
initial purpose is to get the contract signed and the account created. Additional
users can be invited after the signer completes the required steps.

Implementation note: the target operating model is Slack-first. The source draft
also references a Manage App "Create Account" modal. If Slack forms are not
ready for the first slice, the same required fields may be implemented in Manage
App while preserving the Slack notifications and target Slack-first direction.

### v2: MSA override logic and mobile convenience

v2 adds the real coverage logic and more flexible invite workflows:

- MSA-level `covers_franchisees` flag:
  - If true, franchisee locations inherit the MSA and no per-franchisee ToS is
    needed.
  - If false, each franchisee must accept ToS for their own locations while
    corporate-owned locations remain covered by the MSA.
- Per-location ToS tracking.
- Franchisee sub-accounts with visibility scoped to their own stores.
- Slackbot support to add additional external users after account creation.
- Mobile-friendly invite link generation per invitee, so an AE can manually
  share the link over SMS, WeChat, or another customer-preferred channel.
- Automated Notion/Folk sales-stage sync with stage updates pushed to Slack.
- More robust RBAC and privacy features based on permissions and store access,
  mostly deferred to a separate project.

## Requirements

### Account creation

- AE can create an account from the approved v1 entry point.
- Account creation requires the signer email to match the email used for the
  DocuSign envelope.
- Account is created without automatically creating a project or agent.
- AE is joined as owner without receiving or accepting an invite.
- Folk record is updated with Manage App account ID and contract-sent date when
  applicable.
- Contract signer receives a unique account creation/signup link.
- Confirmation posts to `#client-updates`.

### External signer acceptance

- Signer lands on a single page that supports password creation and required
  legal actions.
- For SMB:
  - Signer completes embedded DocuSign order form.
  - Signer checks the ToS acceptance box.
  - Account creation remains blocked until DocuSign completion is confirmed.
- For Enterprise:
  - Signer completes embedded DocuSign MSA and order form.
  - Account creation remains blocked until DocuSign completion is confirmed.
- On completion:
  - User account is created.
  - Contract/order form/ToS acceptance is logged with date and signer.
  - Slack channel is created.
  - Folk is updated.
  - Notion ticket is created.
  - Assigned FDE is added as owner.

If embedded DocuSign cannot be delivered reliably, the fallback must be an
explicit "check your email for DocuSign" CTA with timestamp/context, not a silent
failure.

### Additional customer user acceptance

After the legal signer has completed the contract, AE/FDE users can add
additional customer users:

- User clicks email invite link, or in v2 a manually shared mobile-friendly
  link.
- User lands on a single Admin Console page to set password and submit.
- If a newly added franchisee location requires its own ToS in v2, the
  invite-acceptance page surfaces the ToS checkbox at that step.
- Per-location ToS for newly added locations belongs in Admin Console
  invite-acceptance, not in the account creation modal.

### FDE handoff

- FDE receives a ping in `#client-<name>`.
- FDE sees a Notion ticket in the Client Master Database, pre-populated from
  Folk.
- FDE creates projects/locations and configures agents in Manage App after the
  account exists.
- FDE advances stage in Notion when ready; the update syncs to Folk and Slack.

### Visibility loop

At minimum, AE/FDE users need Slackbot visibility commands:

- `status <account>` returns invite, ToS, DocuSign, current stage, and FDE owner.
- `pending-tos` returns accounts with unsigned ToS, sorted by days outstanding.
- `pending-tos <AE name>` filters pending ToS by AE.
- `pending-invites <account>` lists pending invites for an account.

## Data and State Model Implications

- Account creation must not imply project or agent creation.
- Internal users need email-domain-based auto-provisioning.
- Contract state must include DocuSign envelope ID, contract type, signer name,
  signer email, signed status, signed timestamp, and source.
- ToS acceptance must be trackable at account level and, for enterprise and
  franchisee structures, at location level.
- v1 needs `location_type` on locations: `corporate_owned` or
  `franchisee_owned`.
- v2 needs an MSA-level `covers_franchisees` flag.
- Order form state must be represented for every account.
- Folk ID is the primary join key across Folk, Manage App, Notion, and Slack;
  Manage App account ID is a fallback identifier.

## Dependencies and Spikes

1. **Auth auto-provisioning.** Validate email-domain-based provisioning of
   internal AE/FDE users without invitation flow.
2. **DocuSign integration.** Track envelope ID, signed-status webhook, optional
   embedded signing, and signer identity pulled from the envelope.
3. **External signup flow rebuild.** Replace temp-password, set-password, and
   accept-invite with one page that handles password setup and contract/ToS.
4. **Manage App bug fixes.** Fix account deactivation on accept, viewer-role
   default, and false-failure invite send behavior.
5. **Folk/Manage App/Notion/Slack sync.** Make sync bidirectional and reliable.
6. **Data model migration.** Add `location_type` in v1 and MSA
   `covers_franchisees` in v2.
7. **Slack bot platform.** Support forms, channel creation, user invitation,
   posting to channels, and backend API calls.
8. **Order form artifact in DocuSign.** Every account requires an order form
   signed through DocuSign. The ToS remains clickwrap; it does not move into
   DocuSign.

## Risks and Mitigations

| Risk | Mitigation |
| ---- | ---------- |
| Embedded DocuSign is not reliable because of iframe, CORS, or API limits | Spike early; ship explicit email-link fallback if needed. |
| Customer communication remains fragmented across email, SMS, and WeChat | Keep email as system of record; provide mobile-friendly links for manual sharing. |
| Shared-password customer behavior creates confusion | Invite the legal signer directly and avoid inviting non-signers until after signing. |
| Duplicate accounts cause AEs to use the wrong record | Dedupe v3-migration accounts before v1 ships. |
| Folk personal views are unavailable | Do not depend on per-AE Folk dashboards for critical visibility; surface status in Slack. |
| DocuSign templates are unstable | Do not infer contract type from template in v1; revisit after contract templates stabilize. |

## Housekeeping

These are small-effort, high-impact fixes that should ship alongside or before
v1:

- Add Stage 7b: Store Activation to Notion and Folk.
- Dedupe v3-migration duplicate accounts in Manage App and Admin Console.
- Remove the Admin Console self-signup link that creates orphan/duplicate
  accounts.
- Audit or eliminate account deactivation logic on invite acceptance.
- Auto-add AE/FDE as owners without invite acceptance.
- Replace the external temp-password flow with the new single-page signup flow.
- Fix the false "Failed to create account" error when invite send succeeds.
- Make default invite role respect the selected role instead of defaulting to
  viewer.
- Standardize on "ToS" naming everywhere.
- Standardize Mercury formatting/templates for new account communications.
- Make the invite/accept page mobile-readable even before v2 link-sharing.

## Open Questions

- Is the final v1 creation entry point Slackbot, Manage App modal, or a
  transitional implementation of both?
- In the franchisor/franchisee structure, does a single corporate-signed order
  form cover franchisee locations, or does each franchisee eventually need its
  own order form alongside ToS?
- Who owns cleanup of v3-migration duplicate accounts before v1 ships?
- What is the final fallback copy and CTA if embedded DocuSign fails?
- When should subscription selection happen relative to ToS/order-form signing?
  Current proposal: keep billing/subscription automation separate until the
  sales process is more stable.

## Out of Scope

- DocuSign reminder timing logic; senders configure this in DocuSign.
- Folk integration with WeChat or SMS.
- Billing logic, invoicing cadence, payment terms, and credit-card vs invoice
  flows.
- Full RBAC/privacy redesign beyond what v1/v2 require for account onboarding.

## Referenced Artifacts

The source draft referenced supporting artifacts that are not stored in this
repository yet:

- MSA vs ToS franchisor/franchisee structure diagram from 2026-05-18.
- Proposed solution walkthrough screen recording from 2026-05-19.
- Backend walkthrough recording.
- Create Account modal screenshots.
- Subscription clarification screenshot from 2026-06-08.
