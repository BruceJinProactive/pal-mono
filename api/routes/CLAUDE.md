# api/routes/

## CRITICAL RULES

### ALWAYS
1. Use `context: UserContext = Depends(authenticate_user)` for authentication
2. Use `require_account_permission()` or `require_project_permission()` dependencies for authorization
3. Use `session: Session = Depends(db.get_db)` for sync DB operations
4. Use `session: AsyncSession = Depends(db.get_db_async)` for async DB operations
5. Raise `HTTPException` with `headers={"Content-Type": "application/json"}`
6. Include error response models in route decorator `responses={400: {"model": ErrorResponse}}`
7. Add docstrings to route handlers (becomes OpenAPI description)
8. Separate route handlers (in `__init__.py`) from implementation (in `_<resource>.py`)
9. Return typed responses with `-> ResourceModel` annotation
10. Use `status.HTTP_*` constants for status codes

### NEVER
1. Manually manage database sessions with `next(db.get_db())` - use `Depends(db.get_db)` instead
2. Mix sync and async inconsistently - match async endpoint with `AsyncSession = Depends(db.get_db_async)`, sync endpoint with `Session = Depends(db.get_db)`
3. Skip authorization checks after authentication - always use `require_account_permission()` or `require_project_permission()` dependencies
4. Use manual HTML escaping with `html.escape()` - use Pydantic `Field` validation and SQLAlchemy parameterization instead
5. Create monolithic `__init__.py` files over 500 lines - split into separate `_<resource>.py` implementation files
6. Use hardcoded status codes like `404` - use `status.HTTP_404_NOT_FOUND` constants instead
7. Use inconsistent status codes for same operations - standardize on `201` for creation, `200` for updates, `204` for deletion

## DIRECTORY STRUCTURE

```
api/routes/
├── __init__.py
├── capabilities.py       # Capability-related routes
├── endpoints.py          # Centralized endpoint path constants (ALWAYS use)
├── v1_router.py         # Root router that aggregates all domain routers
├── status.py            # Health check endpoints
├── utils.py             # Cross-domain shared utilities
├── internal/            # Internal routes (not exposed via v1)
│   ├── __init__.py
│   ├── _implementation.py
│   └── <resource>.py
└── <domain>/            # Domain-specific routes (admin, chat, asset, etc.)
    ├── __init__.py         # Router definition + route decorators
    ├── _implementation.py  # Generic business logic
    ├── _<resource>.py      # Resource-specific logic (e.g., _account.py)
    ├── _auth.py           # Authentication/authorization (if domain-specific)
    ├── _utils.py          # Domain-specific utilities
    └── _builder.py        # Response builders (DB model → API schema)
```

**RULE:** All implementation modules MUST start with underscore `_`

## FILE ORGANIZATION PATTERN

### `__init__.py` - Route Handler Layer
**PURPOSE:** Router definition, route decorators only
**CONTAINS:**
- Router instantiation
- Route decorators (`@router.get/post/patch/delete`)
- Parameter extraction
- Calls to implementation functions
- MUST NOT contain business logic

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import db
from api.routes.endpoints import endpoints
from api.routes.admin._auth import authenticate_user
from api.routes.admin._utils import UserContext
from api.schemas.admin.account import Account
from . import _account

admin_router = APIRouter(prefix=endpoints.ADMIN, tags=["Admin"])

@admin_router.get("/accounts/{account_name}")
def get_account(
    account_name: str,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Account:
    """Retrieve account details by account name."""
    return _account.get_account(account_name, context, session)
```

### `_<resource>.py` - Implementation Layer
**PURPOSE:** Business logic for specific resource
**CONTAINS:**
- Authorization checks
- Service layer calls
- Database operations
- Error handling
- Response building

```python
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from api.routes.admin._utils import UserContext
from api.routes.admin._builder import build_account
from services import account_service
from api.schemas.admin.account import Account

def get_account(
    account_name: str,
    context: UserContext,
    session: Session,
) -> Account:
    # Authorization handled by require_account_permission in route decorator

    # Business logic
    db_account = account_service.get_account(session, account_name)
    if not db_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_name} not found",
            headers={"Content-Type": "application/json"},
        )

    # Convert to response model
    return build_account(db_account)
