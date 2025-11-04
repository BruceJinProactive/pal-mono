# api/schemas/

## CRITICAL RULES

### ALWAYS
1. Use `model_config = ConfigDict(from_attributes=True)` for response models populated from ORM
2. Use `datetime` with timezone awareness for all timestamps
3. Use modern union syntax `str | None` instead of `Optional[str]`
4. Type all collections: `dict[str, Any]`, `list[str]` (never bare `dict` or `list`)
5. Use `Field(default_factory=dict)` or `Field(default_factory=list)` for mutable defaults
6. Add `Field(description="...")` for all public API fields
7. Use `Field(...)` for required fields without defaults
8. Inherit Create requests from Update requests to reduce duplication
9. Add `@field_validator` for business logic validation
10. Add docstrings to all schema classes

### NEVER
1. Use bare mutable defaults like `metadata: dict = {}` - use `Field(default_factory=dict)` instead
2. Mix Pydantic v1 patterns (`class Config`) - use `model_config = ConfigDict(from_attributes=True)` instead
3. Use inconsistent timestamp types (int, str, datetime) - always use `datetime` with timezone awareness
4. Mix `Optional[T]` and `T | None` syntax - consistently use modern `str | None` syntax
5. Make all fields optional in Create request schemas - use `Field(...)` for required fields
6. Skip validation for user input that has business rules - add `@field_validator` or `@model_validator`
7. Use bare `dict` or `list` without type parameters - use typed `dict[str, Any]` and `list[str]` instead
8. Duplicate field definitions between Update and Create requests - inherit Create from Update instead

## DIRECTORY STRUCTURE

```
api/schemas/
├── admin/          # Core business entities
│   ├── account.py
│   ├── agent.py
│   ├── project.py
│   ├── user.py
│   └── ...
├── chat/           # Chat and messaging
├── asset/          # File/asset management
├── catering/       # Catering-specific features
└── error/          # Error response schemas
    └── error.py
```

**RULE:** No `__init__.py` files - import schemas directly from module files

## NAMING CONVENTIONS (STRICT)

### Request Schemas
| Pattern | Purpose | When to Use |
|---------|---------|-------------|
| `Create{Entity}Request` | New entity creation | POST endpoints creating resources |
| `Update{Entity}Request` | Existing entity updates | PATCH endpoints modifying resources |
| `Batch{Action}{Entity}Request` | Bulk operations | Batch create/update/delete endpoints |

### Response Schemas
| Pattern | Purpose | When to Use |
|---------|---------|-------------|
| `{Entity}` | Main entity model | Single resource responses, mirrors DB model |
| `{Entity}Summary` | Lightweight version | List endpoints returning many items |
| `{Entity}Detail` | Detailed version | Detail endpoints with extra computed fields |
| `List{Entity}Response` | Collection + pagination | List endpoints with pagination metadata |
| `Batch{Action}{Entity}Response` | Bulk operation results | Batch endpoints with success/failure tracking |
| `{Entity}Response` | Specific response wrapper | Special response formats (status, report, etc.) |

### Helper Schemas
| Pattern | Purpose | When to Use |
|---------|---------|-------------|
| `{Entity}Params` | Service layer parameters | Converting API request to service layer |
| `{Entity}CreationResult` | Individual batch result | Tracking individual item in batch operation |

## PYDANTIC V2 PATTERNS

### Base Schema Structure
```python
from pydantic import BaseModel, ConfigDict, Field
import uuid
from datetime import datetime, timezone

class Resource(BaseModel):
    """Resource Model"""
    model_config = ConfigDict(from_attributes=True)  # REQUIRED for ORM models

    id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    account_name: str
    created_at: datetime
    updated_at: datetime | None = None
```

### Model Configuration
```python
# REQUIRED when populating from SQLAlchemy models
model_config = ConfigDict(from_attributes=True)

# Other common config options
model_config = ConfigDict(
    from_attributes=True,
    populate_by_name=True,  # Allow population by field name and alias
    str_strip_whitespace=True,  # Auto-strip strings
)
```

## FIELD PATTERNS

