# Google Business Hours Updater - Detailed Implementation

## Overview

The Google Business Hours Updater automatically syncs restaurant business hours from Google Places API to both the database and knowledge base. This ensures AI agents have accurate, up-to-date information about:
- Regular operating hours (weekly schedule)
- Special hours (holidays, temporary closures)
- Current open/closed status
- Phone numbers and contact information

## Business Value

**For AI Agents:**
- Answer "Are you open now?" with 100% accuracy
- Provide correct hours when customers ask "What time do you close?"
- Inform customers about holiday closures proactively
- Avoid sending orders when restaurant is closed

**For Restaurant Operators:**
- No manual hours updates needed - syncs from Google automatically
- Single source of truth (Google Business Profile)
- Reduces customer confusion and missed orders
- Always shows accurate information across all channels

## Existing Infrastructure

### Google Maps Service (Already Built!)

**Location:** `/services/google_maps_service/`

The codebase already has a comprehensive Google Maps service with:
- Place search by text query
- Place details retrieval (including opening hours)
- Timezone identification
- Phone number formatting
- API key management
- Error handling

**Key Components:**

**Schemas (`schemas.py`):**
```python
class OpeningHours(BaseModel):
    open_now: Optional[bool]
    periods: Optional[List[dict]]  # Structured schedule
    weekday_text: Optional[List[str]]  # Human-readable format

class PlaceResult(BaseModel):
    place_id: str
    name: str
    formatted_address: str
    formatted_phone_number: Optional[str]
    opening_hours: Optional[OpeningHours]
    # ... more fields
```

**Implementation (`_implementation.py`):**
```python
async def get_place_details_by_place_id(place_id: str) -> PlaceResult:
    """Get detailed place information from Google Places API."""
    api_key = _get_api_key()

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,formatted_phone_number,opening_hours,website,...",
        "key": api_key
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        # ... error handling, parsing
```

### Missing Pieces

1. **Database Storage:** `projects` table has no `google_place_id` field (each store location needs its own place ID)
2. **Scheduled Updates:** No automated sync mechanism
3. **Knowledge Base Integration:** Opening hours not stored in Pinecone
4. **Event-Driven Architecture:** Not using EventBridge pattern
5. **Structured Hours:** Current `store_hours` field is plain text, not structured JSONB

## Proposed Architecture

### Components

```
┌────────────────────────────────────────────────────────────────┐
│  EventBridge Scheduler                                          │
│  Rule: pal-daily-business-hours-update                         │
│  Schedule: cron(0 4 * * ? *)  # 4 AM UTC daily                │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     │ POST /v1/internal/scheduled/business-hours-update
                     │ Headers: X-API-Key: ***
                     ▼
┌────────────────────────────────────────────────────────────────┐
│  Internal API: Discovery Endpoint                              │
│  File: /api/routes/internal/scheduled.py                       │
│                                                                  │
│  1. Query all projects with google_place_id                     │
│  2. Filter projects that need updates (24h threshold)           │
│  3. For each project:                                            │
│     - Publish GoogleBusinessHoursUpdateRequested event          │
│  4. Return summary: {total_queued: N}                          │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     │ Publish N events (one per store/project)
                     ▼
┌────────────────────────────────────────────────────────────────┐
│  EventBridge: pal-main-event-bus                               │
│  DetailType: integration.google.BusinessHoursUpdateRequested   │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     │ N parallel invocations
                     ▼
┌────────────────────────────────────────────────────────────────┐
│  Lambda: google-business-hours-updater                          │
│  Runtime: Python 3.12                                            │
│  Timeout: 2 minutes                                              │
│  Concurrency: 3 (reserved, respect API quotas)                  │
│                                                                  │
│  1. Parse event (project_id, place_id, namespace)              │
│  2. Call Google Places API for place details                    │
│  3. Extract opening_hours, phone, etc.                          │
│  4. POST /v1/internal/projects/{id}/business-hours             │
│     - Updates projects table with structured hours              │
│  5. POST /v1/internal/knowledge/{project_id}/business-hours    │
│     - Updates Pinecone with natural language hours              │
│  6. Log metrics to Datadog for observability                    │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     │ POST with hours data
                     ▼
┌────────────────────────────────────────────────────────────────┐
│  Internal API: Project & Knowledge Update Endpoints            │
│  Files: /api/routes/internal/projects.py                       │
│         /api/routes/internal/knowledge.py                       │
│                                                                  │
│  Project Update:                                                 │
│  1. Validate project exists                                      │
│  2. Update projects.business_hours (JSONB)                      │
│  3. Update projects.business_hours_last_updated                 │
│  4. Update projects.store_hours (human-readable text)           │
│  5. Commit transaction                                           │
│                                                                  │
│  Knowledge Update:                                               │
│  1. Validate project exists and has namespace                   │
│  2. Convert hours to natural language                            │
│  3. Query Pinecone for existing hours (metadata filter)         │
│  4. Compare old vs new                                           │
│  5. If different:                                                │
│     - Delete old vectors                                         │
│     - Upload new hours document                                  │
│  6. Return result                                                │
└────────────────────────────────────────────────────────────────┘
```

## Database Changes

### Schema Migration

**File:** `db/migrations/YYYYMMDD_add_google_place_id_to_projects.py`