```

### `_builder.py` - Response Builder Layer
**PURPOSE:** Convert DB models to API schemas
**CONTAINS:**
- Transformation functions
- Data aggregation
- Computed fields

```python
from api.schemas.admin.account import Account
from db.tables.account import Account as DbAccount

def build_account(db_account: DbAccount) -> Account:
    """Convert database Account model to API Account schema."""
    return Account(
        id=db_account.id,
        account_name=db_account.account_name,
        display_name=db_account.display_name,
        created_at=db_account.created_at,
        updated_at=db_account.updated_at,
    )
```

### `_auth.py` - Authentication Layer
**PURPOSE:** Authentication and user context
**CONTAINS:**
- Token validation
- User context creation
- FastAPI dependencies for auth

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from api.routes.admin._utils import UserContext

security = HTTPBearer()

def authenticate_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserContext:
    """Validate JWT token and return user context."""
    token = credentials.credentials
    # Token validation logic
    # Return UserContext object
```

### `_utils.py` - Domain Utilities Layer
**PURPOSE:** Domain-specific helper functions
**CONTAINS:**
- Authorization helpers
- Validation helpers
- Common error constructors

```python
from dataclasses import dataclass
from fastapi import HTTPException, status

@dataclass
class UserContext:
    username: str
    email: str
    groups: list[str]
    display_name: str
    role: UserRole

def authorize_admin(context: UserContext) -> None:
    """Verify user has admin role."""
    if context.role != UserRole.Admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
            headers={"Content-Type": "application/json"},
        )
```

## ROUTER AGGREGATION PATTERNS

### Pattern 1: Main Domain Router
```python
from fastapi import APIRouter
from api.routes.endpoints import endpoints

# REQUIRED: Use endpoints constants, not hardcoded strings
admin_router = APIRouter(prefix=endpoints.ADMIN, tags=["Admin"])
```

### Pattern 2: Sub-Router for Nested Features
```python
# In integrations/vapi/__init__.py
vapi_router = APIRouter(prefix="/vapi", tags=["Integrations"])

# In integrations/__init__.py
integrations_router = APIRouter(prefix=endpoints.INTEGRATIONS, tags=["Integrations"])
integrations_router.include_router(vapi_router)
integrations_router.include_router(toast_router)
integrations_router.include_router(square_router)
```

### Pattern 3: V1 Root Aggregation
```python
# In v1_router.py
from fastapi import APIRouter

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(admin_router)
v1_router.include_router(chat_router)
v1_router.include_router(asset_router)
v1_router.include_router(operation_router)
v1_router.include_router(integrations_router)
v1_router.include_router(status_router)
```

## AUTHENTICATION & AUTHORIZATION FLOW

### Required Pattern for All Protected Endpoints
```python
from api.routes.admin._auth import authenticate_user
from services.auth_service.dependencies import require_account_permission

@router.get("/accounts/{account_name}/resource")
def get_resource(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),  # Authentication + Authorization in one step
    session: Session = Depends(db.get_db),
):
    # Business logic - authorization already handled by dependency
```

### UserContext Structure
```python
@dataclass
class UserContext:
    username: str              # Cognito username
    email: str                 # User email
    groups: list[str]          # Cognito groups
    display_name: str          # Display name
    role: UserRole             # Admin or AccountManager
```

### Authorization Helpers
| Function | Purpose | When to Use |
|----------|---------|-------------|
| `require_account_permission(permission, auth_dep)` | Check account access via RBAC | All account-scoped endpoints |
| `require_project_permission(permission, auth_dep)` | Check project access via RBAC | All project-scoped endpoints |
| `authorize_admin(context)` | Restrict to Admin role | Admin-only operations |

## HTTP METHOD CONVENTIONS

| Method | Purpose | Path Pattern | Status Code | Idempotent |
|--------|---------|--------------|-------------|------------|
| `GET` | Retrieve resource(s) | `/resources` or `/resources/{id}` | 200 | Yes |
| `POST` | Create resource or trigger action | `/resources` | 201 (create), 200 (action), 202 (async) | No |
| `PUT` | Create resource with known ID | `/resources` or `/resources/{id}` | 201 | Yes |
| `PATCH` | Update resource partially | `/resources/{id}` | 200 | No |
| `DELETE` | Delete resource | `/resources/{id}` | 204 (no content) or 200 | Yes |

