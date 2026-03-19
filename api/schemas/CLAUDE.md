# api/schemas/

Pydantic V2 schemas for API request/response models.

## Rules

### ALWAYS

- `model_config = ConfigDict(from_attributes=True)` on response models populated from ORM
- Modern union syntax: `str | None` (never `Optional[str]`)
- Typed collections: `dict[str, Any]`, `list[str]` (never bare `dict` or `list`)
- `Field(default_factory=dict)` / `Field(default_factory=list)` for mutable defaults
- `Field(description="...")` on all public API fields
- `Field(...)` for required fields without defaults
- Inherit Create requests from Update requests to reduce duplication
- `@field_validator` for business logic validation
- Docstrings on all schema classes

### NEVER

- Bare mutable defaults (`metadata: dict = {}`) — always `Field(default_factory=dict)`
- Pydantic V1 patterns (`class Config:`) — use `model_config = ConfigDict(...)` 
- Mixed timestamp types — always `datetime` with `timezone.utc`
- All fields optional in Create requests — required fields use `Field(...)`
- Duplicate fields between Update and Create — use inheritance

## Directory Structure

```
api/schemas/
├── admin/          # Core business entities (account, agent, project, user)
├── asset/          # File/asset management
├── catering/       # Catering-specific features
├── chat/           # Chat and messaging
├── error/          # Error response schemas
├── events/         # Event-related schemas
└── operations/     # Operational workflow schemas
```

No `__init__.py` files — import schemas directly from module files.

## Naming Conventions

### Requests
| Pattern | Purpose |
|---------|---------|
| `Create{Entity}Request` | POST endpoints creating resources |
| `Update{Entity}Request` | PATCH endpoints modifying resources |
| `Batch{Action}{Entity}Request` | Bulk operations |

### Responses
| Pattern | Purpose |
|---------|---------|
| `{Entity}` | Single resource (mirrors DB model) |
| `{Entity}Summary` | Lightweight version for list endpoints |
| `{Entity}Detail` | Detailed version with computed fields |
| `List{Entity}Response` | Collection + pagination |
| `Batch{Action}{Entity}Response` | Bulk results with success/failure |

### Helpers
| Pattern | Purpose |
|---------|---------|
| `{Entity}Params` | API request → service layer conversion |
| `{Entity}CreationResult` | Individual item tracking in batch ops |

## Key Pattern: Update → Create Inheritance

```python
class UpdateAgentRequest(BaseModel):
    """All fields optional."""
    name: str | None = None
    description: str | None = None

class CreateAgentRequest(UpdateAgentRequest):
    """Adds required fields, overrides optional→required."""
    account_name: str = Field(..., description="Account identifier")
    name: str = Field(..., min_length=1, max_length=255)
```

## Key Pattern: Summary → Detail Inheritance

```python
class ProjectSummary(BaseModel):
    """Lightweight for list views."""
    id: uuid.UUID
    name: str
    account_name: str
    created_at: datetime

class Project(ProjectSummary):
    """Full details."""
    model_config = ConfigDict(from_attributes=True)
    description: str | None
    metadata: dict[str, Any]
    raw_config: dict[str, Any]
    updated_at: datetime | None
```

## Enums

Import from `db.tables.types` or `db.tables.agent` — don't redefine in schemas.