```sql
-- Add google_place_id to projects (each store location has its own place ID)
ALTER TABLE projects
ADD COLUMN google_place_id VARCHAR(255),
ADD COLUMN business_hours JSONB,
ADD COLUMN business_hours_last_updated TIMESTAMP WITH TIME ZONE;

-- Add index for faster lookups
CREATE INDEX idx_projects_google_place_id
ON projects(google_place_id)
WHERE google_place_id IS NOT NULL;

-- Add index for update discovery (find stale hours)
CREATE INDEX idx_projects_business_hours_last_updated
ON projects(business_hours_last_updated)
WHERE google_place_id IS NOT NULL;

-- Add comments
COMMENT ON COLUMN projects.google_place_id IS
'Google Places ID for this store location. Used to sync business hours from Google Business Profile.';

COMMENT ON COLUMN projects.business_hours IS
'Structured business hours data from Google Places API. Format: {regular_hours: {...}, special_hours: [...], open_now: bool, last_fetched: ISO8601}. Updated daily via automated sync.';

COMMENT ON COLUMN projects.business_hours_last_updated IS
'Timestamp of last successful business hours sync from Google Places API.';

-- Note: store_hours field already exists as VARCHAR, will be updated with human-readable hours
COMMENT ON COLUMN projects.store_hours IS
'Human-readable business hours text. Auto-updated from business_hours JSONB field.';
```

### Business Hours Data Structure

**projects.business_hours JSONB format:**

```json
{
  "source": "google_places",
  "place_id": "ChIJ...",
  "last_fetched": "2025-01-12T04:15:32Z",

  "regular_hours": {
    "open_now": true,
    "periods": [
      {
        "open": {"day": 1, "time": "0900"},
        "close": {"day": 1, "time": "1700"}
      },
      {
        "open": {"day": 2, "time": "0900"},
        "close": {"day": 2, "time": "1700"}
      }
    ],
    "weekday_text": [
      "Monday: 9:00 AM – 5:00 PM",
      "Tuesday: 9:00 AM – 5:00 PM",
      "Wednesday: 9:00 AM – 5:00 PM",
      "Thursday: 9:00 AM – 5:00 PM",
      "Friday: 9:00 AM – 5:00 PM",
      "Saturday: Closed",
      "Sunday: Closed"
    ]
  },

  "special_hours": [
    {
      "date": "2025-01-01",
      "closed": true,
      "description": "New Year's Day"
    },
    {
      "date": "2025-12-25",
      "closed": true,
      "description": "Christmas Day"
    }
  ],

  "phone_number": "+1 555-123-4567",
  "formatted_phone_number": "(555) 123-4567",
  "website": "https://restaurant.com"
}
```

### Repository Methods

**File:** `db/repositories/project_repository.py` (add methods)

```python
def get_projects_with_google_place_id(self) -> List[Project]:
    """Get all projects (stores) that have a google_place_id configured."""
    return self.session.query(Project).filter(
        Project.google_place_id.isnot(None),
        Project.google_place_id != ''
    ).all()


def update_project_business_hours(
    self,
    project_id: UUID,
    business_hours: dict,
    last_updated: datetime
) -> Project:
    """Update business hours for a project (store location)."""
    project = self.get_project_by_id(project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    project.business_hours = business_hours
    project.business_hours_last_updated = last_updated
    project.updated_at = datetime.now(timezone.utc)

    # Also update the human-readable store_hours field
    weekday_text = business_hours.get('regular_hours', {}).get('weekday_text', [])
    if weekday_text:
        project.store_hours = '\n'.join(weekday_text)

    self.session.commit()
    self.session.refresh(project)

    return project


def get_projects_needing_hours_update(
    self,
    hours_threshold: int = 24
) -> List[Project]:
    """
    Get projects whose hours haven't been updated recently.

    Args:
        hours_threshold: Hours since last update
    """
    threshold_time = datetime.now(timezone.utc) - timedelta(hours=hours_threshold)

    return self.session.query(Project).filter(
        Project.google_place_id.isnot(None),
        or_(
            Project.business_hours_last_updated.is_(None),
            Project.business_hours_last_updated < threshold_time
        )
    ).all()
```

## Implementation Details

### Phase 1: Event Schemas

**File:** `/events/schema.py` (add to existing)

```python
@dataclass
class GoogleBusinessHoursUpdateRequested(BaseEvent):
    """Event published when business hours need updating from Google for a specific store."""

    detail_type: ClassVar[str] = "integration.google.BusinessHoursUpdateRequested"

    # Resource identifiers
    project_id: UUID  # The store/location
    project_name: str
    account_id: UUID  # Parent account (for context)
    account_name: str
    google_place_id: str

    # Knowledge base info
    namespace: Optional[str] = None  # Pinecone namespace for this project

    # Metadata
    requested_at: datetime
    requested_by: str = "scheduler"  # or "manual"
    last_updated: Optional[datetime] = None  # When hours were last fetched


```

### Phase 2: Discovery Endpoint

**File:** `/api/routes/internal/scheduled.py` (add to existing)