### Required Fields
```python
# Required, no default
name: str = Field(...)
id: uuid.UUID = Field(...)

# Required with validation
name: str = Field(..., min_length=1, max_length=255)
email: str = Field(..., pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$")

# Required with description (for public APIs)
account_name: str = Field(..., description="Account identifier")
```

### Optional Fields
```python
# Optional nullable (most common)
description: str | None = None
updated_at: datetime | None = None

# Optional with default value
status: str = Field(default="active")
is_active: bool = Field(default=True)
priority: int = Field(default=0, ge=0)

# Optional with default factory (for mutable types)
metadata: dict[str, str] = Field(default_factory=dict)
tags: list[str] = Field(default_factory=list)
```

### Dynamic Defaults
```python
# UUID generation
id: uuid.UUID = Field(default_factory=uuid.uuid4)

# Current timestamp
created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Empty mutable types (ALWAYS use default_factory)
metadata: dict[str, Any] = Field(default_factory=dict)
items: list[str] = Field(default_factory=list)
```

### Validation Constraints
```python
# String constraints
name: str = Field(..., min_length=1, max_length=255)
code: str = Field(..., pattern=r"^[A-Z]{3}$")

# Numeric constraints
age: int = Field(..., ge=0, le=120)  # Greater or equal, less or equal
price: float = Field(..., gt=0)  # Greater than
page_size: int = Field(default=10, gt=0, le=100)

# Collection constraints
tags: list[str] = Field(default_factory=list, min_length=1, max_length=10)
```

## TYPE PATTERNS

### Identifiers
```python
import uuid

# UUIDs (most common for IDs)
id: uuid.UUID
resource_id: uuid.UUID
agent_id: uuid.UUID

# Strings (for names, codes)
account_name: str
name: str
code: str
```

### Timestamps (STANDARDIZED)
```python
from datetime import datetime, date, timezone

# ALWAYS use timezone-aware datetime
created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
updated_at: datetime | None = None

# Date-only fields (rare)
start_date: date
end_date: date
```

**RULE:** NEVER mix int (Unix timestamp) or str (ISO 8601) with datetime objects

### Collections (TYPED)
```python
from typing import Any

# Typed lists
tags: list[str] = Field(default_factory=list)
ids: list[uuid.UUID] = Field(default_factory=list)

# Typed dictionaries
metadata: dict[str, str] = Field(default_factory=dict)
raw_config: dict[str, Any] = Field(default_factory=dict)
channel_info: dict[str, Any] = Field(default_factory=dict)

# NEVER use bare types
metadata: dict = {}  # WRONG
tags: list = []      # WRONG
```

### Enums
```python
from enum import Enum
from db.tables.agent import AgentType, Language, SpeechRate

# String enums (for API schemas)
class Status(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"

# Import from database types (preferred)
class Agent(BaseModel):
    agent_type: AgentType
    language: Language = Language.EN
    speech_rate: SpeechRate = SpeechRate.NORMAL
```

## VALIDATION PATTERNS

### Field Validators (Single Field)
```python
from pydantic import field_validator

class CreateResourceRequest(BaseModel):
    name: str
    price: float
    page_size: int

    @field_validator("name")
    def validate_name(cls, v):
        """Validate name is not empty or whitespace."""
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()

    @field_validator("price")
    def validate_price(cls, v):
        """Validate price is positive."""
        if v < 0:
            raise ValueError("Price must be non-negative")
        return v

    @field_validator("page_size")
    def validate_page_size(cls, v):
        """Validate page size is within bounds."""
        if v < 1 or v > 100:
            raise ValueError("Page size must be between 1 and 100")
        return v
```

### Model Validators (Cross-Field)
```python
from pydantic import model_validator

class DateRangeRequest(BaseModel):
    start_date: datetime
    end_date: datetime

    @model_validator(mode="after")
    def validate_date_range(self):
        """Ensure end date is after start date."""
        if self.end_date < self.start_date:
            raise ValueError("end_date must be after or equal to start_date")
        return self
```

