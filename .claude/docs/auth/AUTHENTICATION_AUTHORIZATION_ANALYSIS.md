# AUTH SYSTEM REFERENCE - PALONA

## METADATA
- System: pal-mono
- Auth Method: AWS Cognito JWT (RS256)
- Roles: Admin, AccountManager
- Protected Routes: ~161 admin endpoints
- Public Routes: chat, webhooks, integrations

## ARCHITECTURE SUMMARY
```
Admin APIs: Cognito JWT + RBAC (2 roles)
Public APIs: No auth (chat, integrations)
Authorization: Account-level isolation
Multi-account: Supported via custom:account_names
```

---

## 1. AUTHENTICATION IMPLEMENTATION

### 1.1 Cognito JWT Authentication

**FILES:**
- `api/routes/admin/_auth.py` - Core auth (authenticate_user, JWT verification)
- `api/routes/admin/_utils.py` - UserContext, UserRole enums
- `api/routes/admin/__init__.py` - Protected endpoints

**FLOW:**
```
Request → authenticate_user() → Extract Auth Header → Verify JWT
  ↓
Try pools: 1) Admin Console, 2) Manage App (fallback)
  ↓
JWKS validation: RS256 signature + audience + expiration
  ↓
Valid → Extract claims → Create UserContext → Return
Invalid → 401 Unauthorized
```

**JWT CLAIMS:**
```json
{
  "sub": "uuid",
  "cognito:username": "uuid",
  "cognito:groups": ["account-admins"],
  "custom:account_name": "account-name",
  "custom:account_names": "name1,name2,name3",
  "email": "user@domain.com",
  "name": "Display Name",
  "exp": 1690003600,
  "aud": "client-id",
  "token_use": "id"
}
```

**VALIDATION STEPS:**
1. Extract `kid` from header
2. Fetch JWKS from Cognito
3. Verify RS256 signature
4. Check: exp, aud, token_use="id"
5. Raise ValueError if invalid

**ENV VARS:**
```
AWS_REGION
AWS_ADMIN_CONSOLE_USER_POOL_ID
AWS_ADMIN_CONSOLE_APP_CLIENT_ID
AWS_MANAGE_APP_USER_POOL_ID (optional)
AWS_MANAGE_APP_APP_CLIENT_ID (optional)
```

---

## 2. USER MODEL

### 2.1 UserContext (Runtime)

**FILE:** `api/routes/admin/_utils.py:21-28`
```python
@dataclass
class UserContext:
    username: str              # Cognito UUID
    email: str
    groups: List[str]          # cognito:groups
    display_name: str
    account_names: List[str]   # Parsed from custom:account_name(s)
    role: UserRole             # Admin | AccountManager
```

**CREATED BY:** `_auth.py:280-329` authenticate_user()

### 2.2 Database Model

**FILE:** `db/tables/users.py:22-56`
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    account_id UUID REFERENCES accounts(id),
    raw_config JSONB DEFAULT '{}',
    channel_identifiers TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);
```

**NOTE:** Primary user data in Cognito, minimal local tracking

### 2.3 Roles

**FILE:** `_auth.py:332-337` get_user_role()
```
Admin: @proactiveailab.com, @palona.ai
AccountManager: All other domains
```

---

## 3. AUTHORIZATION

### 3.1 Functions

**FILE:** `_auth.py:340-366, 369-375`

**authorize_user_account(context, account_name):**
```python
# Grants access if:
# - account_name in context.account_names, OR
# - context.role == Admin
# Else: 403 Forbidden
```

**authorize_admin(context):**
```python
# Grants access if: context.role == Admin
# Else: 403 Forbidden
```

**MATRIX:**
```
Admin + Any Account → Allow
AccountManager + account_name in account_names → Allow
AccountManager + account_name NOT in account_names → 403
```

### 3.2 Endpoint Patterns

**PATTERN 1: Account-Scoped**
```python
context: UserContext = Depends(authenticate_user)
authorize_user_account(context, account_name)
```

**PATTERN 2: Admin-Only**
```python
context: UserContext = Depends(authenticate_user)
authorize_admin(context)
```

**PATTERN 3: Dual-Role**
```python
context: UserContext = Depends(authenticate_user)
if context.role not in [UserRole.Admin, UserRole.AccountManager]:
    raise HTTPException(403)
