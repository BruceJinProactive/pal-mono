# Routines System - Technical Design Document

## Overview

The Routines system enables restaurants to manage daily operational tasks with staff accountability and evidence collection. It provides a structured workflow for opening/closing procedures, food safety compliance, and other recurring operational tasks.

**V1 Scope:**
- Photo input only (future: checkbox, number, text, multi-select)
- Project-level routines (future: corporate templates)
- 3-tier architecture (future: Escalation/Alerts tier)
- EventBridge Scheduler for automated execution generation

**Key Principles:**
- Routines define **what** needs to be done (Standard Tier)
- Schedules define **when** and **how often** (Workflow Tier)
- Submissions capture **proof of completion** (Evidence Tier)
- AI-powered photo verification for quality assurance

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STANDARD TIER                                      │
│  Defines WHAT needs to be done                                               │
│                                                                              │
│  ┌──────────────────┐         ┌──────────────────┐                          │
│  │     Routine      │ 1 ──► N │   RoutineItem    │                          │
│  │                  │         │                  │                          │
│  │ - name           │         │ - name           │                          │
│  │ - project_id     │         │ - input_type     │                          │
│  │ - category       │         │ - is_required    │                          │
│  │ - is_active      │         │ - reference_img  │                          │
│  │                  │         │ - ai_rules       │                          │
│  └────────┬─────────┘         └──────────────────┘                          │
│           │                                                                  │
└───────────┼──────────────────────────────────────────────────────────────────┘
            │ 1
            │
            ▼ N
┌─────────────────────────────────────────────────────────────────────────────┐
│                           WORKFLOW TIER                                      │
│  Defines WHEN to complete                                                    │
│                                                                              │
│  ┌──────────────────┐         ┌──────────────────┐                          │
│  │     Schedule     │ 1 ──► N │    Execution     │                          │
│  │                  │         │                  │                          │
│  │ - frequency      │         │ - scheduled_start│                          │
│  │ - start_time     │         │ - scheduled_end  │                          │
│  │ - end_time       │         │ - status         │                          │
│  │ - timezone       │         │ - assigned_user  │                          │
│  │ - days_of_week   │         │                  │                          │
│  └──────────────────┘         └────────┬─────────┘                          │
│                                        │                                     │
└────────────────────────────────────────┼─────────────────────────────────────┘
                                         │ 1
                                         │
                                         ▼ 1
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EVIDENCE TIER                                      │
│  Captures PROOF of completion                                                │
│                                                                              │
│  ┌──────────────────┐         ┌──────────────────┐                          │
│  │    Submission    │ 1 ──► N │  ItemResponse    │                          │
│  │                  │         │                  │                          │
│  │ - status         │         │ - status         │                          │
│  │ - submitted_by   │         │ - image_url      │                          │
│  │ - submitted_at   │         │ - ai_result      │                          │
│  │ - reviewed_by    │         │ - ai_passed      │                          │
│  │ - review_notes   │         │ - notes          │                          │
│  └──────────────────┘         └──────────────────┘                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Relationship Summary:
  Routine (1) ──► (N) RoutineItem     : A routine has many items
  Routine (1) ──► (N) Schedule        : A routine can have multiple schedules
  Schedule (1) ──► (N) Execution      : Each schedule generates many executions
  Execution (1) ──► (1) Submission    : Each execution has one submission
  Submission (1) ──► (N) ItemResponse : Each submission has responses per item
