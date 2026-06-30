# Customer RBAC Implementation Plan

Last updated: 2026-06-29

Status: draft implementation plan

Repos in scope:

- `pal-mono`: backend authorization, team service, billing, operations, catering,
conversation, feedback, and migration work.
- `pal-admin-console`: customer-facing route gating, scoped data views, and role
UI.
- `pal-manage-app`: internal role administration, store assignment, and billing
toggles.

## Summary

The current customer RBAC system has the right primitives, but policy is split
between backend route decorators, backend role config, and frontend role checks.
The next implementation should collapse customer roles, make store scoping the
default, and centralize permissions so later changes are small policy edits
instead of endpoint rewrites.

The target customer roles are:

- Product role `Admin`, backend key `account_admin`: corporate or account-level
customer admins. This is not the same as Palona's internal
`services.auth_types.UserRole.Admin` bypass.
- Product role `Store Owner`, backend key `store_owner`: store-scoped operator
with write access to assigned stores, except for product areas that are not
customer-editable yet.
- Product role `Store Member`, backend key `store_member`: store-scoped
read-mostly user.

Recommended implementation principle:

> Every customer-facing permission decision should be expressible as a role
> permission plus a resource scope. Billing adds one data condition: whether the
> store is configured as store-paid. Store-paid billing gives visibility to
> Store Owners only; Store Members still have no billing visibility. For
> example, giving Store Member write access to Catering Requests later should be
> a one-line change in the role permission map, followed by tests.

## Current Implementation Map

### pal-mono

Relevant current files:

- `services/auth_service/config.py`
  - Defines `ROLE_PERMISSIONS`, `PERMISSION_REGISTRY`, and resource metadata.
  - The live role policy is config-backed today.
- `services/auth_service/authorization.py`
  - Resolves direct `resource_role_assignment` rows and parent resources.
  - Uses config permissions through `get_role_permissions`.
  - Has an internal Palona `UserRole.Admin` bypass.
- `db/tables/resource_role_assignment.py`
  - Supports multiple roles per user/resource. The new customer model should
  still create only the three customer-facing role keys.
- `db/tables/permission.py` and `db/tables/role_permission.py`
  - Exist for DB-backed permissions, but the checker does not currently source
  role permissions from these tables.
- `api/routes/admin/_projects.py`
  - Already demonstrates store scoping by returning only assigned projects for
  project-level users.
- `api/routes/admin/__init__.py`
  - Team routes are account-level today. Team list uses `account.read`; team
  mutations use `account.team_manage`.
- `services/team_service/_implementation.py`
  - Invitations support account-level or project-level assignment through
  `project_ids`.
  - Updates do not currently accept or apply `project_ids`.
  - Removal clears account-level roles but does not clear project-level roles.
  - Team listing returns all account users/invites, not a caller-scoped view.
- `api/routes/admin/_conversation.py`, `_feedback.py`, `_subscription.py`,
`_catering.py`, and `api/routes/operation/*`
  - Several account-scoped routes need store filtering or resource-level checks.

Admin naming proposal:

- Use product label `Admin` in the UI and customer-facing copy.
- Use canonical backend role key `account_admin` in RBAC data, API payloads, and
  role policy config.
- Keep legacy backend role key `owner` as a temporary migration alias only.
  Do not create new `owner` assignments after this rollout starts.
- Do not use plain backend role key `admin` for customer RBAC because
  `services.auth_types.UserRole.Admin` already means internal Palona admin and
  bypasses authorization checks.
- Optional later cleanup: rename the internal enum/display language to
  `InternalAdmin` or `PalonaAdmin` to reduce ambiguity, but do not block this
  RBAC migration on that rename.

### pal-admin-console

Relevant current files:

- `contexts/AccountContext.tsx`
  - Stores the current account and role returned by `/users/me/accounts`.
- `lib/constants/route-permissions.ts`
  - Hard-codes broad non-staff access versus staff access.