```

### 3.3 Protected Resources

**TOTAL:** ~161 admin endpoints

**BREAKDOWN:** Accounts(11), Integrations(13), Agents(6), Campaigns(3), Conversations(4), Feedback(5), FAQs(4), Projects(7), Phone Numbers(4), Users(4), KB(6), ChangeLogs(2), Leads(5), Onboarding(5), Plans(5), Subscriptions(16), Prompts(6), VoiceConfigs(5), Affiliate(5), Others(Email, Analytics)

---

## 4. DATABASE SCHEMA

### 4.1 Account

**FILE:** `db/tables/accounts.py:72-154`
```python
class Account:
    id: UUID (PK)
    name: str (unique)
    display_name: str
    status: AccountStatus  # pending|initializing|initialized|integration_complete|evaluation_complete|active|disabled|suspended|pending_closure|closed|deleted
    contract_signed: bool
    terms_accepted: bool
    segment: BusinessSegment  # smb|mm|ent
    tier: TargetTier
    # Relations: projects[], agents[], users[], subscriptions[]
```

### 4.2 Project

**FILE:** `db/tables/projects.py:22-74`
```python
class Project:
    id: UUID (PK)
    account_id: UUID (FK)
    agent_id: UUID (FK)
    name: str
    raw_config: JSONB
    channel_identifiers: TEXT[]
    store_hours: str
    address: str
    product_info: str
    service_instruction: str
```

### 4.3 Relationships

```
Account 1:N Users
Account 1:N Projects
Account 1:N Agents
Account 1:N Subscriptions
Project N:1 Account, N:1 Agent
```

---

## 5. PUBLIC (NO AUTH) APIs

### 5.1 Chat
**FILE:** `api/routes/chat/chat.py:44-160`
```
POST /v1/chat
Auth: None
Request: {message, project_id, conversation_id, channel, user_id, stream, relay_response}
```

### 5.2 Webhooks
```
DELETE /v1/instagram/deauthorize/{ig_user_id}
GET /v1/accounts/{account_name}/integrations/{integration_id}/locations
```
**SECURITY:** Some validate signatures (e.g., Instagram), others use external credentials

### 5.3 Operations
```
GET/POST /v1/operations/checkpoints
GET/POST /v1/operations/checklists
```

---

## 6. SECURITY

### 6.1 Middleware

**FILE:** `api/main.py:45-52`
```python
CORSMiddleware:
  allow_origins: configured list
  allow_origin_regex: https://.*-proactiveailab\.vercel\.app
  allow_credentials: True
  allow_methods: ["*"]
  allow_headers: ["*"]
```

**MISSING:** Rate limiting, request signing, HTTPS enforcement, security headers (HSTS, CSP), audit logging, IP whitelisting

### 6.2 HTTP Status Codes
```
401 - Missing/invalid token
403 - Insufficient permissions
404 - Not found
409 - Conflict
422 - Invalid request data
500 - Server error
```

### 6.3 Guest Context

**FILE:** `api/routes/admin/_utils.py:121-140`
```python
create_guest_context(account_name, user_email) → UserContext
# Used for: signup flow, pre-auth account creation
```

---

## 7. USER MANAGEMENT

### 7.1 Create User (Admin)
```
PUT /v1/admin/accounts/{account_name}/users
Auth: Admin only
Flow: Authenticate → Authorize → Cognito AdminCreateUser → Set attributes → Add to group
Cognito: custom:account_name, custom:account_names, cognito:groups:["{account_name}-admins"]
```

### 7.2 Update Account Access (Admin)
```
PATCH /v1/admin/users/{user_email}/account_names
Auth: Admin only
Body: {"account_names": ["name1", "name2"]}
Flow: Authenticate → Check Admin → Update custom:account_names in Cognito
```

### 7.3 List Users
```
GET /v1/admin/accounts/{account_name}/users
Auth: Account access or Admin
Backend: Cognito AdminListUsersInGroup("{account_name}-admins")
```

### 7.4 Delete User (Admin)
```
DELETE /v1/admin/accounts/{account_name}/users?email=...
Auth: Admin only
Flow: Authenticate → Authorize → Cognito AdminDeleteUser
Note: Local DB records preserved
```

---

## 8. SERVICE LAYER

### 8.1 Account Service

**FILE:** `services/account_service/__init__.py`
```python
get_account(session, account_name) → Optional[Account]
get_account_by_id(session, account_id) → Optional[Account]
mget_accounts(session, account_names) → List[Account]
create_account(session, context, account_name, params, lead_id, auto_commit)
update_account(session, context, account_name, params, expected_version)
delete_account(session, account_name, hard_delete, context)
filter_accounts_by_name(session, keyword) → List[Account]
```
**NOTE:** Context used for audit trail, soft delete supported

### 8.2 Admin Service

**FILE:** `services/admin_service/`
```python
list_account_users(account_name)
create_account_user(account_name, email, name)
delete_account_user(account_name, user_email)
get_user_account_names(user_email) → List[str]
update_user_account_names(user_email, account_names)
```
**COGNITO:** boto3 client, AdminCreateUser/AdminDeleteUser/AdminUpdateUserAttributes, group management

---

## 9. DATA FLOW: SIGNUP → USAGE

```
1. SIGNUP
POST /v1/admin/signup
  → create_guest_context()
  → account_service.create_account() [DB: status=initializing]
  → admin_service.create_account_user() [Cognito: user + group]
  → Send temp password email