```

---

## Database Schema

### Table: `routines`

**Purpose:** Define routine templates that can be scheduled

```sql
CREATE TABLE routines (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- OWNERSHIP
    project_id      UUID NOT NULL,                    -- References projects.id (no FK)

    -- IDENTITY
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    category        VARCHAR(50) NOT NULL DEFAULT 'custom',  -- enum: RoutineCategory

    -- STATUS
    is_active       BOOLEAN NOT NULL DEFAULT true,

    -- TIMESTAMPS
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX routines_project_id_idx ON routines(project_id);
CREATE UNIQUE INDEX routines_project_name_idx ON routines(project_id, name);
```

**Business Rules:**
- Name must be unique per project
- Deleting a routine cascades to items, schedules, executions, submissions

---

### Table: `routine_items`

**Purpose:** Define individual tasks within a routine

```sql
CREATE TABLE routine_items (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- PARENT
    routine_id          UUID NOT NULL,                    -- References routines.id (no FK)

    -- IDENTITY
    name                VARCHAR(255) NOT NULL,
    description         TEXT,
    sort_order          INTEGER NOT NULL DEFAULT 0,

    -- INPUT CONFIGURATION
    input_type          VARCHAR(50) NOT NULL DEFAULT 'photo',  -- enum: RoutineInputType (V1: photo only)
    is_required         BOOLEAN NOT NULL DEFAULT true,

    -- AI VERIFICATION (for photo type)
    reference_image_url VARCHAR(500),                     -- S3 URL of reference image
    ai_rules            JSONB NOT NULL DEFAULT '{}',      -- AI prompt and rules

    -- CAMERA INTEGRATION (optional)
    signal_source_id    UUID,                             -- References signal_sources.id for auto-verify

    -- TIMESTAMPS
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX routine_items_routine_id_idx ON routine_items(routine_id);
CREATE INDEX routine_items_sort_order_idx ON routine_items(routine_id, sort_order);
```

**AI Rules Structure (JSONB):**
```json
{
  "prompt": "Verify that the prep station is clean and sanitized",
  "pass_criteria": [
    "All surfaces are wiped down",
    "No food debris visible",
    "Sanitizer solution is present"
  ],
  "fail_criteria": [
    "Visible food residue",
    "Dirty towels on surface",
    "Missing sanitizer"
  ],
  "comparison_mode": "reference_match",  // or "checklist"
  "confidence_threshold": 0.8
}
```

---

### Table: `routine_schedules`

**Purpose:** Define when routines should be completed

```sql
CREATE TABLE routine_schedules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- PARENT
    routine_id      UUID NOT NULL,                    -- References routines.id (no FK)

    -- SCHEDULE DEFINITION
    frequency       VARCHAR(50) NOT NULL,             -- enum: RoutineFrequency
    start_time      TIME NOT NULL,                    -- Time of day routine is due
    end_time        TIME NOT NULL,                    -- Grace period end
    timezone        VARCHAR(100) NOT NULL DEFAULT 'America/Los_Angeles',

    -- FREQUENCY-SPECIFIC
    days_of_week    INTEGER[],                        -- For weekly: [0=Sun, 1=Mon, ..., 6=Sat]
    day_of_month    INTEGER,                          -- For monthly: 1-31
    interval_hours  INTEGER,                          -- For custom: hours between executions

    -- DATE RANGE
    effective_from  DATE,                             -- NULL = starts immediately
    effective_until DATE,                             -- NULL = no end date

    -- STATUS
    is_active       BOOLEAN NOT NULL DEFAULT true,

    -- TIMESTAMPS
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX routine_schedules_routine_id_idx ON routine_schedules(routine_id);
CREATE INDEX routine_schedules_active_idx ON routine_schedules(is_active) WHERE is_active = true;
```

**Frequency Examples:**
| Frequency | Configuration |
|-----------|---------------|
| Daily | `frequency: "daily"`, `start_time: "06:00"`, `end_time: "07:00"` |
| Weekly | `frequency: "weekly"`, `days_of_week: [1,3,5]` (Mon/Wed/Fri) |
| Monthly | `frequency: "monthly"`, `day_of_month: 1` (1st of each month) |
| Custom | `frequency: "custom"`, `interval_hours: 4` (every 4 hours) |

---

### Table: `routine_executions`

**Purpose:** Track individual instances of scheduled routines

```sql
CREATE TABLE routine_executions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- PARENTS
    routine_id          UUID NOT NULL,                    -- References routines.id (no FK)
    schedule_id         UUID NOT NULL,                    -- References routine_schedules.id (no FK)

    -- TIMING
    scheduled_start     TIMESTAMP WITH TIME ZONE NOT NULL,  -- When routine becomes due
    scheduled_end       TIMESTAMP WITH TIME ZONE NOT NULL,  -- Grace period deadline

    -- STATUS
    status              VARCHAR(50) NOT NULL DEFAULT 'pending',  -- enum: ExecutionStatus

    -- ASSIGNMENT (optional)
    assigned_user_id    UUID,                             -- References users.id (no FK)

    -- TIMESTAMPS
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX routine_executions_routine_id_idx ON routine_executions(routine_id);
CREATE INDEX routine_executions_schedule_id_idx ON routine_executions(schedule_id);
CREATE INDEX routine_executions_status_idx ON routine_executions(status);
CREATE INDEX routine_executions_scheduled_start_idx ON routine_executions(scheduled_start);

-- Composite index for finding pending executions
CREATE INDEX routine_executions_pending_idx
    ON routine_executions(routine_id, scheduled_start)
    WHERE status = 'pending';
```

**Status Transitions:**
```
pending → in_progress → completed
pending → missed (if not started by scheduled_end)
in_progress → completed
in_progress → missed (if not completed by scheduled_end + grace)
```

---

### Table: `routine_submissions`

**Purpose:** Capture staff submissions for routine executions

```sql
CREATE TABLE routine_submissions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- PARENT
    execution_id        UUID NOT NULL UNIQUE,             -- References routine_executions.id (no FK)

    -- SUBMISSION STATUS
    status              VARCHAR(50) NOT NULL DEFAULT 'draft',  -- enum: SubmissionStatus

    -- STAFF INFO
    submitted_by        UUID,                             -- References users.id (no FK)
    submitted_at        TIMESTAMP WITH TIME ZONE,

    -- MANAGER REVIEW
    reviewed_by         UUID,                             -- References users.id (no FK)
    reviewed_at         TIMESTAMP WITH TIME ZONE,
    review_notes        TEXT,

    -- TIMESTAMPS
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE UNIQUE INDEX routine_submissions_execution_id_idx ON routine_submissions(execution_id);
CREATE INDEX routine_submissions_status_idx ON routine_submissions(status);
CREATE INDEX routine_submissions_submitted_by_idx ON routine_submissions(submitted_by);
```

**Status Flow:**
```
draft → submitted → approved
draft → submitted → rejected → draft (resubmit)
```

---

### Table: `routine_item_responses`

**Purpose:** Store evidence for each item in a submission

```sql
CREATE TABLE routine_item_responses (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- PARENTS
    submission_id       UUID NOT NULL,                    -- References routine_submissions.id (no FK)
    routine_item_id     UUID NOT NULL,                    -- References routine_items.id (no FK)

    -- RESPONSE DATA (V1: photo only)
    image_url           VARCHAR(500),                     -- S3 URL of uploaded image
    notes               TEXT,                             -- Staff notes/comments

    -- AI VERIFICATION RESULTS
    ai_result           JSONB,                            -- AI analysis output
    ai_passed           BOOLEAN,                          -- Quick pass/fail flag
    ai_confidence       DECIMAL(3,2),                     -- Confidence score 0.00-1.00

    -- STATUS
    status              VARCHAR(50) NOT NULL DEFAULT 'pending',  -- pending, passed, failed, skipped

    -- TIMESTAMPS
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX routine_item_responses_submission_id_idx ON routine_item_responses(submission_id);
CREATE INDEX routine_item_responses_routine_item_id_idx ON routine_item_responses(routine_item_id);
CREATE UNIQUE INDEX routine_item_responses_unique_idx
    ON routine_item_responses(submission_id, routine_item_id);
```

**AI Result Structure (JSONB):**
```json
{
  "analysis_type": "ai_vision",
  "result": "pass",
  "confidence": 0.92,
  "finding": "Prep station is clean and properly sanitized",
  "details": {
    "criteria_met": [
      "All surfaces are wiped down",
      "Sanitizer solution is present"
    ],
    "criteria_not_met": [],
    "observations": "Station appears ready for food preparation"
  },
  "model": "claude-3.5-sonnet",
  "processing_time_ms": 2340
}
```

---

## Enums

Location: `db/tables/types.py`

```python
import enum

class RoutineCategory(str, enum.Enum):
    """Category of routine"""
    opening = "opening"
    closing = "closing"
    food_safety = "food_safety"
    cleaning = "cleaning"
    compliance = "compliance"
    custom = "custom"

class RoutineInputType(str, enum.Enum):
    """Type of input for routine items (V1: photo only)"""
    photo = "photo"
    # Future:
    # checkbox = "checkbox"
    # number = "number"
    # text = "text"
    # multi_select = "multi_select"

class RoutineFrequency(str, enum.Enum):
    """Frequency of routine schedules"""
    once = "once"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    custom = "custom"

class ExecutionStatus(str, enum.Enum):
    """Status of routine executions"""
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    missed = "missed"

class SubmissionStatus(str, enum.Enum):
    """Status of routine submissions"""
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"

class ItemResponseStatus(str, enum.Enum):
    """Status of individual item responses"""
    pending = "pending"
    passed = "passed"
    failed = "failed"
    skipped = "skipped"
```

---

## Configuration Schemas

Location: `api/schemas/operations/routine.py`

### Routine Item AI Rules Config

```python
from typing import Literal, Optional
from pydantic import BaseModel, Field

class AIRulesConfig(BaseModel):
    """Configuration for AI-powered photo verification"""
    prompt: str = Field(..., description="Main prompt for AI analysis")
    pass_criteria: list[str] = Field(
        default_factory=list,
        description="Criteria that indicate a passing result"
    )
    fail_criteria: list[str] = Field(
        default_factory=list,
        description="Criteria that indicate a failing result"
    )
    comparison_mode: Literal["reference_match", "checklist"] = Field(
        default="checklist",
        description="How to evaluate: compare to reference image or check criteria list"
    )
    confidence_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score to trust AI result"
    )
```

### Schedule Config

```python
class ScheduleConfig(BaseModel):
    """Configuration for routine scheduling"""
    frequency: RoutineFrequency
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="HH:MM format")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="HH:MM format")
    timezone: str = Field(default="America/Los_Angeles")

    # Frequency-specific
    days_of_week: list[int] | None = Field(
        default=None,
        description="For weekly: [0=Sun, 1=Mon, ..., 6=Sat]"
    )
    day_of_month: int | None = Field(
        default=None,
        ge=1,
        le=31,
        description="For monthly: day of month"
    )
    interval_hours: int | None = Field(
        default=None,
        ge=1,
        le=24,
        description="For custom: hours between executions"
    )