- `lib/constants/features.ts`
  - Uses account allowlists for Operations and Catering feature availability.
- `components/(console)/team/actions.ts`
  - Defines frontend role names and maps legacy role keys.
  - Sends `project_ids` on invites for store-level roles.
  - Sends `projectIds` on role updates, but the backend schema does not yet
  apply them.
- `components/(console)/team/Team.tsx`
  - Contains legacy role options and mixed Owner-only versus Store Owner team
  controls.

The frontend should keep feature flags separate from RBAC. A route or action
should require both:

1. Feature availability, when applicable.
2. Backend permission for the current user and resource.

### pal-manage-app

Relevant current files:

- `components/(console)/team/actions.ts`
  - Currently knows only `Owner`, `Manager`, and `Viewer`.
- Existing billing UI supports account-level and project-level subscription
workflows, including independent project subscriptions.

Manage App is internal, but it still needs to create and edit the new customer
role assignments correctly.

## Target Role Model


| Product role              | Backend role key                               | Assignment scope | Purpose                                                                                 |
| ------------------------- | ---------------------------------------------- | ---------------- | --------------------------------------------------------------------------------------- |
| Admin                     | `account_admin`                                | Account          | Corporate/account-level customer user. Has all account stores in scope.                 |
| Store Owner               | `store_owner`                                  | Project/store    | Store-scoped user with store write access and scoped team management.                   |
| Store Member              | `store_member`                                 | Project/store    | Store-scoped read-mostly user. Replaces legacy Manager and Viewer for customer console. |
| Internal Palona Admin/FDE | `UserRole.Admin` or internal-only service role | Internal         | Palona-only bypass or internal write access for product areas not ready for clients.    |


Billing-enabled Store Owner is not a separate role. It is an effective access
state derived from:

1. The user has `store_owner` on the store.
2. The store is configured as store-paid or has an independent project
   subscription.
3. The user is not merely a `store_member`; Store Members do not get billing
   visibility even when the store is store-paid.

Legacy roles:

- `owner` should become `account_admin`, or remain as a temporary alias displayed
  as Admin during migration.
- `manager` and `viewer` should collapse to `store_member`.
- `staff` should not be migrated to any of the three customer-console roles.
  Existing `staff` users fail closed for customer-console access and must be
  explicitly re-assigned to Admin, Store Owner, or Store Member if they still
  need access.
- Existing `store_owner` assignments can remain, but their permission set must
  change.

## Target Permission Matrix

All Store Owner and Store Member access is limited to assigned stores. Admin
access is account-wide, not global across accounts. Internal Palona Admin/FDE
access is separate from customer roles.


| Product area                            | Store Member                       | Store Owner                                                        | Admin                             | Internal Palona/FDE              |
| --------------------------------------- | ---------------------------------- | ------------------------------------------------------------------ | --------------------------------- | -------------------------------- |
| Dashboard                               | Read assigned stores               | Read assigned stores                                               | Read all account stores           | Read all                         |
| Conversations                           | Read assigned stores               | Read assigned stores                                               | Read all account stores           | Read/write as needed             |
| Feedback                                | Read/write assigned stores         | Read/write assigned stores                                         | Read/write all account stores     | Read/write all                   |
| Agents                                  | Read assigned stores               | Read assigned stores                                               | Read all account stores           | Write/edit configuration         |
| Locations / Stores                      | Read assigned stores               | Read/write assigned stores                                         | Read/write all account stores     | Read/write all                   |
| Brand/account brand settings            | Read only or hidden                | Read only or hidden                                                | Read/write                        | Read/write all                   |
| Team                                    | No team page, or self/profile only | Manage Store Owner and Store Member users for assigned stores only | Manage customer users for account | Manage all                       |
| Subscription/Billing                    | No access                          | Store billing only when the assigned store is store-paid           | Account/project billing access    | Full billing access              |
| Docs                                    | Read                               | Read                                                               | Read                              | Read/write docs admin as needed  |
| Account settings                        | Self/profile and status only       | Self/profile and status only                                       | Account settings write            | Full internal access             |
| Catering requests list                  | Read assigned stores               | Read assigned stores                                               | Read all account stores           | Read/write all                   |
| Catering request details                | Read assigned stores               | Read/write assigned stores                                         | Read/write all account stores     | Read/write all                   |
| Operations portfolio/cameras/monitoring | Read assigned stores               | Read assigned stores                                               | Read all account stores           | Write/edit checks, rules, events |