**RULE:** Use `status.HTTP_201_CREATED` for creation, `status.HTTP_200_OK` for updates

## REST ENDPOINT PATTERNS

### CRUD Operations
```python
# List resources
@router.get("/resources")
def list_resources(...) -> ListResourcesResponse:

# Get single resource
@router.get("/resources/{resource_id}")
def get_resource(resource_id: uuid.UUID, ...) -> Resource:

# Create resource
@router.post("/resources", status_code=status.HTTP_201_CREATED)
def create_resource(request: CreateResourceRequest, ...) -> Resource:

# Update resource
@router.patch("/resources/{resource_id}")
def update_resource(resource_id: uuid.UUID, request: UpdateResourceRequest, ...) -> Resource:

# Delete resource
@router.delete("/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resource(resource_id: uuid.UUID, ...):
```

### Nested Resources (Hierarchical Access)
```python
GET    /accounts/{account_name}/projects
GET    /accounts/{account_name}/projects/{project_id}
POST   /accounts/{account_name}/projects
PATCH  /projects/{project_id}  # Can use top-level for updates
DELETE /projects/{project_id}

GET    /projects/{project_id}/checklists
GET    /checklists/{checklist_id}/checkpoints
```

**RULE:** Use nested paths for listing/creating, top-level for get/update/delete

## REQUEST PARAMETER PATTERNS

### 1. JSON Body (Most Common)
```python
from api.schemas.admin.resource import CreateResourceRequest

@router.post("/resources")
async def create_resource(
    request: CreateResourceRequest,  # Pydantic model auto-validates
    context: UserContext = Depends(authenticate_user),
    session: AsyncSession = Depends(db.get_db_async),
) -> Resource:
    return await _resource.create(request, context, session)
```

### 2. Path Parameters
```python
@router.get("/accounts/{account_name}/projects/{project_id}")
def get_project(
    account_name: str,      # From path
    project_id: uuid.UUID,  # From path, auto-converted to UUID
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Project:
    # Use path parameters
```

### 3. Query Parameters
```python
from fastapi import Query

@router.get("/resources")
def list_resources(
    keyword: str = Query(None, description="Filter by keyword"),
    page: int = Query(1, gt=0, description="Page number"),
    page_size: int = Query(10, gt=0, le=100, description="Items per page"),
    session: Session = Depends(db.get_db),
) -> ListResourcesResponse:
    # Query parameters are optional by default
```

### 4. Form Data with File Upload
```python
from fastapi import Form, File, UploadFile
import json

@router.post("/checkpoints")
async def create_checkpoint(
    name: str = Form(...),                    # Required form field
    description: str | None = Form(None),     # Optional form field
    rules: str | None = Form(None),           # JSON as string
    image: UploadFile | None = File(None),    # File upload
    session: AsyncSession = Depends(db.get_db_async),
):
    # Parse JSON from form field
    rules_dict = json.loads(rules) if rules else None

    # Read file if provided
    if image:
        image_content = await image.read()
```

**RULE:** Use Form/File for multipart/form-data, JSON body for application/json

## RESPONSE PATTERNS

### 1. Typed Response Model (Required)
```python
from api.schemas.admin.resource import Resource

@router.get("/resources/{resource_id}")
def get_resource(...) -> Resource:  # Type annotation REQUIRED
    """Return type enables OpenAPI schema generation."""
    return resource_object  # Must match return type
```

### 2. List Response with Pagination
```python
from api.schemas.admin.resource import ListResourcesResponse

@router.get("/resources")
def list_resources(...) -> ListResourcesResponse:
    return ListResourcesResponse(
        resources=[...],
        total=100,
        total_pages=10,
        page=1,
        page_size=10,
    )
```

### 3. Error Response Documentation (Required)
```python
from api.schemas.error.error import ErrorResponse

@router.post(
    "/resources",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        403: {"model": ErrorResponse, "description": "Permission denied"},
        404: {"model": ErrorResponse, "description": "Resource not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
def create_resource(...) -> Resource:
    # Document all possible error responses
```