```python
@scheduled_router.post("/business-hours-update")
async def trigger_business_hours_update(
    force_update: bool = False,  # Update all, even if recently updated
    session: Session = Depends(get_db),
    _: bool = Depends(validate_api_key)
):
    """
    Discovery endpoint for business hours updates.

    Queries database for projects (stores) with Google Place IDs and publishes events.
    Called by EventBridge Scheduler daily.
    """
    project_repo = ProjectRepository(session)

    try:
        # Get projects needing updates
        if force_update:
            projects = project_repo.get_projects_with_google_place_id()
        else:
            # Only update if not updated in last 24 hours
            projects = project_repo.get_projects_needing_hours_update(hours_threshold=24)

        events_published = 0
        skipped = 0
        errors = []

        for project in projects:
            # Skip if missing place_id
            if not project.google_place_id:
                skipped += 1
                continue

            # Skip if no namespace (can't update KB)
            if not project.namespace:
                skipped += 1
                logger.warning(
                    f"Skipping project {project.id}: no namespace configured"
                )
                continue

            # Get account info for context
            account = project.account

            try:
                # Publish event for this store/project
                event = GoogleBusinessHoursUpdateRequested(
                    project_id=project.id,
                    project_name=project.name,
                    account_id=account.id,
                    account_name=account.name,
                    google_place_id=project.google_place_id,
                    namespace=project.namespace,
                    requested_at=datetime.now(timezone.utc),
                    requested_by="scheduler",
                    last_updated=project.business_hours_last_updated
                )

                success = await publish_event(event)

                if success:
                    events_published += 1
                    logger.info(
                        f"Published hours update event for project {project.id}",
                        extra={
                            "project_id": str(project.id),
                            "account_id": str(account.id),
                            "place_id": project.google_place_id
                        }
                    )
                else:
                    errors.append(
                        f"Failed to publish event for project {project.id}"
                    )

            except Exception as e:
                errors.append(
                    f"Error processing project {project.id}: {str(e)}"
                )
                logger.error(
                    f"Error processing project {project.id}",
                    exc_info=True,
                    extra={"project_id": str(project.id)}
                )

        # Return summary
        return {
            "success": True,
            "total_projects": len(projects),
            "events_published": events_published,
            "skipped": skipped,
            "errors": errors,
            "force_update": force_update
        }

    except Exception as e:
        logger.error("Error in business hours update discovery", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger hours update: {str(e)}"
        )
```

### Phase 3: Lambda Function

**File:** `lambdas/google_business_hours_updater/handler.py` (new Lambda project)