## Resolved Product Decisions

These decisions are reflected in the target matrix and implementation plan:

- Billing/subscription access: Store Owners should have billing/subscription
  access only for assigned stores that pay for their own bill. Store Members do
  not get billing visibility even when a store is store-paid. Corporate-paid
  account billing remains account-level Admin/internal access. Implement this
  with store/project payer scope or independent project subscription state, not
  a fourth customer role.
- Operations events/checks: Store Owners should not create or modify
Operations/Vision events or checks yet. These writes stay Palona internal for
now.
- Invitations: Store Owners can invite users to their assigned stores as either
Store Owner or Store Member. They cannot invite account Admins or assign users
to stores outside their own scope.
- Agent configuration: agent configuration remains read-only for all
customer-facing roles, including Admin. FDE/internal workflows own agent
configuration edits.

## Permission Design

### Central policy file

For the MVP, keep permissions config-backed in
`services/auth_service/config.py`, because that is what `check_permission` uses
today. The important change is to make this file the single customer policy
source and remove role-specific business logic from route handlers and frontend
code where possible.

Use a shape like:

```python
ROLE_PERMISSIONS = {
    "account_admin": {
        "account.read",
        "account.write",
        "project.read",
        "project.write",
        "brand.read",
        "brand.write",
        "team.read",
        "team.manage",
        "conversation.read",
        "feedback.read",
        "feedback.write",
        "agent.read",
        "billing.read",
        "billing.write",
        "docs.read",
        "catering.read",
        "catering.write",
        "operation.read",
    },
    "store_owner": {
        "account.read",
        "project.read",
        "project.write",
        "brand.read",
        "team.read",
        "team.manage",
        "conversation.read",
        "feedback.read",
        "feedback.write",
        "agent.read",
        "docs.read",
        "catering.read",
        "catering.write",
        "operation.read",
    },
    "store_member": {
        "account.read",
        "project.read",
        "brand.read",
        "conversation.read",
        "feedback.read",
        "feedback.write",
        "agent.read",
        "docs.read",
        "catering.read",
        "operation.read",
    },
}
```

Billing is the exception to pure role permission because payment ownership is
store data. Keep its policy centralized, but do not introduce a fourth customer
role. The effective rule is:

```python
can_manage_store_billing = (
    has_project_role(user_id, project_id, "store_owner")
    and project_billing_policy(project_id).payer_scope == "store"
)
```

The source of `payer_scope` can be the existing independent project
subscription state if it is unambiguous. If not, add a small billing policy field
or table with values such as `account` and `store`.

Example future tweak:

```python
"store_member": {
    # ...
    "catering.read",
    "catering.write",
}
```

That is the intended one-line policy change when Store Members are allowed to
write Catering Requests later. Endpoint code should already be checking
`catering.write`, so no system rewrite is needed.

### Permission naming

Prefer permission names in the `resource.action` format with exactly one dot,
such as `billing.read`, `billing.write`, `team.manage`, and `operation.read`.
This stays compatible with the current `permission_name_format_check` on
`db/tables/permission.py`.

If we decide to make `role_permission` the source of truth now, do that as a
separate migration step:

1. Confirm the permission name format.
2. Seed all permissions and role-permission rows.
3. Update `get_role_permissions` to read from DB with caching.
4. Keep config as the seed/default source, not a second live policy system.