## ERROR HANDLING PATTERNS

### Standard HTTPException Pattern
```python
from fastapi import HTTPException, status

# 404 Not Found
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Resource not found",
    headers={"Content-Type": "application/json"},
)

# 400 Bad Request
raise HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail=f"Invalid input: {error_message}",
    headers={"Content-Type": "application/json"},
)

# 403 Forbidden
raise HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="User does not have permission to access this resource",
    headers={"Content-Type": "application/json"},
)

# 500 Internal Server Error
raise HTTPException(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    detail="An unexpected error occurred",
    headers={"Content-Type": "application/json"},
)
```

**RULE:** Always include `headers={"Content-Type": "application/json"}`

### Error Helper Functions (Recommended)
```python
# In _utils.py
def not_found_error(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=message,
        headers={"Content-Type": "application/json"},
    )

def forbidden_error(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=message,
        headers={"Content-Type": "application/json"},
    )
```

## ASYNC VS SYNC DECISION MATRIX

### Use ASYNC When:
1. Making external API calls (HTTP requests to third-party services)
2. Long-running operations (>100ms)
3. Streaming responses (Server-Sent Events, WebSockets)
4. Background tasks with fire-and-forget pattern
5. Multiple I/O operations that can run concurrently

### Use SYNC When:
1. Simple CRUD operations with database
2. Operations complete in <100ms
3. No external I/O beyond database
4. Simpler code maintenance is priority

### Async Endpoint with Async DB
```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

@router.post("/resources")
async def create_resource(
    request: CreateResourceRequest,
    session: AsyncSession = Depends(db.get_db_async),
) -> Resource:
    result = await session.execute(select(DbResource).filter(...))
    resource = result.scalar_one_or_none()
    await session.commit()
    return resource
```

### Sync Endpoint with Sync DB
```python
from sqlalchemy.orm import Session

@router.post("/resources")
def create_resource(
    request: CreateResourceRequest,
    session: Session = Depends(db.get_db),
) -> Resource:
    resource = session.query(DbResource).filter(...).first()
    session.commit()
    return resource
```

**RULE:** NEVER mix async endpoint with sync DB or sync endpoint with async DB

### Background Task Pattern
```python
import asyncio
from db.session import AsyncSessionLocal

# Module-level set prevents GC of in-flight tasks
_background_tasks: set[asyncio.Task] = set()

@router.post("/process")
async def trigger_processing(request: ProcessRequest):
    async def background_task():
        async with AsyncSessionLocal() as session:
            try:
                await process_data(session, request)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    task = asyncio.create_task(background_task())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"status": "processing", "message": "Task started"}
```

**NEVER** use bare `asyncio.create_task()` without storing the reference in a module-level set. The task can be garbage-collected before completion, abandoning any checked-out DB connections.

### Streaming Response Pattern

**WARNING:** `Depends(get_db_async)` MUST NOT be used for sessions that are needed inside a `StreamingResponse` generator. When `BaseHTTPMiddleware` is present, FastAPI dependency cleanup runs when the handler returns the `StreamingResponse` object — **before the generator starts streaming** — so the session is closed before the generator can use it. This leaks exactly 1 connection per streaming request.

Instead, the generator must own its session via `AsyncSessionLocal()`:

```python
from fastapi.responses import StreamingResponse
from typing import AsyncIterator
from db.session import AsyncSessionLocal

@router.post("/stream")
async def stream_response(request: StreamRequest):
    # Auth/validation params can still use Depends() — they complete before return

    async def generate() -> AsyncIterator[str]:
        async with AsyncSessionLocal() as session:
            try:
                async for chunk in get_data_stream(session, request):
                    yield f"data: {json.dumps(chunk)}\n\n"
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
```

See ADR-019 (`docs/decisions/019-streaming-session-ownership.md`) for full context.

## SPECIAL ENDPOINT PATTERNS