```

---

## API Endpoints

### Base Path: `/v1/operations`

### Routine Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/projects/{project_id}/routines` | Create routine |
| `GET` | `/projects/{project_id}/routines` | List routines |
| `GET` | `/routines/{routine_id}` | Get routine with items |
| `PATCH` | `/routines/{routine_id}` | Update routine |
| `DELETE` | `/routines/{routine_id}` | Delete routine |

#### Create Routine

```
POST /v1/operations/projects/{project_id}/routines
```

**Request:**
```json
{
  "name": "Opening Routine",
  "description": "Daily opening tasks",
  "category": "opening",
  "items": [
    {
      "name": "Check walk-in cooler temperature",
      "description": "Verify temperature is between 35-40°F",
      "input_type": "photo",
      "is_required": true,
      "ai_rules": {
        "prompt": "Verify the thermometer shows temperature between 35-40°F",
        "pass_criteria": ["Temperature reading visible", "Reading is between 35-40"],
        "comparison_mode": "checklist"
      }
    }
  ],
  "schedule": {
    "frequency": "daily",
    "start_time": "06:00",
    "end_time": "07:00",
    "timezone": "America/Los_Angeles"
  }
}
```

**Response:** `201 Created`

---

### Routine Items

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/routines/{routine_id}/items` | Add item |
| `PATCH` | `/routine-items/{item_id}` | Update item |
| `DELETE` | `/routine-items/{item_id}` | Delete item |
| `POST` | `/routine-items/{item_id}/reference-image` | Upload reference image |

---

### Schedules

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/routines/{routine_id}/schedules` | Create schedule |
| `GET` | `/routines/{routine_id}/schedules` | List schedules |
| `PATCH` | `/schedules/{schedule_id}` | Update schedule |
| `DELETE` | `/schedules/{schedule_id}` | Delete schedule |