Do not half-migrate role policy into DB while `check_permission` still reads the
config map. That would make permission changes look correct in data but not
actually enforce them.

### Scope rule

A permission answers "what can this role do?" Scope answers "where can this user
do it?"

Use these rules:

- Account-level `account_admin` applies to every project in the account.
- Project-level `store_owner` and `store_member` apply only to the assigned
project/store.
- Child resources must resolve to their owning project whenever possible.
- Account-scoped list endpoints that return store-backed data must filter to
accessible project IDs before querying or before returning data.

Recommended helper:

```python
accessible_project_ids = await authz.get_accessible_project_ids(
    session=session,
    user_id=context.user_id,
    account_id=account.id,
    permission="conversation.read",
)

effective_project_ids = authorize_requested_project_ids(
    requested_project_ids=query.project_ids,
    accessible_project_ids=accessible_project_ids,
)
```

This should become the common pattern for Dashboard, Conversations, Feedback,
Catering, Operations, and any account route that can expose store-specific data.

## Backend Implementation Plan

### 1. Add the new role and permission policy

Files:

- `services/auth_service/config.py`
- `services/auth_service/authorization.py`
- `api/schemas/admin/team.py`
- `services/team_service/schema.py`
- Tests under `tests/services/auth_service/` and `tests/integration/`

Work:

1. Add `account_admin`, `store_owner`, and `store_member` to the role policy.
2. Remove agent write permissions from all customer-facing roles.
3. Do not assign `operation.write` to customer-facing roles.
4. Add legacy aliases:
   - `owner` maps to `account_admin` during migration.
   - `manager` and `viewer` map to `store_member`.
   - `staff` is rejected in new customer-console invitations. Existing `staff`
     assignments are report-only and fail closed unless an operator explicitly
     reassigns the user to one of the three supported roles.
5. Replace role precedence with:
   - Account roles: `account_admin`
   - Project roles: `store_owner`, `store_member`
6. Add tests that assert the exact permission set for each role.

### 2. Add store-scope authorization helpers

Files:

- `services/auth_service/authorization.py`
- `services/auth_service/dependencies.py`
- Possibly a new `services/auth_service/scope.py`

Work:

1. Implement a helper to return accessible project IDs for a user/account and
  permission.
2. Implement a helper that validates requested `project_ids` against the
  accessible set.
3. Use 403 when the user explicitly asks for a store outside their scope.
4. Default to the user's accessible stores when no project filter is supplied.
5. Return an empty result only when the user has valid account access but no
  stores for that product area.

This avoids the current pattern where an account route guarded by `account.read`
can accidentally return all account data or block project-level users entirely.

### 3. Apply scope to store-backed routes

High-priority backend surfaces:

- `api/routes/admin/_projects.py`
  - Keep the existing scoped project list pattern.
  - Ensure account admins see all projects, store roles see assigned projects.
- Dashboard/reporting routes in `api/routes/admin/__init__.py`
  - Constrain `project_ids` query params to accessible projects.
  - Default Store Owner/Member views to assigned stores, not all stores.
- `api/routes/admin/_conversation.py`
  - List conversations only for accessible projects.
  - Authorize conversation detail/message reads by resolving conversation to
  project.
- `api/routes/admin/_feedback.py`
  - Replace account-wide filtering with project-aware feedback access.
  - Check `feedback.write` for submit/update actions.
- `api/routes/catering/__init__.py` and admin catering routes
  - Check `catering.read` for list/detail reads.
  - Check `catering.write` for detail mutation.
  - Resolve request ownership to project/store before allowing mutation.
- `api/routes/operation/*`
  - Check `operation.read` for customer reads.
  - Keep operations config/check/event writes internal-only or behind
  `operation.write`, with no customer roles assigned that permission.
- Agent and agent-config routes
  - Keep customer reads.
  - Restrict create/update/delete/config writes to internal Palona/FDE paths.