2. LOGIN
Cognito login flow
  → Change password
  → Receive JWT (custom:account_name, cognito:groups)
  → Store token

3. API CALLS
Authorization: Bearer <JWT>
  → authenticate_user() [validate JWT]
  → Extract UserContext
  → authorize_user_account() or authorize_admin()
  → Execute or 403
```

---

## 10. SECURITY ASSESSMENT

### STRENGTHS
- RS256 JWT (Cognito), Multi-pool support, Account isolation, RBAC (2 roles), Soft deletes, Multi-account support, Cognito groups, Token expiration, Secure user creation

### GAPS
- No API keys, Limited roles (2), Email-based role assignment, No auth on chat API, No session tracking, Limited audit logging, No rate limiting, Permissive CORS

### ATTACK VECTORS
- JWT theft, Account enumeration, Multi-account exploit, Admin impersonation, Public API abuse, Webhook replay

---

## 11. DEVELOPER GUIDE

### Protected Endpoint (Account-Scoped)
```python
from api.routes.admin._auth import authenticate_user, authorize_user_account
@admin_router.get("/accounts/{account_name}/resource")
def get_resource(account_name: str, context: UserContext = Depends(authenticate_user)):
    authorize_user_account(context, account_name)
    return do_work()
```

### Admin-Only Endpoint
```python
from api.routes.admin._auth import authorize_admin
@admin_router.patch("/admin-resource")
def update(context: UserContext = Depends(authenticate_user)):
    authorize_admin(context)
    return do_work()
```

### Public Endpoint
```python
@router.post("/public")
async def public_op(request: Request):
    return do_work()
```

---

## 12. ENHANCEMENT ROADMAP

**SHORT-TERM:** API keys, Rate limiting, Audit logging, HTTPS headers, Session tracking
**MEDIUM-TERM:** Granular permissions, OAuth scopes, IP whitelisting, Audit DB, Access expiration
**LONG-TERM:** Full RBAC/ABAC, Permission caching, Threat detection, MFA, SSO (SAML/OIDC)

---

## 13. FILE REFERENCE

**AUTH:**
- `api/routes/admin/_auth.py` - Core auth, JWT validation
- `api/routes/admin/_utils.py` - UserContext, UserRole
- `api/routes/admin/__init__.py` - Protected endpoints
- `api/main.py` - FastAPI app, CORS

**DB:**
- `db/tables/accounts.py` - Account model
- `db/tables/users.py` - User model
- `db/tables/projects.py` - Project model

**SERVICES:**
- `services/account_service/` - Account CRUD
- `services/admin_service/` - Cognito user management

**PUBLIC:**
- `api/routes/chat/chat.py` - Chat API (no auth)
- `api/routes/operation/` - Operations
- `api/routes/asset/` - Assets

---

## 14. TESTING

**Get Token:**
```bash
aws cognito-idp initiate-auth \
  --client-id <ID> --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=user@x.com,PASSWORD=pass
```

**Test Protected:**
```bash
curl -H "Authorization: Bearer <TOKEN>" \
  http://localhost:8000/v1/admin/accounts/acme-corp
```

**Test 403:**
```bash
# Wrong account → 403
curl -H "Authorization: Bearer <TOKEN>" \
  http://localhost:8000/v1/admin/accounts/unauthorized-account

# Non-admin → 403
curl -X PATCH -H "Authorization: Bearer <TOKEN>" \
  http://localhost:8000/v1/admin/users/test@x.com/account_names
```

---

## SUMMARY

**SYSTEM:** Cognito JWT auth + account-level RBAC (2 roles)
**USERS:** Cognito primary, PostgreSQL secondary
**AUTH:** Admin APIs protected, Public APIs (chat/webhooks) unprotected
**MULTI-ACCOUNT:** Supported via custom:account_names
**USE CASE:** B2B SaaS with admin/customer separation