```python
import json
import os
import requests
from datetime import datetime, timezone
from typing import Dict, Any, List
import logging
from datadog_lambda.metric import lambda_metric
from datadog_lambda.wrapper import datadog_lambda_wrapper

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
INTERNAL_API_URL = os.environ['INTERNAL_API_URL']
INTERNAL_API_KEY = os.environ['INTERNAL_API_KEY']
GOOGLE_MAPS_API_KEY = os.environ['GOOGLE_MAPS_API_KEY']
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')


@datadog_lambda_wrapper
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for business hours update.

    Receives GoogleBusinessHoursUpdateRequested event from EventBridge.
    """
    start_time = datetime.now(timezone.utc)
    request_id = context.request_id

    try:
        # Parse event
        detail = event['detail']
        project_id = detail['project_id']
        project_name = detail['project_name']
        account_id = detail['account_id']
        account_name = detail['account_name']
        place_id = detail['google_place_id']
        namespace = detail.get('namespace')

        logger.info(
            f"Processing hours update for project {project_id}",
            extra={
                "project_id": project_id,
                "account_id": account_id,
                "place_id": place_id
            }
        )

        # Fetch place details from Google
        place_data = fetch_place_details(place_id)

        # Extract hours and other info
        hours_data = extract_business_hours(place_data)

        # Update project via internal API
        project_update_result = update_project_hours_via_api(
            project_id=project_id,
            hours_data=hours_data
        )

        # Update knowledge base
        kb_updated = False
        if namespace:
            try:
                kb_result = update_knowledge_base_via_api(
                    project_id=project_id,
                    namespace=namespace,
                    hours_data=hours_data,
                    project_name=project_name
                )
                kb_updated = kb_result.get('updated', False)
            except Exception as e:
                logger.error(
                    f"Failed to update KB for project {project_id}",
                    exc_info=True,
                    extra={"project_id": project_id}
                )
                # Don't fail entire operation if KB update fails
                lambda_metric(
                    "business_hours_updater.kb_update_failed",
                    1,
                    tags=[
                        f"environment:{ENVIRONMENT}",
                        f"account_id:{account_id}",
                        f"project_id:{project_id}"
                    ]
                )

        # Calculate duration
        duration_ms = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )

        # Log success metrics to Datadog
        lambda_metric(
            "business_hours_updater.success",
            1,
            tags=[
                f"environment:{ENVIRONMENT}",
                f"account_id:{account_id}",
                f"project_id:{project_id}"
            ]
        )

        lambda_metric(
            "business_hours_updater.duration",
            duration_ms,
            tags=[
                f"environment:{ENVIRONMENT}",
                f"account_id:{account_id}"
            ]
        )

        if project_update_result.get('hours_changed', False):
            lambda_metric(
                "business_hours_updater.hours_changed",
                1,
                tags=[
                    f"environment:{ENVIRONMENT}",
                    f"account_id:{account_id}",
                    f"project_id:{project_id}"
                ]
            )

        if kb_updated:
            lambda_metric(
                "business_hours_updater.kb_updated",
                1,
                tags=[
                    f"environment:{ENVIRONMENT}",
                    f"account_id:{account_id}",
                    f"project_id:{project_id}"
                ]
            )

        logger.info(
            f"Successfully updated hours for project {project_id}",
            extra={
                "project_id": project_id,
                "account_id": account_id,
                "hours_changed": project_update_result.get('hours_changed', False),
                "kb_updated": kb_updated,
                "duration_ms": duration_ms
            }
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "project_id": project_id,
                "hours_updated": project_update_result.get('hours_changed', False),
                "knowledge_base_updated": kb_updated
            })
        }

    except Exception as e:
        logger.error(
            f"Error updating hours: {str(e)}",
            exc_info=True,
            extra={
                "account_id": detail.get('account_id'),
                "project_id": detail.get('project_id'),
                "error": str(e)
            }
        )

        # Calculate duration
        duration_ms = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )

        # Log failure metrics to Datadog
        lambda_metric(
            "business_hours_updater.error",
            1,
            tags=[
                f"environment:{ENVIRONMENT}",
                f"account_id:{detail.get('account_id', 'unknown')}",
                f"error_type:{type(e).__name__}"
            ]
        )

        lambda_metric(
            "business_hours_updater.duration",
            duration_ms,
            tags=[
                f"environment:{ENVIRONMENT}",
                f"account_id:{detail.get('account_id', 'unknown')}",
                "status:error"
            ]
        )

        # Re-raise to trigger Lambda retry
        raise


def fetch_place_details(place_id: str) -> Dict[str, Any]:
    """Fetch place details from Google Places API."""
    url = "https://maps.googleapis.com/maps/api/place/details/json"

    params = {
        "place_id": place_id,
        "fields": "name,opening_hours,current_opening_hours,formatted_phone_number,international_phone_number,website",
        "key": GOOGLE_MAPS_API_KEY
    }

    response = requests.get(url, params=params, timeout=30)

    if response.status_code != 200:
        raise Exception(
            f"Google Places API error: {response.status_code} - {response.text}"
        )

    data = response.json()

    if data.get('status') != 'OK':
        raise Exception(
            f"Google Places API error: {data.get('status')} - {data.get('error_message', 'Unknown error')}"
        )

    return data.get('result', {})


def extract_business_hours(place_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and structure business hours from Google Place data.

    Returns structured hours data compatible with our database schema.
    """
    hours_data = {
        "source": "google_places",
        "place_id": place_data.get('place_id'),
        "last_fetched": datetime.now(timezone.utc).isoformat()
    }

    # Regular hours
    opening_hours = place_data.get('opening_hours', {})
    if opening_hours:
        hours_data['regular_hours'] = {
            "open_now": opening_hours.get('open_now'),
            "periods": opening_hours.get('periods', []),
            "weekday_text": opening_hours.get('weekday_text', [])
        }

    # Current hours (includes special hours/holidays)
    current_hours = place_data.get('current_opening_hours', {})
    if current_hours:
        special_days = current_hours.get('special_days', [])
        if special_days:
            hours_data['special_hours'] = special_days

    # Phone numbers
    if place_data.get('formatted_phone_number'):
        hours_data['formatted_phone_number'] = place_data['formatted_phone_number']
    if place_data.get('international_phone_number'):
        hours_data['phone_number'] = place_data['international_phone_number']

    # Website
    if place_data.get('website'):
        hours_data['website'] = place_data['website']

    return hours_data


def update_project_hours_via_api(
    project_id: str,
    hours_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Update project business hours via internal API."""
    url = f"{INTERNAL_API_URL}/v1/internal/projects/{project_id}/business-hours"

    response = requests.post(
        url,
        json=hours_data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": INTERNAL_API_KEY
        },
        timeout=30
    )

    if response.status_code != 200:
        raise Exception(
            f"Internal API error: {response.status_code} - {response.text}"
        )

    return response.json()


def update_knowledge_base_via_api(
    project_id: str,
    namespace: str,
    hours_data: Dict[str, Any],
    project_name: str
) -> Dict[str, Any]:
    """Update knowledge base with business hours via internal API."""
    url = f"{INTERNAL_API_URL}/v1/internal/knowledge/{project_id}/business-hours"

    # Convert hours to natural language
    natural_language_hours = format_hours_natural_language(
        hours_data,
        project_name
    )

    response = requests.post(
        url,
        json={
            "hours_text": natural_language_hours,
            "hours_data": hours_data,
            "namespace": namespace
        },
        headers={
            "Content-Type": "application/json",
            "X-API-Key": INTERNAL_API_KEY
        },
        timeout=60
    )

    if response.status_code != 200:
        raise Exception(
            f"Internal API error: {response.status_code} - {response.text}"
        )

    return response.json()


def format_hours_natural_language(
    hours_data: Dict[str, Any],
    location_name: str
) -> str:
    """
    Convert structured hours to natural language for better RAG retrieval.

    Example output:
    "Downtown Store business hours:
    Monday through Friday from 9:00 AM to 5:00 PM,
    and Saturday from 10:00 AM to 8:00 PM. We are closed on Sundays.

    We will be closed on January 1st for New Year's Day and December 25th
    for Christmas.

    You can reach us at (555) 123-4567."
    """
    parts = []

    # Location name
    parts.append(f"{location_name} business hours:")

    # Regular hours
    regular_hours = hours_data.get('regular_hours', {})
    weekday_text = regular_hours.get('weekday_text', [])

    if weekday_text:
        parts.append("\nRegular Hours:")
        for day_hours in weekday_text:
            parts.append(f"- {day_hours}")

    # Current status
    open_now = regular_hours.get('open_now')
    if open_now is not None:
        status = "currently open" if open_now else "currently closed"
        parts.append(f"\nWe are {status}.")

    # Special hours/closures
    special_hours = hours_data.get('special_hours', [])
    if special_hours:
        parts.append("\nSpecial Hours:")
        for special in special_hours:
            date = special.get('date', 'Unknown date')
            description = special.get('description', 'Closed')
            parts.append(f"- {date}: {description}")

    # Phone number
    phone = hours_data.get('formatted_phone_number')
    if phone:
        parts.append(f"\nPhone: {phone}")

    # Website
    website = hours_data.get('website')
    if website:
        parts.append(f"Website: {website}")

    return "\n".join(parts)


```

**Lambda Dependencies (`requirements.txt`):**
```
requests==2.31.0
datadog-lambda==6.96.0
```

### Phase 4: Project Update Endpoint

**File:** `/api/routes/internal/projects.py` (new file or add to existing)