- Subscription routes in `api/routes/admin/_subscription.py`
  - Separate account billing from project/store billing.
  - Require `billing.read` or `billing.write` on the account for account-level
  billing.
  - For Store Owner project billing, require `store_owner` on the project and
  require the project billing policy to be store-paid.

### 4. Fix team management semantics

Files:

- `api/routes/admin/__init__.py`
- `api/schemas/admin/team.py`
- `services/team_service/_implementation.py`
- `services/team_service/schema.py`
- `tests/services/team_service/`

Work:

1. Add explicit scope updates to team member update requests. Do not model this
   as a plain nullable `project_ids` field because omitted, `null`, and `[]`
   have different security meanings.
   - Omitted scope update: leave the user's current store/account assignments
     unchanged.
   - `scope_update = "account"`: convert to an account-level role. This is
     allowed only for `account_admin` and only by callers who can manage
     account-level roles.
   - `scope_update = "replace_projects"` with non-empty `project_ids`: replace
     project-level assignments with exactly those stores after validating the
     caller can manage every requested store.
   - `scope_update = "clear_projects"`: explicitly remove all project-level
     assignments. This should be restricted to Admin removal/deactivation flows
     or a dedicated no-access action.
   - `scope_update = "replace_projects"` with `project_ids = []` is invalid.
2. Replace the account-level `account.team_manage` mutation decorator with
   caller-aware checks:
   - `account_admin` can invite/update/remove customer users across the account.
   - `store_owner` can invite/update/remove `store_owner` and `store_member`
     users only for stores they own.
   - `store_owner` cannot invite or modify `account_admin`.
   - `store_owner` cannot create account-level roles by omitting `project_ids`.
   - `store_member` cannot manage team.
3. Make team list caller-scoped:
   - `account_admin` sees customer team members and invitations for the account.
   - `store_owner` sees only users/invitations that overlap their assigned
     stores, excluding account admins and internal users.
   - `store_member` gets no team list, or only self/profile if product wants it.
4. Update removal logic:
   - Remove project-level role assignments as well as account-level roles.
   - For scoped Store Owner removal, remove only assignments in the caller's
     scope.
   - Deactivate account membership only when the user has no remaining roles in
     the account.
5. Keep invitation acceptance behavior mostly as-is:
   - `project_ids is None` means account-level role.
   - Non-empty `project_ids` means project-level role assignment per store.
   - Empty `project_ids` should remain invalid.

### 5. Implement flexible store-level billing

Billing should not create a fourth customer role. Some customers have
corporate-paid account billing. Some franchisees pay their own store bill. Store
Owner billing access should be computed from role plus billing ownership.

Use this effective rule:

- Account Admin has account billing access.
- Store Owner has billing access only for assigned stores whose payer scope is
  `store` or whose subscription is an independent project subscription.
- Store Member never has billing access.

Backend rules:

1. Account-level billing endpoints require account-level `billing.read/write`.
2. Project-level independent subscription endpoints require:
   - `store_owner` on the project, and
   - project billing policy `payer_scope == "store"`.
3. Billing UI should show store billing only when both are true:
  - The store has independent/project-level billing, or is configured as
   store-paid.
  - The user is Store Owner for that store, or Account Admin for the account.

Manage App should expose the payer scope as an explicit per-store billing toggle.
Changing that toggle updates billing policy/subscription ownership, not the role
model.

### 6. Migrate existing roles and data

Migration approach:

1. Create a pre-migration report of all `resource_role_assignment` rows grouped
  by account, resource type, role, and user.
2. Apply aliases in code first so old assignments keep working during deploy.
3. Backfill role rows:
   - `owner` account role -> `account_admin` account role.
   - Existing `store_owner` project role -> keep `store_owner`.
   - `manager` and `viewer` -> `store_member`.
   - `staff` -> no customer-console role. Do not map `staff` to
     `store_member` automatically. Report these users and withhold
     customer-console access until an operator explicitly reassigns them to
     `account_admin`, `store_owner`, or `store_member`.