---

### Executions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/projects/{project_id}/executions` | List executions (with filters) |
| `GET` | `/executions/{execution_id}` | Get execution details |

**Query Parameters for List:**
- `status`: Filter by status (pending, in_progress, completed, missed)
- `date`: Filter by scheduled date (YYYY-MM-DD)
- `routine_id`: Filter by specific routine

---

### Submissions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/executions/{execution_id}/submissions` | Start submission (creates draft) |
| `GET` | `/submissions/{submission_id}` | Get submission with responses |
| `POST` | `/submissions/{submission_id}/submit` | Finalize and submit for review |

#### Start Submission

```
POST /v1/operations/executions/{execution_id}/submissions
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "execution_id": "uuid",
  "status": "draft",
  "items": [
    {
      "routine_item_id": "uuid",
      "name": "Check walk-in cooler temperature",
      "is_required": true,
      "response": null
    }
  ],
  "created_at": "2025-01-15T06:05:00Z"
}
```

---

### Item Responses

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/submissions/{submission_id}/responses` | Add/update response with image |
| `GET` | `/item-responses/{response_id}` | Get response details |

#### Add Response (multipart/form-data)

```
POST /v1/operations/submissions/{submission_id}/responses
Content-Type: multipart/form-data

routine_item_id: uuid
image: <file>
notes: "Temperature at 38°F"
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "routine_item_id": "uuid",
  "image_url": "s3://bucket/routines/...",
  "notes": "Temperature at 38°F",
  "status": "pending",
  "ai_result": null,
  "ai_passed": null
}
```

**Note:** AI verification runs asynchronously. Poll or use webhooks to get results.

---

### Manager Review

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/projects/{project_id}/submissions/pending-review` | List submissions awaiting review |
| `POST` | `/submissions/{submission_id}/approve` | Approve submission |
| `POST` | `/submissions/{submission_id}/reject` | Reject with notes |