```python
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
from datetime import datetime, timezone

from db import get_db
from db.repositories.project_repository import ProjectRepository

logger = logging.getLogger(__name__)

projects_router = APIRouter()


class UpdateBusinessHoursRequest(BaseModel):
    source: str
    place_id: Optional[str] = None
    last_fetched: str
    regular_hours: Optional[Dict[str, Any]] = None
    special_hours: Optional[list] = None
    formatted_phone_number: Optional[str] = None
    phone_number: Optional[str] = None
    website: Optional[str] = None


def validate_api_key(x_api_key: str = Header(...)) -> bool:
    """Validate API key for internal endpoints."""
    expected_key = os.getenv("INTERNAL_API_KEY")
    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return True


@projects_router.post("/{project_id}/business-hours")
async def update_project_business_hours(
    project_id: str,
    request: UpdateBusinessHoursRequest,
    session: Session = Depends(get_db),
    _: bool = Depends(validate_api_key)
):
    """
    Update project (store location) business hours.

    Called by Lambda after fetching hours from Google Places API.
    """
    project_repo = ProjectRepository(session)

    try:
        # Get project
        project = project_repo.get_project_by_id(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Convert request to dict for storage
        new_hours_data = request.dict()

        # Check if hours actually changed
        old_hours_data = project.business_hours or {}
        hours_changed = _hours_have_changed(old_hours_data, new_hours_data)

        # Check if phone changed
        old_phone = old_hours_data.get('formatted_phone_number')
        new_phone = new_hours_data.get('formatted_phone_number')
        phone_changed = old_phone != new_phone

        # Update project
        project_repo.update_project_business_hours(
            project_id=project_id,
            business_hours=new_hours_data,
            last_updated=datetime.now(timezone.utc)
        )

        logger.info(
            f"Updated business hours for project {project_id}",
            extra={
                "project_id": project_id,
                "hours_changed": hours_changed,
                "phone_changed": phone_changed
            }
        )

        return {
            "success": True,
            "project_id": project_id,
            "hours_changed": hours_changed,
            "phone_changed": phone_changed,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error updating hours for project {project_id}",
            exc_info=True,
            extra={"project_id": project_id}
        )
        session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update business hours: {str(e)}"
        )


def _hours_have_changed(old_data: Dict[str, Any], new_data: Dict[str, Any]) -> bool:
    """
    Compare old and new hours data to detect changes.

    Ignores last_fetched timestamp for comparison.
    """
    # Remove timestamps for comparison
    old_compare = {k: v for k, v in old_data.items() if k != 'last_fetched'}
    new_compare = {k: v for k, v in new_data.items() if k != 'last_fetched'}

    return old_compare != new_compare
```

### Phase 5: Knowledge Base Update Endpoint

**File:** `/api/routes/internal/knowledge.py` (add to existing)

```python
class UpdateBusinessHoursKBRequest(BaseModel):
    hours_text: str  # Natural language format
    hours_data: Dict[str, Any]  # Structured data
    namespace: str


@knowledge_router.post("/{project_id}/business-hours")
async def update_business_hours_kb(
    project_id: str,
    request: UpdateBusinessHoursKBRequest,
    session: Session = Depends(get_db),
    _: bool = Depends(validate_api_key)
):
    """
    Update business hours in Pinecone knowledge base.

    Called by Lambda for each project associated with the account.
    """
    project_repo = ProjectRepository(session)

    try:
        # Get project
        project = project_repo.get_project_by_id(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if not project.namespace:
            raise HTTPException(
                status_code=400,
                detail="Project has no namespace"
            )

        namespace = project.namespace
        account_id = str(project.account_id)

        # Query existing business hours
        existing_docs = query_vector_database(
            query_text="business hours open closed schedule",
            namespace=namespace,
            account_id=account_id,
            top_k=10,
            filter={"isBusinessHours": True}
        )

        # Compare
        new_content = request.hours_text
        needs_update = True

        if existing_docs and len(existing_docs) > 0:
            old_content = existing_docs[0].get("text", "")
            if old_content == new_content:
                needs_update = False

        # Update if needed
        if needs_update:
            # Delete old hours
            if existing_docs:
                delete_knowledge_file_by_metadata(
                    namespace=namespace,
                    account_id=account_id,
                    metadata={"isBusinessHours": True}
                )

            # Upload new hours
            upload_knowledge_file(
                namespace=namespace,
                account_id=account_id,
                file_content=new_content,
                file_name=f"business_hours_{project.account_id}.txt",
                metadata={
                    "isBusinessHours": True,
                    "source": "google_places",
                    "place_id": request.hours_data.get('place_id'),
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
            )

        logger.info(
            f"Updated business hours KB for project {project_id}",
            extra={
                "project_id": project_id,
                "namespace": namespace,
                "updated": needs_update
            }
        )

        return {
            "success": True,
            "project_id": project_id,
            "namespace": namespace,
            "updated": needs_update
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error updating hours KB for {project_id}",
            exc_info=True,
            extra={"project_id": project_id}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update hours in knowledge base: {str(e)}"
        )
```

### Phase 6: Register Router

**File:** `/api/routes/internal/__init__.py` (modify existing)

```python
from fastapi import APIRouter
from .events import events_router
from .scheduled import scheduled_router
from .integrations import integrations_router
from .knowledge import knowledge_router
from .projects import projects_router  # NEW (if separate file)

internal_router = APIRouter()

internal_router.include_router(events_router, prefix="/events", tags=["Internal Events"])
internal_router.include_router(scheduled_router, prefix="/scheduled", tags=["Scheduled Tasks"])
internal_router.include_router(integrations_router, prefix="/integrations", tags=["Internal Integrations"])
internal_router.include_router(knowledge_router, prefix="/knowledge", tags=["Internal Knowledge"])
internal_router.include_router(projects_router, prefix="/projects", tags=["Internal Projects"])  # NEW
```