### Validators with Context
```python
from pydantic import field_validator, ValidationInfo

class UpdateRequest(BaseModel):
    field1: str | None = None
    field2: str | None = None

    @field_validator("field2")
    def validate_field2_dependency(cls, v, info: ValidationInfo):
        """Validate field2 requires field1."""
        if v and not info.data.get("field1"):
            raise ValueError("field2 requires field1 to be set")
        return v
```

### Multiple Field Validation
```python
@field_validator("email", "backup_email")
def validate_email_format(cls, v):
    """Validate email format for multiple fields."""
    if v and "@" not in v:
        raise ValueError("Invalid email format")
    return v.lower() if v else v
```

## INHERITANCE PATTERNS

### Pattern 1: Update → Create (RECOMMENDED)
```python
class UpdateAgentRequest(BaseModel):
    """Update Agent Request - all fields optional."""
    name: str | None = None
    description: str | None = None
    agent_type: AgentType | None = None
    language: Language | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

class CreateAgentRequest(UpdateAgentRequest):
    """Create Agent Request - adds required fields."""
    account_name: str = Field(..., description="Account identifier")
    name: str = Field(..., min_length=1, max_length=255)  # Override optional to required
```

**Benefits:**
- Zero duplication
- Update has all fields optional
- Create adds required fields and overrides
- Shared validators apply to both

### Pattern 2: Summary → Detail
```python
class ProjectSummary(BaseModel):
    """Lightweight for list views."""
    id: uuid.UUID
    name: str
    account_name: str
    created_at: datetime

class Project(ProjectSummary):
    """Full details for single resource."""
    description: str | None
    metadata: dict[str, Any]
    raw_config: dict[str, Any]
    agent_count: int
    updated_at: datetime | None
```

## REQUEST/RESPONSE PATTERNS

### Create Request Template
```python
class CreateResourceRequest(BaseModel):
    """Create Resource Request"""
    # Required fields
    account_name: str = Field(..., description="Account identifier")
    name: str = Field(..., min_length=1, max_length=255, description="Resource name")

    # Optional fields
    description: str | None = Field(default=None, description="Optional description")
    metadata: dict[str, str] = Field(default_factory=dict, description="Custom metadata")

    # Validation
    @field_validator("name")
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()
```

### Update Request Template
```python
class UpdateResourceRequest(BaseModel):
    """Update Resource Request - all fields optional"""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    metadata: dict[str, str] | None = None
    expected_version: int | None = Field(default=None, description="For optimistic locking")

    @field_validator("name")
    def validate_name(cls, v):
        if v is not None and not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip() if v else v
```

### Response Model Template
```python
class Resource(BaseModel):
    """Resource Model"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_name: str
    name: str
    description: str | None
    metadata: dict[str, str]
    created_at: datetime
    updated_at: datetime | None
```

### List Response Template
```python
class ListResourcesResponse(BaseModel):
    """List Resources Response"""
    resources: list[ResourceSummary]  # Use Summary for lists
    total: int = Field(..., description="Total number of items")
    total_pages: int = Field(..., description="Total number of pages")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Items per page")
```

### Batch Response Template
```python
class ResourceCreationResult(BaseModel):
    """Individual resource creation result"""
    name: str
    success: bool
    resource_id: uuid.UUID | None = None
    error: str | None = None

class BatchCreateResourcesResponse(BaseModel):
    """Batch create resources response"""
    results: list[ResourceCreationResult]
    total_requested: int
    total_created: int
    total_failed: int

    @property
    def success_rate(self) -> float:
        """Computed success rate percentage."""
        if self.total_requested == 0:
            return 0.0
        return (self.total_created / self.total_requested) * 100.0
```

## CONVERSION METHODS

### To Service Layer Parameters
```python
from services.agent_service import AgentParams

class UpdateAgentRequest(BaseModel):
    name: str | None = None
    description: str | None = None

    def to_agent_params(self) -> AgentParams:
        """Convert API request to service layer parameters."""
        return AgentParams(
            name=self.name,
            description=self.description,
        )
```