4. For legacy account-level Manager/Viewer users, generate a manual review list.
   Fail closed when no approved store mapping exists:
   - Do not auto-assign `store_member` to every current account project.
   - Do not keep legacy Manager/Viewer as an account-wide customer role after
     the migration cutover.
   - Mark the user for manual review and withhold customer-console store access
     until explicit `project_ids` are approved.
5. Set payer scope to `store` only for stores/franchisees that pay their own
   bill.
6. After migration, stop creating legacy role keys.
7. After verification, remove legacy aliases in a later cleanup release.

### 7. Update pal-admin-console

Files:

- `contexts/AccountContext.tsx`
- `lib/constants/route-permissions.ts`
- `lib/constants/features.ts`
- `components/(console)/team/actions.ts`
- `components/(console)/team/Team.tsx`
- Product pages for Agents, Operations, Locations, Billing, Catering, Feedback,
Conversations, Dashboard

Work:

1. Replace frontend role unions with:
  - `Admin`
  - `Store Owner`
  - `Store Member`
2. Map backend keys:
  - `account_admin` and temporary `owner` -> `Admin`
  - `store_owner` -> `Store Owner`
  - `store_member`, temporary `manager`, and temporary `viewer` ->
  `Store Member`
3. Replace broad route gating with backend permissions:
  - Add or consume a `/accounts/{account_name}/me/permissions` endpoint.
  - Include accessible project IDs and permission names for the current
  account.
  - Keep frontend checks for UX only. Backend remains authoritative.
4. Use the scoped `/accounts/{account_name}/projects` response for all store
  selectors.
5. Default Store Owner/Member pages to assigned stores.
6. Remove "all locations" selection for users without account-wide scope.
7. Hide or disable write controls based on permissions:
  - Agents are read-only for customer roles.
  - Operations config/check/event editing is hidden for customer roles.
  - Billing appears only for account admins or Store Owners on store-paid
  stores.
  - Team invite/edit is scoped for Store Owner.
8. Keep feature flags such as Operations and Catering allowlists, but require
  permissions in addition to feature availability.

### 8. Update pal-manage-app

Files:

- `components/(console)/team/actions.ts`
- Team management UI
- Billing/subscription management UI

Work:

1. Add role options for Admin, Store Owner, and Store Member.
2. Keep legacy role display only for migration/audit views.
3. Require project selection for Store Owner and Store Member.
4. Add an explicit "store pays its own billing" toggle that updates payer scope
  or independent project subscription state for selected stores.
5. Show current account-level versus project-level role assignments clearly.
6. Use Manage App for migration review and manual correction where account-level
  Manager/Viewer users need store assignment cleanup.

## Test Plan

Backend unit tests:

- Role permission snapshots for `account_admin`, `store_owner`, and
  `store_member`.
- Legacy alias behavior for `owner`, `manager`, and `viewer`.
- `check_permission` for account-level and project-level customer roles.
- Accessible project helper:
  - Account admin returns all account projects.
  - Store owner/member returns only assigned projects.
  - Store-paid billing policy grants Store Owner billing only on assigned,
  store-paid projects.
- Team service:
  - Store Owner can invite Store Owner/Store Member for owned stores.
  - Store Owner cannot invite Admin.
  - Store Owner cannot assign stores they do not own.
  - Store Member cannot invite users.
  - Update scope modes distinguish omitted scope, account-level conversion,
    project replacement, explicit project clearing, and invalid empty
    replacement.
  - Removal clears project-level role rows.
- Migration:
  - Legacy account-level Manager/Viewer users without approved store mappings do
    not receive default all-store access.
  - Legacy account-level Manager/Viewer users with approved mappings receive
    only the approved project assignments.
  - Legacy Staff users are not mapped to Store Member automatically and do not
    retain customer-console access without explicit reassignment.

Backend integration tests:

- Dashboard, Conversations, Feedback, Catering, Operations, and Locations never
  return unassigned store data for Store Owner/Member.
- Direct detail URLs return 403 or 404 for unassigned resources.
- Store Member can read Catering Requests but cannot write until
  `catering.write` is added to the role.
- Store Owner can write Catering Request details for assigned stores.
- Customer roles cannot write agent config.
- Customer roles cannot write Operations/Vision checks/events.
- Billing endpoints distinguish corporate account billing from store-paid
  project billing.

Frontend tests:

- Role mapping from backend keys to product labels.
- Route gating for Admin, Store Owner, Store Member.
- Store selector contains only assigned stores for store-scoped roles.
- Team invite/update forms enforce role and project constraints.
- Billing controls render only when billing permission is present.
- Agent and Operations write controls are absent or disabled for customer roles.

## Rollout Plan

1. Ship backend role aliases and permission config first.
2. Add store-scope helpers and apply them to high-risk data surfaces:
  Dashboard, Conversations, Feedback, Catering, Operations, Team, Billing.
3. Add backend tests for every role/scope combination.
4. Update pal-admin-console to consume backend-scoped projects and permissions.
5. Update pal-manage-app role administration and billing toggle.
6. Run migration in a dry-run/report mode.
7. Review legacy Manager/Viewer users that need explicit store assignment.
8. Apply migration in staging.
9. Smoke test with fixture users:
  - Account Admin
  - Store Owner for one store
  - Store Owner for multiple stores
  - Store Owner with project billing
  - Store Member
  - Internal Palona Admin
10. Apply migration in production.
11. Remove creation paths for legacy roles.
12. Remove legacy aliases in a later cleanup once no rows remain.

## Observability and Audit

Add structured logs for denied permission checks:

- user ID
- account ID
- requested resource type and ID
- requested permission
- role keys found
- accessible project IDs count
- requested project IDs count

For privacy and log size, avoid logging customer content or full large ID lists
unless the event is sampled or explicitly part of an audit job.

Add migration reports:

- Users with legacy account-level Manager/Viewer roles.
- Users with legacy Staff roles that need explicit reassignment or removal.
- Users with project-level roles on deleted/inactive projects.
- Users with both account-level and project-level customer roles.
- Stores with independent billing but payer scope not set to `store`.
- Store-paid projects with no Store Owner assigned.

## Open Decisions

Recommended defaults are included here so implementation can proceed, but these
should be explicitly confirmed before migration.


| Decision                        | Recommendation                                                                        |
| ------------------------------- | ------------------------------------------------------------------------------------- |
| Customer Admin backend key      | Use `account_admin`; keep `owner` as temporary alias.                                 |
| Store billing toggle            | Use store/project billing payer scope, not a fourth role.                             |
| Agent configuration writes      | Internal Palona/FDE only for now.                                                     |
| Operations/Vision writes        | Internal Palona/FDE only for now.                                                     |
| Brand writes                    | Allow customer Admin for now; keep Store Owner/Member read-only or hidden.            |
| Account settings writes         | Customer Admin only for account-level settings; Store Owner/Member self/profile only. |
| Legacy Manager/Viewer migration | Map to Store Member, but manually review store assignments.                           |
| DB-backed role permissions      | Keep config-backed for MVP unless we schedule the full seed/cache/checker migration.  |


## Definition of Done

- Backend policy for customer roles is centralized and tested.
- Store-scoped users cannot view or mutate unassigned store data through API or
direct URLs.
- Store Owners can invite Store Owners and Store Members only for their stores.
- Store-level billing access can be turned on or off per store without changing
the base Store Owner role.
- Agents and Operations/Vision configuration writes are unavailable to
customer-facing roles.
- pal-admin-console displays only the new product roles and respects backend
permissions.
- pal-manage-app can administer the new roles, store assignments, and billing
access.
- Legacy roles are aliased during rollout and no longer created after migration.