## Infrastructure as Code

### EventBridge Scheduler (Terraform)

```hcl
resource "aws_scheduler_schedule" "business_hours_update" {
  name        = "pal-daily-business-hours-update"
  description = "Triggers Google business hours update daily at 4 AM UTC"

  schedule_expression = "cron(0 4 * * ? *)"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_api_gateway_stage.internal.execution_arn
    role_arn = aws_iam_role.scheduler_role.arn

    http_parameters {
      header_parameters = {
        "X-API-Key" = data.aws_secretsmanager_secret_version.internal_api_key.secret_string
      }
    }

    input = jsonencode({
      force_update = false
    })

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 2
    }
  }
}
```

### EventBridge Event Rule (Terraform)

```hcl
resource "aws_cloudwatch_event_rule" "business_hours_update_requested" {
  name           = "pal-business-hours-update-requested"
  description    = "Routes GoogleBusinessHoursUpdateRequested events to Lambda"
  event_bus_name = "pal-main-event-bus"

  event_pattern = jsonencode({
    source      = ["pal-mono"]
    detail-type = ["integration.google.BusinessHoursUpdateRequested"]
  })
}

resource "aws_cloudwatch_event_target" "business_hours_lambda" {
  rule           = aws_cloudwatch_event_rule.business_hours_update_requested.name
  event_bus_name = "pal-main-event-bus"
  arn            = aws_lambda_function.google_business_hours_updater.arn

  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 2
  }

  dead_letter_config {
    arn = aws_sqs_queue.business_hours_update_dlq.arn
  }
}
```

### Lambda Function (Terraform)

```hcl
resource "aws_lambda_function" "google_business_hours_updater" {
  function_name = "pal-google-business-hours-updater"
  role          = aws_iam_role.google_lambda_role.arn

  filename         = "lambdas/google_business_hours_updater.zip"
  source_code_hash = filebase64sha256("lambdas/google_business_hours_updater.zip")

  runtime = "python3.12"
  handler = "handler.lambda_handler"
  timeout = 120  # 2 minutes
  memory_size = 512

  reserved_concurrent_executions = 3  # Respect Google API quotas

  environment {
    variables = {
      INTERNAL_API_URL     = var.internal_api_url
      INTERNAL_API_KEY     = data.aws_secretsmanager_secret_version.internal_api_key.secret_string
      GOOGLE_MAPS_API_KEY  = data.aws_secretsmanager_secret_version.google_maps_api_key.secret_string
      EVENT_BUS_NAME       = "pal-main-event-bus"
    }
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.business_hours_update_dlq.arn
  }
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.google_business_hours_updater.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.business_hours_update_requested.arn
}
```

## Testing Strategy

### Unit Tests

**Test Discovery Endpoint:**
```python
def test_business_hours_update_discovery(test_client, test_db):
    # Create test account and project with place_id
    account = create_account()
    project = create_project(
        account_id=account.id,
        namespace="test-namespace",
        google_place_id="ChIJtest123",
        business_hours_last_updated=datetime.now(timezone.utc) - timedelta(days=2)
    )

    # Call endpoint
    response = test_client.post(
        "/v1/internal/scheduled/business-hours-update",
        headers={"X-API-Key": "test-key"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data['events_published'] == 1
```

**Test Lambda Handler:**
```python
def test_lambda_handler_success(mock_requests, mock_eventbridge):
    # Mock Google Places API response
    mock_requests.get.return_value.json.return_value = {
        "status": "OK",
        "result": {
            "place_id": "ChIJtest123",
            "opening_hours": {
                "open_now": True,
                "weekday_text": ["Monday: 9:00 AM – 5:00 PM"]
            }
        }
    }

    # Mock internal API responses
    mock_requests.post.return_value.status_code = 200
    mock_requests.post.return_value.json.return_value = {
        "success": True,
        "hours_changed": True
    }

    # Create test event
    event = {
        "detail": {
            "project_id": "proj-1",
            "project_name": "Downtown Store",
            "account_id": "test-account-id",
            "account_name": "Test Restaurant",
            "google_place_id": "ChIJtest123",
            "namespace": "test-namespace"
        }
    }

    # Call handler
    result = lambda_handler(event, mock_context)

    assert result['statusCode'] == 200
    body = json.loads(result['body'])
    assert body['success'] == True
    assert 'project_id' in body
```

### Integration Tests

**End-to-End Test:**
```python
async def test_business_hours_update_e2e():
    # 1. Create project with place_id
    account = create_account()
    project = create_project(
        account_id=account.id,
        namespace="test-ns",
        google_place_id="ChIJ_real_place_id"
    )

    # 2. Call discovery endpoint
    response = await client.post(
        "/v1/internal/scheduled/business-hours-update",
        headers={"X-API-Key": API_KEY},
        json={"force_update": True}
    )
    assert response.status_code == 200

    # 3. Wait for Lambda execution
    await asyncio.sleep(15)

    # 4. Verify database updated
    updated_project = get_project_by_id(project.id)
    assert updated_project.business_hours is not None
    assert updated_project.business_hours_last_updated is not None
    assert updated_project.store_hours is not None  # Human-readable field

    # 5. Verify knowledge base updated
    docs = query_vector_database(
        query_text="business hours",
        namespace="test-ns",
        account_id=str(account.id),
        filter={"isBusinessHours": True}
    )
    assert len(docs) > 0

    # 6. Verify Datadog metrics logged
    # (Check Datadog API or mocked metrics in tests)
```