#### Reject Submission

```
POST /v1/operations/submissions/{submission_id}/reject
```

**Request:**
```json
{
  "review_notes": "Photo of cooler temperature is blurry, please retake"
}
```

---

## Service Layer

Location: `services/`

### routine_service

```python
# services/routine_service/__init__.py

async def create_routine(session, project_id, request) -> Routine
async def get_routine(session, routine_id) -> Routine
async def list_routines(session, project_id) -> list[Routine]
async def update_routine(session, routine_id, request) -> Routine
async def delete_routine(session, routine_id) -> None

# Items
async def add_item(session, routine_id, request) -> RoutineItem
async def update_item(session, item_id, request) -> RoutineItem
async def delete_item(session, item_id) -> None
async def upload_reference_image(session, item_id, file) -> str  # Returns S3 URL
```

### schedule_service

```python
# services/schedule_service/__init__.py

async def create_schedule(session, routine_id, request) -> RoutineSchedule
async def list_schedules(session, routine_id) -> list[RoutineSchedule]
async def update_schedule(session, schedule_id, request) -> RoutineSchedule
async def delete_schedule(session, schedule_id) -> None
```

### execution_service

```python
# services/execution_service/__init__.py

async def generate_executions_for_date(session, project_id, date) -> list[RoutineExecution]
async def get_execution(session, execution_id) -> RoutineExecution
async def list_executions(session, project_id, filters) -> list[RoutineExecution]
async def update_execution_status(session, execution_id, status) -> RoutineExecution
async def mark_overdue_as_missed(session, project_id) -> int  # Returns count
```

### submission_service

```python
# services/submission_service/__init__.py

# Staff workflow
async def start_submission(session, execution_id, user_id) -> RoutineSubmission
async def add_response(session, submission_id, item_id, file, notes) -> RoutineItemResponse
async def submit_for_review(session, submission_id, user_id) -> RoutineSubmission

# Manager workflow
async def list_pending_review(session, project_id) -> list[RoutineSubmission]
async def approve_submission(session, submission_id, reviewer_id) -> RoutineSubmission
async def reject_submission(session, submission_id, reviewer_id, notes) -> RoutineSubmission

# AI processing
async def process_response_ai(session, response_id) -> RoutineItemResponse
```

---

## Scheduler Integration

### EventBridge Scheduler

Daily execution generation is triggered by EventBridge Scheduler:

```json
{
  "Name": "generate-routine-executions",
  "ScheduleExpression": "cron(0 0 * * ? *)",
  "Target": {
    "Arn": "arn:aws:lambda:...:generate-executions",
    "Input": "{\"scope\": \"all_projects\"}"
  }
}
```

### Lambda Handler