### Computed Properties
```python
class ProjectStats(BaseModel):
    total_requested: int
    total_created: int

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_requested == 0:
            return 0.0
        return (self.total_created / self.total_requested) * 100.0
```

## COMMON PATTERNS

### Pagination Request
```python
class PaginationParams(BaseModel):
    """Standard pagination parameters"""
    page: int = Field(default=1, gt=0, description="Page number (1-indexed)")
    page_size: int = Field(default=10, gt=0, le=100, description="Items per page")
    keyword: str | None = Field(default=None, description="Search keyword")
```

### Optimistic Locking
```python
class UpdateResourceRequest(BaseModel):
    name: str | None = None
    expected_version: int | None = Field(
        default=None,
        description="Expected version for optimistic locking"
    )
```

### Idempotency
```python
class CreateOrderRequest(BaseModel):
    customer_id: str
    items: list[OrderItem]
    idempotency_key: str | None = Field(
        default=None,
        description="Idempotency key to prevent duplicate operations"
    )
```

### Metadata Storage
```python
class Resource(BaseModel):
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="User-defined key-value metadata"
    )
    raw_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw configuration object"
    )
```

### Nested Models
```python
class Address(BaseModel):
    """Address component"""
    street: str
    city: str
    state: str
    zip_code: str

class User(BaseModel):
    """User with nested address"""
    id: uuid.UUID
    name: str
    email: str
    address: Address  # Nested model
    billing_address: Address | None = None  # Optional nested
```

## ANTI-PATTERNS

### ❌ WRONG: Mutable Default Values
```python
# NEVER DO THIS - shared across all instances
class Resource(BaseModel):
    tags: list[str] = []
    metadata: dict = {}
```

### ✅ CORRECT: Use default_factory
```python
class Resource(BaseModel):
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
```

---

### ❌ WRONG: Pydantic v1 Config
```python
class Resource(BaseModel):
    class Config:
        orm_mode = True
```

### ✅ CORRECT: Pydantic v2 ConfigDict
```python
from pydantic import ConfigDict

class Resource(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

---

### ❌ WRONG: Mixed Timestamp Types
```python
class Resource(BaseModel):
    created_at: int  # Unix timestamp
    updated_at: str  # ISO 8601 string
    deleted_at: datetime  # datetime object
```

### ✅ CORRECT: Consistent datetime
```python
from datetime import datetime, timezone