## Monitoring & Observability with Datadog

### Datadog Metrics

The Lambda function emits the following custom metrics to Datadog:

**Success Metrics:**
- `business_hours_updater.success` (count) - Successful update completions
  - Tags: `environment`, `account_id`, `project_id`

- `business_hours_updater.duration` (gauge, milliseconds) - Update duration
  - Tags: `environment`, `account_id`, `status` (success/error)

- `business_hours_updater.hours_changed` (count) - Hours data changed
  - Tags: `environment`, `account_id`, `project_id`

- `business_hours_updater.kb_updated` (count) - Knowledge base updated
  - Tags: `environment`, `account_id`, `project_id`

**Error Metrics:**
- `business_hours_updater.error` (count) - Failed updates
  - Tags: `environment`, `account_id`, `error_type`

- `business_hours_updater.kb_update_failed` (count) - KB update failures
  - Tags: `environment`, `account_id`, `project_id`

### Datadog Monitors

**Monitor 1: High Error Rate**
```
Monitor Name: Business Hours Updater - High Error Rate
Query: sum(last_1h):sum:business_hours_updater.error{environment:prd}.as_count() > 3
Message:
  @slack-ops-alerts
  @pagerduty-oncall

  Business hours updater is experiencing high error rates.

  Error count: {{value}}
  Environment: {{environment.name}}

  Check Lambda logs: https://app.datadoghq.com/logs?query=service:google-business-hours-updater
Priority: P2
Tags: service:google-business-hours-updater, team:platform
```

**Monitor 2: Slow Update Duration**
```
Monitor Name: Business Hours Updater - Slow Performance
Query: avg(last_15m):avg:business_hours_updater.duration{environment:prd} > 30000
Message:
  @slack-ops-alerts

  Business hours updates are taking longer than expected.

  Average duration: {{value}}ms (threshold: 30000ms)
  Environment: {{environment.name}}

  Investigate:
  - Google Places API latency
  - Internal API performance
  - Database query performance
Priority: P3
Tags: service:google-business-hours-updater, team:platform
```

**Monitor 3: No Updates Running**
```
Monitor Name: Business Hours Updater - No Updates
Query: sum(last_2h):sum:business_hours_updater.success{environment:prd}.as_count() < 1
Message:
  @slack-ops-alerts

  No successful business hours updates in the last 2 hours.

  Expected: At least 1 update per day (daily cron runs at 4 AM UTC)

  Check:
  - EventBridge Scheduler is enabled
  - Lambda is not throttled
  - Discovery endpoint is healthy
Priority: P3
Tags: service:google-business-hours-updater, team:platform
```

**Monitor 4: Knowledge Base Update Failures**
```
Monitor Name: Business Hours Updater - KB Update Failures
Query: sum(last_1h):sum:business_hours_updater.kb_update_failed{environment:prd}.as_count() > 2
Message:
  @slack-ops-alerts

  Multiple knowledge base update failures detected.

  Failure count: {{value}}
  Environment: {{environment.name}}

  Check:
  - Pinecone API status
  - Project namespace configuration
  - Embedding generation performance
Priority: P3
Tags: service:google-business-hours-updater, team:platform
```

### Datadog Dashboard

Create a dashboard with the following widgets:

1. **Success Rate** - Timeseries of success vs error count
2. **Update Duration** - P50, P95, P99 latency
3. **Hours Changed Rate** - How often hours actually change
4. **KB Update Rate** - Knowledge base update success rate
5. **Error Breakdown** - Pie chart by error_type
6. **Updates by Account** - Top 10 accounts by update count
7. **Lambda Metrics** - Duration, memory usage, concurrent executions

### Lambda Layer Configuration

Add Datadog Lambda Layer to Terraform:

```hcl
resource "aws_lambda_function" "google_business_hours_updater" {
  # ... existing configuration ...

  layers = [
    "arn:aws:lambda:${var.aws_region}:464622532012:layer:Datadog-Python312:${var.datadog_layer_version}"
  ]

  environment {
    variables = {
      INTERNAL_API_URL     = var.internal_api_url
      INTERNAL_API_KEY     = data.aws_secretsmanager_secret_version.internal_api_key.secret_string
      GOOGLE_MAPS_API_KEY  = data.aws_secretsmanager_secret_version.google_maps_api_key.secret_string
      ENVIRONMENT          = var.environment

      # Datadog configuration
      DD_API_KEY           = data.aws_secretsmanager_secret_version.datadog_api_key.secret_string
      DD_SITE              = "datadoghq.com"
      DD_SERVICE           = "google-business-hours-updater"
      DD_ENV               = var.environment
      DD_VERSION           = var.app_version
      DD_LOGS_INJECTION    = "true"
      DD_TRACE_ENABLED     = "true"
    }
  }
}
```

## Admin UI Integration

### Add Place ID to Project Settings

**File:** `/api/routes/admin/__init__.py` (add endpoint)

```python
class UpdateProjectGooglePlaceIdRequest(BaseModel):
    google_place_id: str


@admin_router.post("/projects/{project_id}/google-place-id")
async def update_project_google_place_id(
    project_id: str,
    request: UpdateProjectGooglePlaceIdRequest,
    context: UserContext = Depends(authenticate_user),
    session: Session = Depends(get_db)
):
    """
    Update Google Place ID for a project (store location).

    This enables automated business hours updates for this specific store.
    Each store location should have its own Google Business Profile Place ID.
    """
    authorize_admin(context)

    project_repo = ProjectRepository(session)
    project = project_repo.get_project_by_id(project_id)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate place_id by fetching from Google
    try:
        place_data = await get_place_details_by_place_id(request.google_place_id)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid Google Place ID: {str(e)}"
        )

    # Update project
    project.google_place_id = request.google_place_id
    session.commit()

    return {
        "success": True,
        "project_id": project_id,
        "google_place_id": request.google_place_id,
        "place_name": place_data.name,
        "place_address": place_data.formatted_address
    }
```

