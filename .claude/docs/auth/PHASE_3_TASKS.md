# Phase 3: Team Management API - Detailed Task Breakdown

**Timeline**: Weeks 5-6

**Goal**: Implement team member invitation, role management, and multi-account support

**Related**: [TDD_RBAC.md](./TDD_RBAC.md), [PHASE_2_TASKS.md](./PHASE_2_TASKS.md)

---

## Prerequisites

Before starting Phase 3, ensure Phase 2 is complete:

- [x] Core authorization functions implemented
- [x] Permission decorators working
- [x] All admin endpoints protected with RBAC
- [x] Authorization tests passing
- [x] Performance targets met (<50ms p99)

---

## Design Context

### Team Management Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    INVITATION FLOW                           │
└─────────────────────────────────────────────────────────────┘

1. Owner invites user (email + role)
   ↓
2. System creates invitation record + secure token
   ↓
3. Email sent with invitation link
   ↓
4. User clicks link and accepts invitation
   ↓
5. System creates:
   - Account membership (account_users)
   - Role assignment (resource_role_assignments with resource_type='account')
   ↓
6. User can now access account
```

### Role Management

- **Owner only** can invite, change roles, and remove team members
- At least one Owner must exist per account (cannot remove last owner)
- Role changes take effect immediately (cache invalidation)
- Removing user deletes all role assignments and deactivates membership

---

## Task Categories

1. [Team Management Endpoints](#team-management-endpoints)
2. [Invitation Flow](#invitation-flow)
3. [Multi-Account Support](#multi-account-support)
4. [Email Notifications](#email-notifications)
5. [Cache Invalidation](#cache-invalidation)
6. [Testing](#testing)

---

## Team Management Endpoints

### Task 3.1: Implement Invite Team Member Endpoint

**Priority**: High

**Estimated Time**: 3 hours

**Dependencies**: Phase 2 complete

**File Location**: `src/api/v1/admin/team.py`

**Description**: Create endpoint for inviting team members with role assignment.

**Requirements**:

**Router**: `/admin/accounts/{account_id}/team` (tags: ["team"])

**Request Schema: InviteTeamMemberRequest**
- email: EmailStr (required)
- account_role: UserRole enum (role to assign on acceptance)

**Response Schema: InvitationResponse**
- invitation_id: UUID
- email: str
- account_role: UserRole
- invitation_token: str (secure token)
- expires_at: datetime
- status: InvitationStatus

**Endpoint: POST /invite**
- Auth: Depends(PermissionChecker("account.team_manage")) - Owner only
- Parameters: account_id (path), request body, current_user, db
- Returns: InvitationResponse (200)
- Errors: 400 if duplicate invitation or already member

**Algorithm**:
1. Log invitation request
2. Check if email is already a member (AccountUserRepository.is_member)
   - If member → raise HTTPException 400 "already a member"
3. Check for existing pending invitation (UserInvitationRepository.get_for_email)
   - If pending invitation exists for this account → raise HTTPException 400 "already has pending invitation"
4. Generate secure token (secrets.token_urlsafe(32) - 256 bits)
5. Set expiration (7 days from now)
6. Create invitation record (UserInvitationRepository.create)
7. Send invitation email (try/except, log failure but continue)
8. Log success
9. Return invitation details

**Validation Steps**:

1. Test successful invitation creation
2. Test duplicate invitation rejection
3. Test inviting existing member rejection
4. Test invitation email sent
5. Test secure token generation (32 bytes)
6. Test expiration date (7 days from now)
7. Test rate limiting (max 10 invitations per hour per account)

---

### Task 3.2: Implement List Team Members Endpoint

**Priority**: High

**Estimated Time**: 2.5 hours

**Dependencies**: Phase 2 complete

**File Location**: `src/api/v1/admin/team.py` (add to existing)

**Description**: List all team members with their roles and status.

**Requirements**:

**Response Schema: TeamMemberResponse**
- user_id: UUID
- email: str
- name: Optional[str]
- account_role: Optional[UserRole] (role on account resource)
- status: str (active, deactivated)
- added_at: datetime
- last_active: Optional[datetime]
- resource_roles: List[dict] (empty for V1, future project/agent roles)

**Response Schema: TeamMembersListResponse**
- members: List[TeamMemberResponse]
- total: int

**Endpoint: GET /**
- Auth: Depends(PermissionChecker("account.read")) - Owner, Manager, Viewer
- Parameters: account_id (path), role (query, optional), status (query, optional), search (query, optional)
- Returns: TeamMembersListResponse (200)

**Algorithm**:
1. Log query parameters
2. Build query joining User, AccountUser, ResourceRoleAssignment tables
   - Join User with AccountUser on user_id
   - Left join ResourceRoleAssignment for account-level role (resource_type='account')
   - Filter by account_id
3. Apply filters:
   - status: Filter AccountUser.status (default: 'active' only)
   - role: Filter ResourceRoleAssignment.role
   - search: Filter User.email or User.name (case-insensitive ILIKE)
4. Execute query
5. Format results into TeamMemberResponse objects
6. Return TeamMembersListResponse with members and total count

**Validation Steps**:

1. Test listing all members
2. Test role filter (only Owners, only Managers, etc.)
3. Test status filter (active, deactivated)
4. Test search by email
5. Test search by name
6. Test empty results
7. Test performance with 100+ members (<500ms)

---

### Task 3.3: Implement Update Team Member Role Endpoint

**Priority**: High

**Estimated Time**: 2.5 hours

**Dependencies**: Task 3.2

**File Location**: `src/api/v1/admin/team.py` (add to existing)

**Description**: Update a team member's account-level role.

**Requirements**:

**Request Schema: UpdateTeamMemberRequest**
- account_role: UserRole (new role)

**Response Schema: UpdateTeamMemberResponse**
- user_id: UUID
- account_role: UserRole
- updated_at: datetime

**Endpoint: PATCH /{user_id}**
- Auth: Depends(PermissionChecker("account.team_manage")) - Owner only
- Parameters: account_id (path), user_id (path), request body, current_user, db
- Returns: UpdateTeamMemberResponse (200)
- Errors: 404 if user not member, 400 if removing last owner

**Algorithm**:
1. Log role update request
2. Verify user is member (AccountUserRepository.is_member)
   - If not member → raise HTTPException 404
3. Get current role (ResourceRoleAssignmentRepository.get_role_for_resource)
4. Check if removing last owner:
   - If current_role == OWNER and new_role != OWNER:
     - Count owners (count_owners_for_account)
     - If count <= 1 → raise HTTPException 400 "cannot remove last owner"
5. Update or create role assignment:
   - If current_role exists → update assignment.role, set updated_at
   - Else → create new assignment via assign_role()
6. Commit transaction
7. Invalidate cache (clear_user_resource_role_cache for user_id)
8. Log success
9. Return updated assignment

**Validation Steps**:

1. Test successful role update (Manager → Viewer)
2. Test preventing last owner removal
3. Test creating role for member without role
4. Test cache invalidation after update
5. Test non-member returns 404
6. Test self role change (Owner can change their own role if not last owner)

---

### Task 3.4: Implement Remove Team Member Endpoint

**Priority**: High

**Estimated Time**: 2.5 hours

**Dependencies**: Task 3.3

**File Location**: `src/api/v1/admin/team.py` (add to existing)

**Description**: Remove a team member from the account (deactivate membership and remove all role assignments).

**Requirements**:

**Endpoint: DELETE /{user_id}**
- Auth: Depends(PermissionChecker("account.team_manage")) - Owner only
- Parameters: account_id (path), user_id (path), current_user, db
- Returns: 204 No Content
- Errors: 404 if user not member, 400 if removing last owner

**Algorithm**:
1. Log removal request
2. Get account user (AccountUserRepository.get_by_user_and_account)
   - If not found → raise HTTPException 404
3. Get current role (ResourceRoleAssignmentRepository.get_role_for_resource)
4. Check if removing last owner:
   - If current_role == OWNER:
     - Count owners (count_owners_for_account)
     - If count <= 1 → raise HTTPException 400 "cannot remove last owner"
5. Deactivate membership (account_user.status = DEACTIVATED, updated_at = now)
6. Remove all role assignments (remove_all_assignments_for_user, returns deleted count)
7. Commit transaction
8. Log success with deleted count
9. Invalidate cache (clear_user_resource_role_cache for user_id)
10. Return 204 No Content

**Validation Steps**:

1. Test successful removal
2. Test preventing last owner removal
3. Test all role assignments deleted
4. Test membership status set to deactivated
5. Test cache invalidation
6. Test non-member returns 404
7. Test removed user cannot access account after removal

---

## Invitation Flow

### Task 3.5: Implement Get Invitation Details Endpoint

**Priority**: High

**Estimated Time**: 1.5 hours

**Dependencies**: Task 3.1

**File Location**: `src/api/v1/invitations.py`

**Description**: Endpoint to view invitation details before accepting (public, no auth).

**Requirements**:

**Router**: `/invitations` (tags: ["invitations"])

**Response Schema: InvitationDetailsResponse**
- account_name: str
- invited_by: str (name or email of inviter)
- role: UserRole
- expires_at: datetime
- status: InvitationStatus

**Endpoint: GET /{token}**
- Auth: None (public endpoint)
- Parameters: token (path), db
- Returns: InvitationDetailsResponse (200)
- Errors: 404 if not found, 400 if expired or not pending

**Algorithm**:
1. Get invitation by token (UserInvitationRepository.get_by_token)
   - If not found → raise HTTPException 404 "not found or expired"
2. Check status:
   - If status != PENDING → raise HTTPException 400 with status
3. Check expiration:
   - If expires_at < now → mark_as_expired(), raise HTTPException 400 "expired"
4. Load account and inviter details from database
5. Return InvitationDetailsResponse (no sensitive info like full token)

**Validation Steps**:

1. Test valid invitation returns details
2. Test expired invitation marked as expired
3. Test accepted invitation returns 400
4. Test invalid token returns 404
5. Test no sensitive information exposed

---

### Task 3.6: Implement Accept Invitation Endpoint

**Priority**: High

**Estimated Time**: 3 hours

**Dependencies**: Task 3.5

**File Location**: `src/api/v1/invitations.py` (add to existing)

**Description**: Accept an invitation and create account membership + role assignment.

**Requirements**:

**Request Schema: AcceptInvitationRequest**
- invitation_token: str

**Response Schema: AcceptInvitationResponse**
- account_id: UUID
- account_name: str
- account_role: UserRole
- message: str

**Endpoint: POST /accept**
- Auth: Depends(get_current_user) - requires authenticated user
- Parameters: request body, current_user, db
- Returns: AcceptInvitationResponse (200)
- Errors: 404 if not found, 400 if expired/email mismatch/already member

**Algorithm**:
1. Log acceptance request
2. Get invitation by token (UserInvitationRepository.get_by_token)
   - If not found → raise HTTPException 404
3. Validate invitation:
   - If status != PENDING → raise HTTPException 400
   - If expired → mark_as_expired(), raise HTTPException 400
   - If email != current_user.email → raise HTTPException 400 "different email"
4. Check if already member (AccountUserRepository.is_member)
   - If member → raise HTTPException 400 "already a member"
5. Create account membership (AccountUserRepository.create with status=ACTIVE)
6. Assign role on account (ResourceRoleAssignmentRepository.assign_role with resource_type='account')
7. Mark invitation as accepted (invitation_repo.mark_as_accepted)
8. Get account details
9. Log success
10. Return AcceptInvitationResponse

**Validation Steps**:

1. Test successful invitation acceptance
2. Test creates account_users entry
3. Test creates resource_role_assignments entry with resource_type='account'
4. Test marks invitation as accepted
5. Test email mismatch rejection
6. Test expired invitation rejection
7. Test duplicate acceptance (already a member)
8. Test user can now access account

---

### Task 3.7: Implement Resend Invitation Endpoint

**Priority**: Medium

**Estimated Time**: 1.5 hours

**Dependencies**: Task 3.1

**File Location**: `src/api/v1/admin/team.py` (add to existing)

**Description**: Resend invitation email for pending invitations.

**Requirements**:

**Endpoint: POST /invitations/{invitation_id}/resend**
- Auth: Depends(PermissionChecker("account.team_manage")) - Owner only
- Parameters: account_id (path), invitation_id (path), current_user, db
- Returns: {"message": "success"} (200)
- Errors: 404 if not found, 400 if not pending, 500 if email fails

**Algorithm**:
1. Get invitation by ID (UserInvitationRepository.get_by_id)
   - If not found or account_id mismatch → raise HTTPException 404
2. Check status:
   - If status != PENDING → raise HTTPException 400
3. Load account details
4. Send invitation email (send_invitation_email with existing token)
   - Wrap in try/except
   - If error → raise HTTPException 500
5. Log success
6. Return success message

**Validation Steps**:

1. Test successful resend
2. Test email sent with same token
3. Test cannot resend accepted invitation
4. Test cannot resend expired invitation
5. Test 404 for non-existent invitation

---

## Multi-Account Support

### Task 3.8: Implement List User Accounts Endpoint

**Priority**: High

**Estimated Time**: 2 hours

**Dependencies**: Phase 2 complete

**File Location**: `src/api/v1/users.py`

**Description**: List all accounts a user has access to (for account switcher UI).

**Requirements**:

**Router**: `/users/me` (tags: ["users"])

**Response Schema: UserAccountResponse**
- account_id: UUID
- account_name: str
- role: Optional[UserRole] (account-level role, may be None)
- last_accessed: Optional[datetime]

**Response Schema: UserAccountsListResponse**
- accounts: List[UserAccountResponse]

**Endpoint: GET /accounts**
- Auth: Depends(get_current_user)
- Parameters: current_user, db
- Returns: UserAccountsListResponse (200)

**Algorithm**:
1. Query Account joined with AccountUser and ResourceRoleAssignment
   - Join AccountUser on account_id
   - Left join ResourceRoleAssignment for account-level role (resource_type='account')
   - Filter by current_user.id and status='active'
2. Format results into UserAccountResponse objects
3. Log account count
4. Return UserAccountsListResponse

**Validation Steps**:

1. Test user with multiple accounts
2. Test user with single account
3. Test user with no accounts
4. Test role correctly shown for each account
5. Test only active memberships returned

---

### Task 3.9: Implement Switch Account Endpoint

**Priority**: Medium

**Estimated Time**: 1.5 hours

**Dependencies**: Task 3.8

**File Location**: `src/api/v1/users.py` (add to existing)

**Description**: Switch active account context (for frontend session management).

**Requirements**:

**Request Schema: SwitchAccountRequest**
- account_id: UUID

**Response Schema: SwitchAccountResponse**
- account_id: UUID
- account_name: str
- role: Optional[UserRole]

**Endpoint: POST /switch-account**
- Auth: Depends(get_current_user)
- Parameters: request body, current_user, db
- Returns: SwitchAccountResponse (200)
- Errors: 403 if no access, 404 if account not found

**Algorithm**:
1. Log switch request
2. Verify user is member (AccountUserRepository.is_member)
   - If not member → raise HTTPException 403
3. Get user's role on account (ResourceRoleAssignmentRepository.get_role_for_resource)
4. Get account details
   - If not found → raise HTTPException 404
5. Log success
6. Return SwitchAccountResponse

**Note**: Backend is stateless, this is for frontend state management only

**Validation Steps**:

1. Test successful switch
2. Test switch to account without access (403)
3. Test switch to non-existent account (404)
4. Test role returned correctly

---

## Email Notifications

### Task 3.10: Create Email Service

**Priority**: High

**Estimated Time**: 3 hours

**Dependencies**: None (can be done in parallel)

**File Location**: `src/services/email.py`

**Description**: Email service for sending invitation and notification emails.

**Requirements**:

**Class: EmailService**
- Constructor __init__():
  - Load SMTP settings from config (host, port, user, password, from_email, from_name)
- Method send_email(to_email, subject, html_body, text_body=None) → bool:
  - Purpose: Send email via SMTP
  - Algorithm:
    1. Create MIMEMultipart message with subject, from, to
    2. Attach text_body (if provided) and html_body
    3. Connect to SMTP server, starttls, login
    4. Send message
    5. Log success/failure
    6. Return boolean
  - Error Handling: Catch all exceptions, log, return False

**Global Singleton**: email_service = EmailService()

**Function: send_invitation_email(to_email, invitation_token, inviter_name, account_name, role) → bool**
- Purpose: Send team invitation email
- Email Content:
  - Subject: "{inviter_name} invited you to join {account_name} on Palona"
  - HTML body: Invitation greeting, role description, accept button with invitation_url, expiration notice (7 days), plaintext link fallback
  - Text body: Plain text version with same content
  - Invitation URL: {WEB_APP_URL}/invitations/accept?token={invitation_token}
- Role descriptions (include in HTML as bullet list):
  - Owner: Full access, manage team, billing, create/edit/delete all
  - Manager: Create/edit/delete projects/agents, approve plans, view account (read-only), export data
  - Viewer: View all, export data, no editing/creation
- Returns: Boolean from email_service.send_email()

**Function: send_role_changed_email(to_email, user_name, account_name, old_role, new_role, changed_by) → bool**
- Purpose: Notify user when role changes
- Email Content:
  - Subject: "Your role in {account_name} has been updated"
  - HTML body: Greeting, role change notice, old→new role, new role description, view account button
  - Text body: Plain text version
- Returns: Boolean from email_service.send_email()

**Function: send_removed_from_account_email(to_email, user_name, account_name, removed_by) → bool**
- Purpose: Notify user when removed from account
- Email Content:
  - Subject: "You've been removed from {account_name}"
  - HTML body: Greeting, removal notice, contact owner message
  - Text body: Plain text version
- Returns: Boolean from email_service.send_email()

**Configuration** (`src/config.py`):
- Add environment variables: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, FROM_EMAIL, FROM_NAME, WEB_APP_URL
- Defaults: localhost:587, noreply@palona.ai, Palona, http://localhost:8501

**Validation Steps**:

1. Test invitation email sent with correct formatting
2. Test role changed email sent
3. Test removed from account email sent
4. Test email formatting (HTML and text versions)
5. Test link generation
6. Test SMTP error handling

---

## Cache Invalidation

### Task 3.11: Implement Cache Invalidation Helpers

**Priority**: High

**Estimated Time**: 1.5 hours

**Dependencies**: Phase 2 cache module

**File Location**: `src/auth/rbac/cache.py` (add to existing)

**Description**: Add granular cache invalidation functions for role changes.

**Requirements**:

**Function: clear_user_resource_role_cache(user_id=None, account_id=None, resource_type=None, resource_id=None) → None**
- Purpose: Clear user resource role cache (filtered or all)
- Algorithm:
  1. Acquire user_resource_role_lock
  2. If any filter provided:
     - Iterate through cache keys (structure: (user_id, account_id) for V1)
     - Match keys against filters
     - Collect matching keys to delete
     - Delete matching keys
     - Log count of deleted entries
  3. If no filters → clear entire cache, log "cleared entire cache"
- Note: V1 uses simple in-memory filtering. V2 with Redis will use pattern matching.

**Function: clear_role_permissions_cache(role=None) → None**
- Purpose: Clear role permissions cache
- Algorithm:
  1. Acquire role_permissions_lock
  2. If role provided:
     - Get hashkey for role.value
     - Delete from cache if exists
     - Log cleared role
  3. Else → clear entire cache, log "cleared entire cache"
- Note: Called when role_permissions table changes (admin operation)

**Validation Steps**:

1. Test clearing cache for specific user
2. Test clearing cache for specific account
3. Test clearing entire cache
4. Test thread safety (concurrent cache operations)

---

## Testing

### Task 3.12: Unit Tests for Team Management

**Priority**: High

**Estimated Time**: 4 hours

**Dependencies**: Tasks 3.1-3.4

**File Location**: `tests/unit/api/test_team_management.py`

**Requirements**:

**Test Class: TestInviteTeamMember**
- test_successful_invitation:
  - Setup: Owner auth, sample account
  - Action: POST /team/invite with email and role
  - Verify: 200 status, invitation created with email, role, token, status=pending
- test_duplicate_invitation_rejected:
  - Setup: Existing pending invitation
  - Action: POST /team/invite with same email
  - Verify: 400 status, "already has pending invitation" message
- test_invite_existing_member_rejected:
  - Setup: Existing active member
  - Action: POST /team/invite with member's email
  - Verify: 400 status, "already a member" message
- test_manager_cannot_invite:
  - Setup: Manager auth
  - Action: POST /team/invite
  - Verify: 403 status

**Test Class: TestListTeamMembers**
- test_list_all_members:
  - Action: GET /team
  - Verify: 200 status, members list not empty
- test_filter_by_role:
  - Action: GET /team?role=owner
  - Verify: All returned members have role=owner
- test_search_by_email:
  - Action: GET /team?search={email}
  - Verify: Results contain matching member

**Test Class: TestUpdateTeamMemberRole**
- test_successful_role_update:
  - Action: PATCH /team/{user_id} with new role
  - Verify: 200 status, role updated
- test_prevent_last_owner_removal:
  - Action: PATCH /team/{owner_id} changing from owner
  - Verify: 400 status, "last owner" message
- test_manager_cannot_update_roles:
  - Setup: Manager auth
  - Action: PATCH /team/{user_id}
  - Verify: 403 status

**Test Class: TestRemoveTeamMember**
- test_successful_removal:
  - Action: DELETE /team/{user_id}
  - Verify: 204 status, user cannot access account afterward (403)
- test_prevent_last_owner_removal:
  - Action: DELETE /team/{owner_id}
  - Verify: 400 status, "last owner" message

---

### Task 3.13: Integration Tests for Invitation Flow

**Priority**: High

**Estimated Time**: 3 hours

**Dependencies**: Tasks 3.5-3.6

**File Location**: `tests/integration/api/test_invitation_flow.py`

**Requirements**:

**Test Class: TestInvitationFlow**
- test_complete_invitation_flow:
  - Setup: Owner creates invitation
  - Step 1: POST /team/invite → verify 200, get token
  - Step 2: GET /invitations/{token} → verify 200, account name, role
  - Step 3: New user POST /invitations/accept → verify 200, account_role returned
  - Step 4: New user GET /accounts/{id} → verify 200 (has access)
  - Step 5: New user POST /projects → verify 200 (has permissions)
- test_expired_invitation:
  - Setup: Expired invitation
  - Action: GET /invitations/{token}
  - Verify: 400 status, "expired" message
- test_email_mismatch_rejection:
  - Setup: Invitation for email A, different user email B
  - Action: POST /invitations/accept as user B
  - Verify: 400 status, "different email" message

---

### Task 3.14: End-to-End Tests

**Priority**: Medium

**Estimated Time**: 3 hours

**Dependencies**: All Phase 3 tasks

**File Location**: `tests/e2e/test_team_management_flow.py`

**Test Scenarios**:

1. Owner invites multiple team members with different roles
2. Team members accept invitations and access account
3. Owner changes team member roles
4. Team members lose/gain permissions based on role changes
5. Owner removes team member, user loses access
6. Multi-account scenario: user belongs to multiple accounts

---

## Validation Checklist

Before marking Phase 3 complete, ensure:

- [ ] All team management endpoints implemented
- [ ] Invitation flow works end-to-end
- [ ] Email notifications sent correctly
- [ ] Multi-account support working
- [ ] Cache invalidation after role changes
- [ ] Last owner protection enforced
- [ ] Unit tests passing (>80% coverage)
- [ ] Integration tests passing
- [ ] End-to-end tests passing
- [ ] Email templates formatted correctly (HTML + text)
- [ ] Security: Invitation tokens secure (32 bytes)
- [ ] Security: Email validation enforced
- [ ] Security: Rate limiting on invitations

---

## Estimated Timeline

| Category | Tasks | Estimated Time |
|----------|-------|----------------|
| Team Management Endpoints | 3.1 - 3.4 | 10.5 hours |
| Invitation Flow | 3.5 - 3.7 | 6 hours |
| Multi-Account Support | 3.8 - 3.9 | 3.5 hours |
| Email Notifications | 3.10 | 3 hours |
| Cache Invalidation | 3.11 | 1.5 hours |
| Testing | 3.12 - 3.14 | 10 hours |
| **Total** | | **34.5 hours** |

*Note: Estimates are for development time only. Add 20-30% buffer for code review, bug fixes, and iteration.*

---

## Dependencies Summary

**Critical Path**:

1. Team management endpoints (3.1-3.4)
2. Invitation flow (3.5-3.6) depends on team management
3. Email service (3.10) can be done in parallel
4. Tests depend on implementation

**Parallelizable Work**:

- Email service (3.10) can be done early
- Multi-account endpoints (3.8-3.9) can be done in parallel with team management
- Different endpoint implementations can be parallelized

---

## Next Steps After Phase 3

Once Phase 3 is complete, proceed to:

- **Phase 4**: Frontend Implementation (Weeks 7-9)
  - Team management UI
  - Invitation acceptance flow
  - Account switcher
  - Role-based UI rendering

- **Phase 5**: Testing & Launch (Weeks 10-12)
  - Security audit
  - Performance testing
  - UAT with beta customers
  - Gradual rollout

---

## Post-Launch V2 Features

After successful V1 launch, consider:

- **Project-level role overrides** - Assign different roles per project
- **Agent-level role overrides** - Restrict access to specific agents
- **Custom roles** - Create account-specific roles with custom permissions
- **Permission UI** - Expose permission management interface
- **Audit logging** - Comprehensive audit trail for compliance
- **SSO/SAML** - Enterprise single sign-on integration