```python
# lambdas/generate_routine_executions.py

async def handler(event, context):
    """
    Generate routine executions for today based on schedules.
    Runs daily at midnight UTC.
    """
    today = datetime.now(UTC).date()

    async with get_session() as session:
        # Get all active schedules
        schedules = await schedule_repository.get_active_schedules(session)

        for schedule in schedules:
            if should_execute_today(schedule, today):
                await execution_service.create_execution(
                    session=session,
                    routine_id=schedule.routine_id,
                    schedule_id=schedule.id,
                    scheduled_start=calculate_start_time(schedule, today),
                    scheduled_end=calculate_end_time(schedule, today),
                )

        await session.commit()

    return {"executions_created": len(schedules)}
```

### Missed Execution Detection

Separate scheduled job to mark overdue executions as missed:

```python
# Runs every 15 minutes
async def mark_missed_executions():
    async with get_session() as session:
        count = await execution_service.mark_overdue_as_missed(session)
        await session.commit()
    return {"marked_missed": count}
```

---

## AI Integration

### Photo Verification Flow

```
┌─────────────────┐
│ Staff uploads   │
│ photo           │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Save to S3      │
│ Create response │
│ status: pending │
└────────┬────────┘
         │
         ▼ (async)
┌─────────────────┐
│ AI Service      │
│ - Load image    │
│ - Load rules    │
│ - Call Claude   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Update response │
│ ai_result: {}   │
│ ai_passed: bool │
│ status: passed/ │
│         failed  │
└─────────────────┘
```

### Vision Service Integration

```python
# services/submission_service/_ai.py

async def process_response_ai(session, response_id):
    response = await get_response(session, response_id)
    item = await get_routine_item(session, response.routine_item_id)

    # Skip if no AI rules configured
    if not item.ai_rules:
        return

    # Call vision service
    result = await vision_service.analyze_image(
        image_url=response.image_url,
        reference_url=item.reference_image_url,
        prompt=item.ai_rules.get("prompt"),
        pass_criteria=item.ai_rules.get("pass_criteria", []),
        fail_criteria=item.ai_rules.get("fail_criteria", []),
    )

    # Update response
    response.ai_result = result
    response.ai_passed = result.get("result") == "pass"
    response.ai_confidence = result.get("confidence")
    response.status = "passed" if response.ai_passed else "failed"

    await session.commit()
    return response
```

---

## Files to Create

### Database Layer

| File | Purpose |
|------|---------|
| `db/tables/routines.py` | Routine model |
| `db/tables/routine_items.py` | RoutineItem model |
| `db/tables/routine_schedules.py` | RoutineSchedule model |
| `db/tables/routine_executions.py` | RoutineExecution model |
| `db/tables/routine_submissions.py` | RoutineSubmission model |
| `db/tables/routine_item_responses.py` | RoutineItemResponse model |
| `db/tables/types.py` | Add routine enums |

### Repository Layer

| File | Purpose |
|------|---------|
| `db/repositories/routine_repository.py` | Routine + Item CRUD |
| `db/repositories/routine_schedule_repository.py` | Schedule CRUD |
| `db/repositories/routine_execution_repository.py` | Execution queries |
| `db/repositories/routine_submission_repository.py` | Submission + Response CRUD |

### Service Layer

| File | Purpose |
|------|---------|
| `services/routine_service/__init__.py` | Routine management |
| `services/schedule_service/__init__.py` | Schedule management |
| `services/execution_service/__init__.py` | Execution generation |
| `services/submission_service/__init__.py` | Staff & manager workflows |

### API Layer

| File | Purpose |
|------|---------|
| `api/routes/operation/_routines.py` | Route implementations |
| `api/schemas/operations/routine.py` | Request/response schemas |

### Scheduler

| File | Purpose |
|------|---------|
| `lambdas/generate_routine_executions.py` | Daily execution generator |
| `lambdas/mark_missed_executions.py` | Missed detection job |

---

## Future Enhancements

### Phase 2: Additional Input Types
- Checkbox, number, text, multi-select inputs
- Validation rules per input type
- Numeric threshold checking

### Phase 3: Corporate Templates
- Account-level routine templates
- Copy-on-customize for stores
- Template versioning

### Phase 4: Alerts & Escalation
- `routine_alerts` table
- Overdue, missed, flagged_item, rejected alert types
- Email/SMS/voice notifications
- Escalation chains

### Phase 5: Advanced Features
- Staff assignment and rotation
- Location verification (GPS)
- Offline support with sync
- Analytics and compliance reports