## Rollback Plan

### Phase 1: Disable Scheduler

```bash
aws scheduler update-schedule \
  --name pal-daily-business-hours-update \
  --state DISABLED
```

### Phase 2: Check DLQ

```bash
aws sqs receive-message \
  --queue-url https://sqs.us-east-1.amazonaws.com/.../business-hours-update-dlq \
  --max-number-of-messages 10
```

### Phase 3: Rollback Database Migration

```sql
-- Remove new columns
ALTER TABLE projects
DROP COLUMN google_place_id,
DROP COLUMN business_hours,
DROP COLUMN business_hours_last_updated;

-- Drop indices
DROP INDEX idx_projects_google_place_id;
DROP INDEX idx_projects_business_hours_last_updated;
```

### Phase 4: Rollback Code

```bash
git revert <commit-hash>
./scripts/deploy.sh lat
```

## Future Enhancements

### 1. Popular Times

Fetch and store popular times data:
```json
{
  "popular_times": [
    {
      "day": 1,
      "hour": 12,
      "popularity": 85
    }
  ]
}
```

### 2. Multi-Location Support (Already Built-In!)

✅ **Already supported!** Since hours are stored at the project level:
- Each project = one store location
- Each project has its own `google_place_id`
- Each location gets its own hours update event
- Each location has its own knowledge base namespace
- Perfect for multi-location businesses!

### 3. Smart Update Frequency

Adjust update frequency based on patterns:
- High-change accounts: Update more frequently
- Stable accounts: Update less frequently
- Pre-holiday checks: Update before major holidays

### 4. Proactive Notifications

Notify operators of changes:
- "Your hours on Google changed - updated in system"
- "Special closure detected for Christmas"
- "Phone number mismatch - please verify"

### 5. Hours Verification

Cross-check hours against other sources:
- Compare with POS system hours
- Alert on mismatches
- Suggest corrections

### 6. Analytics Dashboard

Track hours-related metrics:
- How often hours change
- Most common special closures
- "Open now" accuracy rate
- Agent question patterns

## Google Places API Considerations

### API Quotas

**Places API (Pay-as-you-go):**
- $0.017 per Place Details request
- 100,000+ requests/day (depends on quota tier)
- Rate limit: ~100 requests/second

**Optimization strategies:**
- Only update if not updated in 24 hours
- Reserved concurrency: 3 (prevents runaway costs)
- Batch processing with delays
- Cache results in database

### API Fields

**Request only necessary fields to reduce costs:**
```
fields=name,opening_hours,current_opening_hours,formatted_phone_number
```

**Available fields:**
- `opening_hours` - Regular hours
- `current_opening_hours` - Includes special hours/holidays
- `business_status` - OPERATIONAL, CLOSED_TEMPORARILY, CLOSED_PERMANENTLY
- `utc_offset` - Timezone offset

### Error Handling

**Common API errors:**
- `INVALID_REQUEST` - Bad place_id → Skip, log warning
- `OVER_QUERY_LIMIT` - Quota exceeded → Retry with backoff, alert
- `REQUEST_DENIED` - API key invalid → Alert ops immediately
- `NOT_FOUND` - Place no longer exists → Mark in DB, alert
- `ZERO_RESULTS` - Place not found → Mark in DB

## Security Considerations

### API Key Management

**Google Maps API Key:**
- Stored in AWS Secrets Manager
- Restricted to Places API only
- IP restrictions (if possible)
- Separate keys per environment
- Regular rotation schedule

### Rate Limiting

**Prevent abuse:**
- Reserved Lambda concurrency (max 3)
- EventBridge retry limits
- CloudWatch alarms on high volume
- DLQ for failed requests

### Data Privacy

**PII Considerations:**
- Phone numbers stored in database (OK for business)
- No customer data involved
- Business hours are public information
- Log sanitization (no PII in logs)

## References

- Existing Google Maps Service: `/services/google_maps_service/_implementation.py`
- Google Places API Docs: https://developers.google.com/maps/documentation/places/web-service/details
- Event Bus Implementation: `/events/__init__.py`
- Current Square/Toast Updaters: `.claude/docs/business_updater/`

## Summary

The Google Business Hours Updater completes the business data updater suite:

1. **Square Token Refresher** - Keeps OAuth tokens fresh
2. **Toast Menu Updater** - Syncs menu data
3. **Google Business Hours Updater** - Syncs operating hours ✨

All three follow the same event-driven architecture pattern:
- EventBridge Scheduler → Discovery → Events → Lambda → Internal API
- Parallel processing with fan-out
- Observable with Datadog metrics and monitors
- Resilient with retries and DLQ
- Scalable and testable

**Key Differentiators:**
- Simplest auth (API key only)
- Dual updates (database + knowledge base)
- **Project-level storage** (each store location has own place_id and hours)
- Native multi-location support (one event per store)
- Natural language formatting for better RAG
- Lower update frequency (daily vs hourly)
- Cost-aware (Google charges per request)

**Architecture Benefits:**
- **Correct data model**: Hours stored at project (store) level, not account level
- **Multi-location ready**: Each store location is a project with its own Google Place ID
- **Simple fan-out**: One event per store (no complex batching logic)
- **Independent updates**: Each store can be updated independently
- **Clean separation**: Each store has its own knowledge base namespace