### Batch Operations
```python
@router.post("/projects/batch", status_code=status.HTTP_201_CREATED)
async def batch_create_projects(
    request: BatchCreateProjectsRequest,
    context: UserContext = Depends(authenticate_user),
    session: AsyncSession = Depends(db.get_db_async),
) -> BatchCreateProjectsResponse:
    """Create multiple projects in a single request."""
    results = []
    for project_request in request.projects:
        try:
            project = await create_project(project_request, context, session)
            results.append(ProjectCreationResult(
                name=project_request.name,
                success=True,
                project_id=project.id,
            ))
        except Exception as e:
            results.append(ProjectCreationResult(
                name=project_request.name,
                success=False,
                error=str(e),
            ))

    return BatchCreateProjectsResponse(results=results)
```

### Webhook Endpoints
```python
from fastapi import Request
from fastapi.responses import JSONResponse

@router.post("/webhooks/provider")
async def handle_webhook(request: Request):
    # 1. Verify signature
    signature = request.headers.get("X-Provider-Signature")
    body = await request.body()
    if not verify_signature(signature, body):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 2. Parse event
    event_data = await request.json()

    # 3. Process asynchronously
    asyncio.create_task(process_webhook(event_data))

    # 4. Return immediately (webhooks expect fast response)
    return JSONResponse(status_code=200, content={"status": "received"})
```

### OAuth Callback Endpoints
```python
from fastapi import Request, Query
from fastapi.responses import RedirectResponse

@router.get("/oauth/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
):
    # Exchange authorization code for access token
    token_data = await exchange_code_for_token(code)

    # Store token in database
    await save_integration_token(state, token_data)

    # Redirect to success page
    return RedirectResponse(url=f"/integrations/success?provider={state}")
```

## DOCUMENTATION REQUIREMENTS

### Endpoint Docstrings (Required)
```python
@router.get("/resources/{resource_id}")
def get_resource(resource_id: uuid.UUID, ...) -> Resource:
    """
    Retrieve a single resource by ID.

    This docstring appears in OpenAPI documentation.
    First line is the summary, rest is the description.
    """
```

### Detailed Documentation (For Complex Endpoints)
```python
@router.get("/reports")
async def get_reports(...) -> ReportsResponse:
    """
    Retrieve unified analytics reports for account.

    Combines data from multiple sources including chat sessions,
    lead tracking, and catering orders. Data is filtered by the
    specified date range (default: last 7 days).

    Args:
        account_name: Account identifier
        start_date: Start date in ISO 8601 format (YYYY-MM-DD)
        end_date: End date in ISO 8601 format (YYYY-MM-DD)
        include_inactive: Whether to include inactive items

    Returns:
        ReportsResponse: Unified report data with aggregated metrics

    Raises:
        403: User does not have access to account
        404: Account not found
    """
```

## ANTI-PATTERNS

### ❌ WRONG: Manual Session Management
```python
# NEVER DO THIS
session = next(db.get_db())
try:
    result = session.query(Model).all()
finally:
    session.close()
```

### ✅ CORRECT: Use FastAPI Dependencies
```python
@router.get("/resources")
def list_resources(session: Session = Depends(db.get_db)):
    result = session.query(Model).all()
    return result  # Session automatically closed
```

---

### ❌ WRONG: Mixed Async/Sync
```python
@router.post("/resources")  # Async endpoint
async def create_resource(
    session: Session = Depends(db.get_db),  # Sync DB
):
    result = session.query(Model).all()  # Blocks event loop!
```

### ✅ CORRECT: Consistent Async
```python
@router.post("/resources")
async def create_resource(
    session: AsyncSession = Depends(db.get_db_async),
):
    result = await session.execute(select(Model))
```

---

### ❌ WRONG: Missing Authorization
```python
@router.get("/accounts/{account_name}/data")
def get_data(
    account_name: str,
    context: UserContext = Depends(authenticate_user),  # Only authenticated, not authorized!
):
    return get_account_data(account_name)  # No authorization check!
```

### ✅ CORRECT: Always Authorize
```python
@router.get("/accounts/{account_name}/data")
def get_data(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),  # Authorization via RBAC
):
    return get_account_data(account_name)
```

---

### ❌ WRONG: No Error Response Models
```python
@router.post("/resources")
def create_resource(...) -> Resource:  # No error documentation
    if error:
        raise HTTPException(status_code=400, detail="Error")
```

