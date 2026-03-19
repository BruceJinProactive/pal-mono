# api/routes/

FastAPI route layer. Thin handlers that delegate to implementation modules.

## Rules

### ALWAYS

- `context: UserContext = Depends(authenticate_user)` for authentication
- `require_account_permission()` or `require_project_permission()` for authorization
- Match async endpoints with `AsyncSession = Depends(db.get_db_async)`, sync with `Session = Depends(db.get_db)`
- `HTTPException` with `headers={"Content-Type": "application/json"}`
- Error response models in decorator: `responses={400: {"model": ErrorResponse}}`
- Docstrings on route handlers (becomes OpenAPI description)
- Separate route handlers (`__init__.py`) from implementation (`_<resource>.py`)
- Return typed responses with `-> ResourceModel` annotation
- `status.HTTP_*` constants (never hardcoded ints)
- Use `endpoints.py` constants for paths (never hardcoded strings)

### NEVER

- `next(db.get_db())` — always `Depends(db.get_db)`
- Mix async endpoint with sync DB or vice versa
- Skip authorization after authentication
- `html.escape()` — Pydantic validates, SQLAlchemy parameterizes
- Monolithic `__init__.py` over 500 lines — split into `_<resource>.py`
- Bare `asyncio.create_task()` — store reference in module-level set to prevent GC

## Directory Structure

```
api/routes/
├── endpoints.py          # Centralized path constants (ALWAYS use)
├── v1_router.py          # Root router aggregating all domain routers
├── status.py             # Health checks
├── utils.py              # Cross-domain shared utilities
├── internal/             # Internal routes (not exposed via v1)
└── <domain>/             # Domain-specific routes
    ├── __init__.py       # Router + route decorators ONLY
    ├── _implementation.py  # Generic business logic
    ├── _<resource>.py    # Resource-specific logic
    ├── _auth.py          # Auth/authorization
    ├── _utils.py         # Domain utilities
    └── _builder.py       # DB model → API schema conversion
```

All implementation modules MUST start with underscore `_`.

## Auth Flow

```python
from api.routes.admin._auth import authenticate_user
from services.auth_service.dependencies import require_account_permission

@router.get("/accounts/{account_name}/resource")
def get_resource(
    account_name: str,
    context: UserContext = Depends(
        require_account_permission("account.read", authenticate_user)
    ),
    session: Session = Depends(db.get_db),
) -> Resource:
    return _resource.get(account_name, context, session)
```

| Helper | Purpose |
|--------|---------|
| `require_account_permission(perm, auth_dep)` | Account-scoped RBAC |
| `require_project_permission(perm, auth_dep)` | Project-scoped RBAC |
| `authorize_admin(context)` | Admin-only operations |

## Status Code Conventions

| Method | Status | Idempotent |
|--------|--------|------------|
| GET | 200 | Yes |
| POST (create) | 201 | No |
| POST (action) | 200 or 202 | No |
| PATCH | 200 | No |
| DELETE | 204 | Yes |

## Streaming Response Gotcha (ADR-019)

`Depends(get_db_async)` MUST NOT be used for sessions inside `StreamingResponse` generators. With `BaseHTTPMiddleware`, dependency cleanup runs when the handler returns — **before the generator streams** — closing the session early.

Generator must own its session:

```python
from db.session import AsyncSessionLocal

@router.post("/stream")
async def stream_response(request: StreamRequest):
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

    return StreamingResponse(generate(), media_type="text/event-stream")
```

## Background Task GC Pattern

```python
_background_tasks: set[asyncio.Task] = set()  # Module-level, prevents GC

task = asyncio.create_task(background_fn())
_background_tasks.add(task)
task.add_done_callback(_background_tasks.discard)
```

## Router Aggregation

Domain routers → `v1_router.py`:

```python
v1_router = APIRouter(prefix="/v1")
v1_router.include_router(admin_router)
v1_router.include_router(chat_router)
v1_router.include_router(integrations_router)
# ...
```

Sub-routers for nested features:

```python
integrations_router = APIRouter(prefix=endpoints.INTEGRATIONS)
integrations_router.include_router(vapi_router)
integrations_router.include_router(toast_router)
```

Nested resource paths: nested for list/create, top-level for get/update/delete.