class Resource(BaseModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
```

---

### ❌ WRONG: Bare dict/list Types
```python
class Resource(BaseModel):
    metadata: dict = Field(default_factory=dict)
    tags: list = Field(default_factory=list)
```

### ✅ CORRECT: Typed Collections
```python
from typing import Any

class Resource(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
```

---

### ❌ WRONG: Mixed Optional Syntax
```python
from typing import Optional

class Resource(BaseModel):
    description: Optional[str] = None
    metadata: str | None = None  # Inconsistent!
```

### ✅ CORRECT: Consistent Modern Syntax
```python
class Resource(BaseModel):
    description: str | None = None
    metadata: str | None = None
```

---

### ❌ WRONG: No Validation
```python
class CreateRequest(BaseModel):
    name: str
    price: float
    page_size: int
    # No validation!
```

### ✅ CORRECT: Business Logic Validation
```python
from pydantic import field_validator

class CreateRequest(BaseModel):
    name: str
    price: float
    page_size: int

    @field_validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()

    @field_validator("price")
    def validate_price(cls, v):
        if v < 0:
            raise ValueError("Price must be non-negative")
        return v

    @field_validator("page_size")
    def validate_page_size(cls, v):
        if v < 1 or v > 100:
            raise ValueError("Page size must be between 1 and 100")
        return v
```

---

### ❌ WRONG: All Fields Optional in Create Request
```python
class CreateAgentRequest(BaseModel):
    account_name: str | None = None  # Should be required!
    name: str | None = None  # Should be required!
```

### ✅ CORRECT: Required Fields in Create
```python
class CreateAgentRequest(BaseModel):
    account_name: str = Field(..., description="Account identifier")
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None  # Optional is OK
```

---

### ❌ WRONG: Duplicate Update/Create Fields
```python
class UpdateAgentRequest(BaseModel):
    name: str | None = None
    description: str | None = None

class CreateAgentRequest(BaseModel):
    account_name: str
    name: str | None = None  # Duplicated!
    description: str | None = None  # Duplicated!
```

### ✅ CORRECT: Inheritance
```python
class UpdateAgentRequest(BaseModel):
    name: str | None = None
    description: str | None = None

class CreateAgentRequest(UpdateAgentRequest):  # Inherits all fields
    account_name: str = Field(..., description="Account identifier")
    name: str = Field(..., min_length=1, max_length=255)  # Override to required
```

---

### ❌ WRONG: No Field Descriptions
```python
class CreateAgentRequest(BaseModel):
    account_name: str
    name: str
    agent_type: AgentType
```

### ✅ CORRECT: Documented Fields
```python
class CreateAgentRequest(BaseModel):
    account_name: str = Field(..., description="Account identifier")
    name: str = Field(..., min_length=1, max_length=255, description="Agent display name")
    agent_type: AgentType = Field(..., description="Type: VOICE, TEXT, WHATSAPP")
```

---

### ❌ WRONG: Mixed Import Styles
```python
from typing import Optional, List, Dict
import uuid
from uuid import UUID

description: Optional[str] = None
tags: list[str] = []
ids: List[UUID] = []
metadata: Dict[str, str] = {}
```

### ✅ CORRECT: Consistent Modern Syntax
```python
import uuid
from typing import Any

description: str | None = None
tags: list[str] = []
ids: list[uuid.UUID] = []
metadata: dict[str, str] = {}
```

## REQUIRED IMPORTS TEMPLATE

```python
# Core Pydantic
from pydantic import BaseModel, ConfigDict, Field
from pydantic import field_validator, model_validator, ValidationInfo

# Python standard library
import uuid
from datetime import datetime, date, timezone
from typing import Any
from enum import Enum

# Database enums (import as needed)
from db.tables.agent import AgentType, Language, SpeechRate
from db.tables.types import Status, Role

# Service layer (for conversion methods)
from services.agent_service import AgentParams
```

## SCHEMA TEMPLATE (COPY-PASTE STARTER)

```python
import uuid
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator

class UpdateResourceRequest(BaseModel):
    """Update Resource Request - all fields optional"""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("name")
    def validate_name(cls, v):
        """Ensure name is not empty if provided."""
        if v is not None and not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip() if v else v

class CreateResourceRequest(UpdateResourceRequest):
    """Create Resource Request - adds required fields"""
    account_name: str = Field(..., description="Account identifier")
    name: str = Field(..., min_length=1, max_length=255, description="Resource name")

class ResourceSummary(BaseModel):
    """Resource Summary - lightweight for lists"""
    id: uuid.UUID
    name: str
    account_name: str
    created_at: datetime

class Resource(ResourceSummary):
    """Resource Model - full details"""
    model_config = ConfigDict(from_attributes=True)

    description: str | None = None
    metadata: dict[str, str]
    created_at: datetime
    updated_at: datetime | None = None

class ListResourcesResponse(BaseModel):
    """List Resources Response"""
    resources: list[ResourceSummary]
    total: int
    total_pages: int
    page: int
    page_size: int
```

## VALIDATION CHECKLIST

When creating schemas, verify:

- ✅ `model_config = ConfigDict(from_attributes=True)` for response models from ORM
- ✅ All timestamps use `datetime` with `timezone.utc`
- ✅ Consistent `str | None` syntax (not `Optional[str]`)
- ✅ All collections fully typed: `dict[str, Any]`, `list[str]`
- ✅ Mutable defaults use `Field(default_factory=...)`
- ✅ Public API fields have `Field(description="...")`
- ✅ Business logic has `@field_validator` or `@model_validator`
- ✅ Create requests inherit from Update requests
- ✅ Required fields use `Field(...)` or no default
- ✅ All schema classes have docstrings
- ✅ Validation returns modified value (e.g., `.strip()`)
- ✅ Cross-field validation uses `@model_validator(mode="after")`