### ✅ CORRECT: Document All Errors
```python
from api.schemas.error.error import ErrorResponse

@router.post(
    "/resources",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def create_resource(...) -> Resource:
    # Errors documented in OpenAPI
```

---

### ❌ WRONG: Inconsistent Status Codes
```python
@router.post("/resource1")  # Returns 200
def create1(...):

@router.post("/resource2", status_code=201)  # Returns 201
def create2(...):
```

### ✅ CORRECT: Consistent Status Codes
```python
@router.post("/resources", status_code=status.HTTP_201_CREATED)
def create(...):

@router.patch("/resources/{id}", status_code=status.HTTP_200_OK)
def update(...):

@router.delete("/resources/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(...):
```

---

### ❌ WRONG: Manual Input Escaping
```python
import html

@router.post("/resources")
def create(name: str):
    safe_name = html.escape(name)  # Manual escaping
    return process(safe_name)
```

### ✅ CORRECT: Pydantic Validation + ORM Parameterization
```python
from pydantic import BaseModel, Field

class CreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)

@router.post("/resources")
def create(request: CreateRequest, session: Session = Depends(db.get_db)):
    # Pydantic validates, SQLAlchemy parameterizes
    result = session.query(Model).filter(Model.name == request.name).first()
```

---

### ❌ WRONG: Monolithic Route File
```python
# admin/__init__.py - 2700 lines with all endpoints
```

### ✅ CORRECT: Split by Resource
```python
# admin/__init__.py
from admin._account import account_router
from admin._agent import agent_router
from admin._project import project_router

admin_router = APIRouter(prefix=endpoints.ADMIN, tags=["Admin"])
admin_router.include_router(account_router)
admin_router.include_router(agent_router)
admin_router.include_router(project_router)
```

## REQUIRED IMPORTS TEMPLATE

```python
# FastAPI core
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Query, Form, File, UploadFile, Request
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse

# SQLAlchemy
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import db

# Authentication & Authorization
from api.routes.admin._auth import authenticate_user
from api.routes.admin._utils import UserContext
from api.routes.admin._auth import authorize_admin
from services.auth_service.dependencies import require_account_permission, require_project_permission

# Schemas
from api.schemas.admin.<resource> import (
    CreateResourceRequest,
    UpdateResourceRequest,
    Resource,
    ListResourcesResponse,
)
from api.schemas.error.error import ErrorResponse

# Endpoints constants
from api.routes.endpoints import endpoints

# Python standard library
from typing import AsyncIterator
import asyncio
import json
import uuid
```

## ENDPOINT TEMPLATE (COPY-PASTE STARTER)

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import db

from api.routes.admin._auth import authenticate_user
from api.routes.admin._utils import UserContext
from services.auth_service.dependencies import require_account_permission
from api.schemas.admin.resource import CreateResourceRequest, UpdateResourceRequest, Resource, ListResourcesResponse
from api.schemas.error.error import ErrorResponse
from api.routes.endpoints import endpoints

from . import _resource

resource_router = APIRouter(prefix=f"{endpoints.ADMIN}/resources", tags=["Resources"])

@resource_router.get(
    "",
    responses={500: {"model": ErrorResponse}},
)
def list_resources(
    page: int = Query(1, gt=0),
    page_size: int = Query(10, gt=0, le=100),
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> ListResourcesResponse:
    """List all resources with pagination."""
    return _resource.list_resources(page, page_size, context, session)

@resource_router.get(
    "/{resource_id}",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_resource(
    resource_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Resource:
    """Retrieve a single resource by ID."""
    return _resource.get_resource(resource_id, context, session)

@resource_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def create_resource(
    request: CreateResourceRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Resource:
    """Create a new resource."""
    return _resource.create_resource(request, context, session)

@resource_router.patch(
    "/{resource_id}",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def update_resource(
    resource_id: uuid.UUID,
    request: UpdateResourceRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
) -> Resource:
    """Update an existing resource."""
    return _resource.update_resource(resource_id, request, context, session)

@resource_router.delete(
    "/{resource_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def delete_resource(
    resource_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(db.get_db),
):
    """Delete a resource."""
    _resource.delete_resource(resource_id, context, session)
```
