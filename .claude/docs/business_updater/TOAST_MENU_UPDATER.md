# Toast Menu Updater - Detailed Implementation

## Overview

The Toast Menu Updater automatically syncs restaurant menu data from Toast POS to the knowledge base (Pinecone) for AI agent consumption. This enables agents to answer questions about:
- Menu items and pricing
- Item descriptions and ingredients
- Dietary restrictions and allergens
- Dining options (delivery, takeout, dine-in)
- Menu availability and hours

## Current Implementation Analysis

### Location
- **Main Logic:** `/api/routes/integrations/toast/_implementation.py` (lines 339-365)
- **Service Layer:** `/services/knowledge_service/toast/_implementation.py` (585 lines)
- **Client:** `/services/knowledge_service/toast/_client.py`
- **Indexer:** `/services/knowledge_service/toast/_indexer.py`
- **Router:** `/api/routes/integrations/__init__.py` (lines 102-109)

### Current Flow

```
API Endpoint: POST /v1/integrations/toast/refresh-dining-options
    ↓
check_and_refresh_dining_options(session)
    ↓
Query all Toast integrations
    ↓
For each integration:
    ├─> Fetch dining options from Toast API
    ├─> Find associated projects
    └─> For each project:
        ├─> Query Pinecone for existing dining options
        ├─> Compare old vs new (string match)
        └─> If different:
            ├─> Delete old vectors
            └─> Upload new dining options
```

### Database Schema

**Table:** `integrations`

Relevant columns:
```sql
id                UUID PRIMARY KEY
account_id        UUID REFERENCES accounts(id)
provider          VARCHAR (='toast')
type              VARCHAR (='pos')
secret_key        VARCHAR  -- AWS Secrets Manager key
metadata          JSONB    -- Contains: business_id (store ID)
created_at        TIMESTAMP WITH TIME ZONE
updated_at        TIMESTAMP WITH TIME ZONE
```

**Table:** `project_integrations` (many-to-many)

```sql
project_id        UUID REFERENCES projects(id)
integration_id    UUID REFERENCES integrations(id)
PRIMARY KEY (project_id, integration_id)
```

**Table:** `projects`

Relevant columns:
```sql
id                UUID PRIMARY KEY
name              VARCHAR
account_id        UUID REFERENCES accounts(id)
namespace         VARCHAR  -- Pinecone namespace
```

**AWS Secrets Manager Structure:**
```json
{
  "client_id": "toast_client_id",
  "client_secret": "toast_client_secret",
  "business_id": "store_guid"
}
```

### Current Code

#### Discovery & Orchestration

```python
def check_and_refresh_dining_options(session):
    """
    Refresh dining options for all Toast integrations.

    This is the current synchronous implementation.
    """
    integration_repository = IntegrationRepository(session)

    # Get all Toast integrations
    toast_integrations = session.query(Integration).filter(
        Integration.provider == IntegrationProvider.toast
    ).all()

    results = []

    for integration in toast_integrations:
        try:
            # Fetch dining options from Toast
            dining_options = _fetch_dining_options(integration)

            # Get associated projects
            projects = session.query(Project).join(
                ProjectIntegration
            ).filter(
                ProjectIntegration.integration_id == integration.id
            ).all()

            # Update each project's knowledge base
            for project in projects:
                result = _update_project_dining_options(
                    project=project,
                    integration=integration,
                    dining_options=dining_options,
                    session=session
                )
                results.append(result)

        except Exception as e:
            logger.error(
                f"Error refreshing dining options for integration {integration.id}",
                exc_info=True
            )
            results.append({
                "integration_id": str(integration.id),
                "error": str(e)
            })

    return {
        "total_integrations": len(toast_integrations),
        "results": results
    }
```

#### Fetch Dining Options

```python
def _fetch_dining_options(integration: Integration) -> dict:
    """Fetch dining options from Toast API."""
    # Get credentials
    credentials = get_toast_credentials_from_aws(integration.secret_key)
    business_id = credentials.get("business_id")

    # Get access token
    access_token = get_toast_access_token(
        client_id=credentials["client_id"],
        client_secret=credentials["client_secret"]
    )

    # Call Toast API
    url = f"https://api.toasttab.com/config/v2/diningOptions"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Toast-Restaurant-External-ID": business_id
    }

    response = requests.get(url, headers=headers, timeout=30)

    if response.status_code != 200:
        raise Exception(f"Toast API error: {response.status_code}")

    return response.json()
```

#### Update Knowledge Base

```python
def _update_project_dining_options(
    project: Project,
    integration: Integration,
    dining_options: dict,
    session
) -> dict:
    """Update Pinecone knowledge base with dining options."""
    namespace = project.namespace
    account_id = str(project.account_id)

    # Query existing dining options
    existing_docs = query_vector_database(
        query_text="dining options",
        namespace=namespace,
        account_id=account_id,
        top_k=10,
        filter={"isDiningOptions": True}
    )

    # Convert dining options to string for comparison
    new_content = json.dumps(dining_options, indent=2)

    # Check if update needed
    needs_update = True
    if existing_docs and len(existing_docs) > 0:
        existing_content = existing_docs[0].get("text", "")
        if existing_content == new_content:
            needs_update = False

    if needs_update:
        # Delete old dining options
        if existing_docs:
            delete_knowledge_file_by_metadata(
                namespace=namespace,
                account_id=account_id,
                metadata={"isDiningOptions": True}
            )

        # Upload new dining options
        upload_knowledge_file(
            namespace=namespace,
            account_id=account_id,
            file_content=new_content,
            file_name=f"dining_options_{integration.id}.json",
            metadata={
                "isDiningOptions": True,
                "integration_id": str(integration.id),
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
        )

    return {
        "project_id": str(project.id),
        "integration_id": str(integration.id),
        "updated": needs_update
    }
```

### Full Menu Processing (Background)

The system also has a more comprehensive menu processor:

```python
class ToastMenuProcessor:
    """Process and index Toast menus to Pinecone."""

    async def process_and_index_menu_from_api(
        self,
        integration_id: str,
        account_id: str,
        menu_last_updated: Optional[datetime] = None
    ) -> dict:
        """
        Full menu processing pipeline:
        1. Get metadata and check if update needed
        2. Download full menu JSON
        3. Parse menu items
        4. Index to Pinecone
        5. Update dining options
        """
        # Get Toast client
        client = await self._get_toast_client(integration_id)

        # Check if menu changed
        metadata = await client.get_menu_metadata()
        if menu_last_updated and metadata['lastUpdated'] <= menu_last_updated:
            return {"status": "skipped", "reason": "no_changes"}

        # Download menu
        menu_data = await client.download_menu()

        # Parse menu
        parsed_items = self._parse_menu(menu_data)

        # Index to Pinecone
        index_result = await self._index_to_pinecone(
            namespace=namespace,
            items=parsed_items,
            account_id=account_id
        )

        # Update dining options
        dining_options = await client.get_dining_options()
        await self._update_dining_options(dining_options)

        return {
            "status": "success",
            "items_indexed": len(parsed_items),
            "last_updated": metadata['lastUpdated']
        }
```

### Issues with Current Implementation

1. **Synchronous Processing** - All integrations processed sequentially
2. **No Parallel Execution** - Can't scale for many restaurants
3. **No Job Tracking** - Can't see progress of long-running updates
4. **No Retries** - Single failure stops processing
5. **Manual Trigger** - Requires external scheduler
6. **Limited Observability** - No events, only logs
7. **Tight Coupling** - Discovery and execution mixed
8. **No Authentication** - Public endpoint (security risk)

## Event-Driven Architecture

### Components

```
┌────────────────────────────────────────────────────────────────┐
│  EventBridge Scheduler                                          │
│  Rule: pal-daily-toast-menu-update                             │
│  Schedule: cron(0 3 * * ? *)  # 3 AM UTC daily                │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     │ POST /v1/internal/scheduled/toast-menu-update
                     │ Headers: X-API-Key: ***
                     ▼
┌────────────────────────────────────────────────────────────────┐
│  Internal API: Discovery Endpoint                              │
│  File: /api/routes/internal/scheduled.py                       │
│                                                                  │
│  1. Query all Toast integrations                                │
│  2. Join with projects via project_integrations                │
│  3. For each project+integration pair:                          │
│     - Get project namespace                                     │
│     - Publish ToastMenuUpdateRequested event                    │
│  4. Return summary: {total_queued: N}                          │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     │ Publish N events (fan-out)
                     ▼
┌────────────────────────────────────────────────────────────────┐
│  EventBridge: pal-main-event-bus                               │
│  DetailType: integration.toast.MenuUpdateRequested             │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     │ N parallel invocations
                     ▼
┌────────────────────────────────────────────────────────────────┐
│  Lambda: toast-menu-updater                                     │
│  Runtime: Python 3.12                                            │
│  Timeout: 10 minutes (menus can be large)                       │
│  Concurrency: 5 (reserved, API rate limits)                     │
│                                                                  │
│  1. Parse event                                                  │
│  2. Get Toast credentials from Secrets Manager                  │
│  3. Get OAuth token from Toast                                  │
│  4. Fetch dining options JSON                                   │
│  5. POST /v1/internal/knowledge/{project_id}/dining-options    │
│  6. Publish ToastMenuUpdateCompleted event                      │
└────────────────────┬───────────────────────────────────────────┘
                     │
                     │ POST with dining options JSON
                     ▼
┌────────────────────────────────────────────────────────────────┐
│  Internal API: Knowledge Update Endpoint                        │
│  File: /api/routes/internal/knowledge.py                       │
│                                                                  │
│  1. Validate project exists and has namespace                   │
│  2. Query Pinecone for existing dining options                  │
│  3. Compare old vs new (string match)                           │
│  4. If different:                                                │
│     - Delete old vectors (metadata: isDiningOptions=True)       │
│     - Upload new dining options                                 │
│     - Create embeddings                                          │
│  5. Return result                                                │
└────────────────────────────────────────────────────────────────┘
```

### Decision: Lambda + Pinecone

**Two Options:**
1. Lambda does Pinecone operations directly
2. Lambda calls internal API for Pinecone operations

**Recommendation:** **Option 2 - Lambda calls internal API**

**Reasoning:**
- Pinecone operations involve complex business logic (comparison, metadata handling)
- Keeps Pinecone credentials centralized in API
- Easier to update Pinecone logic without redeploying Lambdas
- Consistent with database operation pattern
- API can add additional validation/authorization

## Implementation Details

### Phase 1: Event Schemas

**File:** `/events/schema.py`

```python
@dataclass
class ToastMenuUpdateRequested(BaseEvent):
    """Event published when a Toast menu needs updating."""

    detail_type: ClassVar[str] = "integration.toast.MenuUpdateRequested"

    # Required fields
    project_id: UUID
    integration_id: UUID
    project_name: str
    account_id: UUID
    account_name: str
    namespace: str  # Pinecone namespace
    secret_key: str  # AWS Secrets Manager key

    # Configuration
    update_type: str = "dining_options"  # or "full_menu"

    # Metadata
    requested_at: datetime
    requested_by: str = "scheduler"  # or "manual"


@dataclass
class ToastMenuUpdateCompleted(BaseEvent):
    """Event published when a Toast menu update completes."""

    detail_type: ClassVar[str] = "integration.toast.MenuUpdateCompleted"

    # Required fields
    project_id: UUID
    integration_id: UUID
    account_id: UUID
    success: bool

    # Success fields
    changes_detected: bool = False
    items_updated: int = 0
    update_type: str = "dining_options"

    # Failure fields
    error_message: Optional[str] = None
    error_code: Optional[str] = None

    # Metadata
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: int = 0
    lambda_request_id: Optional[str] = None
```

### Phase 2: Discovery Endpoint

**File:** `/api/routes/internal/scheduled.py` (add to existing)

```python
@scheduled_router.post("/toast-menu-update")
async def trigger_toast_menu_update(
    update_type: str = "dining_options",  # or "full_menu"
    session: Session = Depends(get_db),
    _: bool = Depends(validate_api_key)
):
    """
    Discovery endpoint for Toast menu updates.

    Queries database for Toast integrations and publishes events.
    Called by EventBridge Scheduler daily.
    """
    integration_repo = IntegrationRepository(session)

    try:
        # Get all Toast POS integrations
        toast_integrations = session.query(Integration).filter(
            Integration.provider == IntegrationProvider.toast,
            Integration.type == IntegrationType.pos
        ).all()

        # Get associated projects
        events_published = 0
        skipped = 0
        errors = []

        for integration in toast_integrations:
            # Skip if missing required data
            if not integration.secret_key:
                skipped += 1
                logger.warning(
                    f"Skipping integration {integration.id}: missing secret_key"
                )
                continue

            # Get associated projects
            projects = session.query(Project).join(
                ProjectIntegration
            ).filter(
                ProjectIntegration.integration_id == integration.id
            ).all()

            if not projects:
                skipped += 1
                logger.warning(
                    f"Skipping integration {integration.id}: no projects"
                )
                continue

            # Publish event for each project
            for project in projects:
                if not project.namespace:
                    skipped += 1
                    logger.warning(
                        f"Skipping project {project.id}: no namespace"
                    )
                    continue

                try:
                    # Get account
                    account = session.query(Account).filter(
                        Account.id == project.account_id
                    ).first()

                    # Publish event
                    event = ToastMenuUpdateRequested(
                        project_id=project.id,
                        integration_id=integration.id,
                        project_name=project.name,
                        account_id=project.account_id,
                        account_name=account.name,
                        namespace=project.namespace,
                        secret_key=integration.secret_key,
                        update_type=update_type,
                        requested_at=datetime.now(timezone.utc),
                        requested_by="scheduler"
                    )

                    success = await publish_event(event)

                    if success:
                        events_published += 1
                        logger.info(
                            f"Published menu update event for project {project.id}",
                            extra={
                                "project_id": str(project.id),
                                "integration_id": str(integration.id),
                                "namespace": project.namespace
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
            "total_integrations": len(toast_integrations),
            "events_published": events_published,
            "skipped": skipped,
            "errors": errors,
            "update_type": update_type
        }

    except Exception as e:
        logger.error("Error in toast menu update discovery", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger menu update: {str(e)}"
        )
```

### Phase 3: Lambda Function

**File:** `lambdas/toast_menu_updater/handler.py` (new Lambda project)

```python
import json
import os
import boto3
import requests
from datetime import datetime, timezone
from typing import Dict, Any
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
secrets_client = boto3.client('secretsmanager')
eventbridge_client = boto3.client('events')

# Configuration
INTERNAL_API_URL = os.environ['INTERNAL_API_URL']
INTERNAL_API_KEY = os.environ['INTERNAL_API_KEY']
EVENT_BUS_NAME = os.environ['EVENT_BUS_NAME']
TOAST_API_BASE_URL = "https://api.toasttab.com"


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for Toast menu update.

    Receives ToastMenuUpdateRequested event from EventBridge.
    """
    start_time = datetime.now(timezone.utc)
    request_id = context.request_id

    try:
        # Parse event
        detail = event['detail']
        project_id = detail['project_id']
        integration_id = detail['integration_id']
        account_id = detail['account_id']
        project_name = detail['project_name']
        namespace = detail['namespace']
        secret_key = detail['secret_key']
        update_type = detail.get('update_type', 'dining_options')

        logger.info(
            f"Processing menu update for project {project_id}",
            extra={
                "project_id": project_id,
                "integration_id": integration_id,
                "namespace": namespace,
                "update_type": update_type
            }
        )

        # Get Toast credentials
        credentials = get_credentials_from_secrets_manager(secret_key)

        # Get Toast access token
        access_token = get_toast_access_token(
            client_id=credentials['client_id'],
            client_secret=credentials['client_secret']
        )

        # Fetch data based on update type
        if update_type == "dining_options":
            data = fetch_dining_options(
                access_token=access_token,
                business_id=credentials['business_id']
            )

            # Update via internal API
            result = update_dining_options_via_api(
                project_id=project_id,
                integration_id=integration_id,
                dining_options=data
            )

        elif update_type == "full_menu":
            data = fetch_full_menu(
                access_token=access_token,
                business_id=credentials['business_id']
            )

            # Update via internal API
            result = update_full_menu_via_api(
                project_id=project_id,
                integration_id=integration_id,
                menu_data=data
            )

        else:
            raise ValueError(f"Invalid update_type: {update_type}")

        # Calculate duration
        duration_ms = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )

        # Publish success event
        publish_completion_event(
            project_id=project_id,
            integration_id=integration_id,
            account_id=account_id,
            success=True,
            changes_detected=result.get('changes_detected', False),
            items_updated=result.get('items_updated', 0),
            update_type=update_type,
            duration_ms=duration_ms,
            request_id=request_id
        )

        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "project_id": project_id,
                "changes_detected": result.get('changes_detected', False)
            })
        }

    except Exception as e:
        logger.error(
            f"Error updating menu: {str(e)}",
            exc_info=True,
            extra={
                "project_id": detail.get('project_id'),
                "error": str(e)
            }
        )

        # Calculate duration
        duration_ms = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )

        # Publish failure event
        publish_completion_event(
            project_id=detail.get('project_id'),
            integration_id=detail.get('integration_id'),
            account_id=detail.get('account_id'),
            success=False,
            error_message=str(e),
            error_code=type(e).__name__,
            update_type=detail.get('update_type', 'dining_options'),
            duration_ms=duration_ms,
            request_id=request_id
        )

        # Re-raise to trigger Lambda retry
        raise


def get_credentials_from_secrets_manager(secret_key: str) -> Dict[str, Any]:
    """Get Toast credentials from Secrets Manager."""
    response = secrets_client.get_secret_value(SecretId=secret_key)
    return json.loads(response['SecretString'])


def get_toast_access_token(client_id: str, client_secret: str) -> str:
    """Get Toast OAuth access token."""
    response = requests.post(
        f"{TOAST_API_BASE_URL}/authentication/v1/authentication/login",
        json={
            "clientId": client_id,
            "clientSecret": client_secret,
            "userAccessType": "TOAST_MACHINE_CLIENT"
        },
        headers={"Content-Type": "application/json"},
        timeout=30
    )

    if response.status_code != 200:
        raise Exception(
            f"Toast auth error: {response.status_code} - {response.text}"
        )

    data = response.json()
    return data['token']['accessToken']


def fetch_dining_options(access_token: str, business_id: str) -> Dict[str, Any]:
    """Fetch dining options from Toast API."""
    response = requests.get(
        f"{TOAST_API_BASE_URL}/config/v2/diningOptions",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Toast-Restaurant-External-ID": business_id
        },
        timeout=30
    )

    if response.status_code != 200:
        raise Exception(
            f"Toast API error: {response.status_code} - {response.text}"
        )

    return response.json()


def fetch_full_menu(access_token: str, business_id: str) -> Dict[str, Any]:
    """Fetch full menu from Toast API."""
    response = requests.get(
        f"{TOAST_API_BASE_URL}/menus/v2/menus",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Toast-Restaurant-External-ID": business_id
        },
        timeout=60  # Menus can be large
    )

    if response.status_code != 200:
        raise Exception(
            f"Toast API error: {response.status_code} - {response.text}"
        )

    return response.json()


def update_dining_options_via_api(
    project_id: str,
    integration_id: str,
    dining_options: Dict[str, Any]
) -> Dict[str, Any]:
    """Update dining options via internal API."""
    url = f"{INTERNAL_API_URL}/v1/internal/knowledge/{project_id}/dining-options"

    response = requests.post(
        url,
        json={
            "dining_options_json": json.dumps(dining_options),
            "source": "toast",
            "integration_id": integration_id
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


def update_full_menu_via_api(
    project_id: str,
    integration_id: str,
    menu_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Update full menu via internal API."""
    url = f"{INTERNAL_API_URL}/v1/internal/knowledge/{project_id}/full-menu"

    response = requests.post(
        url,
        json={
            "menu_json": json.dumps(menu_data),
            "source": "toast",
            "integration_id": integration_id
        },
        headers={
            "Content-Type": "application/json",
            "X-API-Key": INTERNAL_API_KEY
        },
        timeout=120  # Full menu processing can take time
    )

    if response.status_code != 200:
        raise Exception(
            f"Internal API error: {response.status_code} - {response.text}"
        )

    return response.json()


def publish_completion_event(
    project_id: str,
    integration_id: str,
    account_id: str,
    success: bool,
    changes_detected: bool = False,
    items_updated: int = 0,
    update_type: str = "dining_options",
    error_message: str = None,
    error_code: str = None,
    duration_ms: int = 0,
    request_id: str = None
) -> None:
    """Publish ToastMenuUpdateCompleted event."""
    detail = {
        "project_id": project_id,
        "integration_id": integration_id,
        "account_id": account_id,
        "success": success,
        "update_type": update_type,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": duration_ms,
        "lambda_request_id": request_id
    }

    if success:
        detail["changes_detected"] = changes_detected
        detail["items_updated"] = items_updated
    else:
        detail["error_message"] = error_message
        detail["error_code"] = error_code

    eventbridge_client.put_events(
        Entries=[{
            "Source": "pal-mono",
            "DetailType": "integration.toast.MenuUpdateCompleted",
            "Detail": json.dumps(detail),
            "EventBusName": EVENT_BUS_NAME
        }]
    )
```

**Lambda Dependencies (`requirements.txt`):**
```
requests==2.31.0
boto3==1.34.0
```

### Phase 4: Knowledge Update Endpoints

**File:** `/api/routes/internal/knowledge.py` (new file)

```python
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import json
import logging

from db import get_db
from db.repositories.project_repository import ProjectRepository
from services.knowledge_service import (
    query_vector_database,
    delete_knowledge_file_by_metadata,
    upload_knowledge_file
)

logger = logging.getLogger(__name__)

knowledge_router = APIRouter()


class UpdateDiningOptionsRequest(BaseModel):
    dining_options_json: str  # JSON string
    source: str  # "toast", "square", etc.
    integration_id: str


class UpdateFullMenuRequest(BaseModel):
    menu_json: str  # JSON string
    source: str
    integration_id: str


def validate_api_key(x_api_key: str = Header(...)) -> bool:
    """Validate API key for internal endpoints."""
    expected_key = os.getenv("INTERNAL_API_KEY")
    if x_api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return True


@knowledge_router.post("/{project_id}/dining-options")
async def update_dining_options(
    project_id: str,
    request: UpdateDiningOptionsRequest,
    session: Session = Depends(get_db),
    _: bool = Depends(validate_api_key)
):
    """
    Update dining options in Pinecone knowledge base.

    Called by Lambda after fetching dining options from POS.
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

        # Parse dining options
        dining_options = json.loads(request.dining_options_json)

        # Query existing dining options
        existing_docs = query_vector_database(
            query_text="dining options delivery takeout",
            namespace=namespace,
            account_id=account_id,
            top_k=10,
            filter={"isDiningOptions": True}
        )

        # Compare
        new_content = request.dining_options_json
        needs_update = True
        old_content = None

        if existing_docs and len(existing_docs) > 0:
            old_content = existing_docs[0].get("text", "")
            if old_content == new_content:
                needs_update = False

        # Update if needed
        items_updated = 0
        if needs_update:
            # Delete old
            if existing_docs:
                delete_knowledge_file_by_metadata(
                    namespace=namespace,
                    account_id=account_id,
                    metadata={"isDiningOptions": True}
                )

            # Upload new
            upload_knowledge_file(
                namespace=namespace,
                account_id=account_id,
                file_content=new_content,
                file_name=f"dining_options_{request.integration_id}.json",
                metadata={
                    "isDiningOptions": True,
                    "integration_id": request.integration_id,
                    "source": request.source,
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
            )

            items_updated = 1

        logger.info(
            f"Updated dining options for project {project_id}",
            extra={
                "project_id": project_id,
                "namespace": namespace,
                "changes_detected": needs_update,
                "items_updated": items_updated
            }
        )

        return {
            "success": True,
            "project_id": project_id,
            "namespace": namespace,
            "changes_detected": needs_update,
            "items_updated": items_updated
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error updating dining options for {project_id}",
            exc_info=True,
            extra={"project_id": project_id}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update dining options: {str(e)}"
        )


@knowledge_router.post("/{project_id}/full-menu")
async def update_full_menu(
    project_id: str,
    request: UpdateFullMenuRequest,
    session: Session = Depends(get_db),
    _: bool = Depends(validate_api_key)
):
    """
    Update full menu in Pinecone knowledge base.

    Called by Lambda after fetching full menu from POS.
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

        # Parse menu
        menu_data = json.loads(request.menu_json)

        # Use existing ToastMenuProcessor logic
        from services.knowledge_service.toast import ToastMenuProcessor

        processor = ToastMenuProcessor()
        result = await processor.index_menu_to_pinecone(
            namespace=namespace,
            account_id=account_id,
            menu_data=menu_data,
            integration_id=request.integration_id
        )

        logger.info(
            f"Updated full menu for project {project_id}",
            extra={
                "project_id": project_id,
                "namespace": namespace,
                "items_indexed": result.get('items_indexed', 0)
            }
        )

        return {
            "success": True,
            "project_id": project_id,
            "namespace": namespace,
            "changes_detected": True,
            "items_updated": result.get('items_indexed', 0)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error updating full menu for {project_id}",
            exc_info=True,
            extra={"project_id": project_id}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update full menu: {str(e)}"
        )
```

### Phase 5: Register Router

**File:** `/api/routes/internal/__init__.py` (modify existing)

```python
from fastapi import APIRouter
from .events import events_router
from .scheduled import scheduled_router
from .integrations import integrations_router
from .knowledge import knowledge_router  # NEW

internal_router = APIRouter()

internal_router.include_router(events_router, prefix="/events", tags=["Internal Events"])
internal_router.include_router(scheduled_router, prefix="/scheduled", tags=["Scheduled Tasks"])
internal_router.include_router(integrations_router, prefix="/integrations", tags=["Internal Integrations"])
internal_router.include_router(knowledge_router, prefix="/knowledge", tags=["Internal Knowledge"])  # NEW
```

## Infrastructure as Code

### EventBridge Scheduler (Terraform)

```hcl
resource "aws_scheduler_schedule" "toast_menu_update" {
  name        = "pal-daily-toast-menu-update"
  description = "Triggers Toast menu update daily at 3 AM UTC"

  schedule_expression = "cron(0 3 * * ? *)"

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
      update_type = "dining_options"
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
resource "aws_cloudwatch_event_rule" "toast_menu_update_requested" {
  name           = "pal-toast-menu-update-requested"
  description    = "Routes ToastMenuUpdateRequested events to Lambda"
  event_bus_name = "pal-main-event-bus"

  event_pattern = jsonencode({
    source      = ["pal-mono"]
    detail-type = ["integration.toast.MenuUpdateRequested"]
  })
}

resource "aws_cloudwatch_event_target" "toast_lambda" {
  rule           = aws_cloudwatch_event_rule.toast_menu_update_requested.name
  event_bus_name = "pal-main-event-bus"
  arn            = aws_lambda_function.toast_menu_updater.arn

  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 2
  }

  dead_letter_config {
    arn = aws_sqs_queue.toast_menu_update_dlq.arn
  }
}
```

### Lambda Function (Terraform)

```hcl
resource "aws_lambda_function" "toast_menu_updater" {
  function_name = "pal-toast-menu-updater"
  role          = aws_iam_role.toast_lambda_role.arn

  filename         = "lambdas/toast_menu_updater.zip"
  source_code_hash = filebase64sha256("lambdas/toast_menu_updater.zip")

  runtime = "python3.12"
  handler = "handler.lambda_handler"
  timeout = 600  # 10 minutes (menus can be large)
  memory_size = 1024  # More memory for large menus

  reserved_concurrent_executions = 5  # Respect Toast API rate limits

  environment {
    variables = {
      INTERNAL_API_URL = var.internal_api_url
      INTERNAL_API_KEY = data.aws_secretsmanager_secret_version.internal_api_key.secret_string
      EVENT_BUS_NAME   = "pal-main-event-bus"
    }
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.toast_menu_update_dlq.arn
  }
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.toast_menu_updater.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.toast_menu_update_requested.arn
}
```

## Testing Strategy

### Unit Tests

**Test Discovery Endpoint:**
```python
def test_toast_menu_update_discovery(test_client, test_db):
    # Create test data
    integration = create_toast_integration()
    project = create_project(namespace="test-namespace")
    create_project_integration(project.id, integration.id)

    # Call endpoint
    response = test_client.post(
        "/v1/internal/scheduled/toast-menu-update",
        headers={"X-API-Key": "test-key"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data['events_published'] == 1
    assert data['total_integrations'] == 1
```

**Test Lambda Handler:**
```python
def test_lambda_handler_success(mock_secrets, mock_requests, mock_eventbridge):
    # Mock Toast API responses
    mock_requests.post.return_value.json.return_value = {
        "token": {"accessToken": "test_token"}
    }
    mock_requests.get.return_value.json.return_value = {
        "diningOptions": [...]
    }

    # Mock internal API response
    mock_requests.post.return_value.status_code = 200
    mock_requests.post.return_value.json.return_value = {
        "success": True,
        "changes_detected": True
    }

    # Create test event
    event = {
        "detail": {
            "project_id": "test-id",
            "integration_id": "test-integration",
            "account_id": "test-account",
            "namespace": "test-namespace",
            "secret_key": "test-secret",
            "update_type": "dining_options"
        }
    }

    # Call handler
    result = lambda_handler(event, mock_context)

    assert result['statusCode'] == 200
    assert json.loads(result['body'])['success'] == True
```

### Integration Tests

**End-to-End Test:**
```python
async def test_toast_menu_update_e2e():
    # 1. Call discovery endpoint
    response = await client.post(
        "/v1/internal/scheduled/toast-menu-update",
        headers={"X-API-Key": API_KEY}
    )
    assert response.status_code == 200

    # 2. Wait for Lambda execution
    await asyncio.sleep(15)

    # 3. Verify Pinecone updated
    docs = query_vector_database(
        query_text="dining options",
        namespace=test_namespace,
        account_id=test_account_id,
        filter={"isDiningOptions": True}
    )
    assert len(docs) > 0

    # 4. Verify completion event published
    events = get_events_from_eventbridge(
        detail_type="integration.toast.MenuUpdateCompleted"
    )
    assert len(events) > 0
    assert events[0]['detail']['success'] == True
```

## Monitoring & Alerts

### CloudWatch Metrics

```python
# In Lambda
cloudwatch = boto3.client('cloudwatch')

cloudwatch.put_metric_data(
    Namespace='pal-mono/business-updater',
    MetricData=[
        {
            'MetricName': 'ToastMenuUpdateSuccess',
            'Value': 1.0,
            'Unit': 'Count',
            'Dimensions': [
                {'Name': 'UpdateType', 'Value': update_type},
                {'Name': 'Environment', 'Value': os.environ['ENVIRONMENT']}
            ]
        },
        {
            'MetricName': 'ToastMenuUpdateDuration',
            'Value': duration_ms,
            'Unit': 'Milliseconds',
            'Dimensions': [
                {'Name': 'UpdateType', 'Value': update_type}
            ]
        },
        {
            'MetricName': 'MenuChangesDetected',
            'Value': 1.0 if changes_detected else 0.0,
            'Unit': 'Count'
        }
    ]
)
```

### CloudWatch Alarms

```hcl
resource "aws_cloudwatch_metric_alarm" "toast_menu_update_failures" {
  alarm_name          = "pal-toast-menu-update-failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 3600
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Alert when Toast menu update has more than 5 failures in 1 hour"

  dimensions = {
    FunctionName = aws_lambda_function.toast_menu_updater.function_name
  }

  alarm_actions = [aws_sns_topic.ops_alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "toast_dlq_messages" {
  alarm_name          = "pal-toast-menu-update-dlq"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Average"
  threshold           = 0
  alarm_description   = "Alert when messages in Toast menu update DLQ"

  dimensions = {
    QueueName = aws_sqs_queue.toast_menu_update_dlq.name
  }

  alarm_actions = [aws_sns_topic.ops_alerts.arn]
}
```

## Rollback Plan

### Phase 1: Disable Scheduler
```bash
aws scheduler update-schedule \
  --name pal-daily-toast-menu-update \
  --state DISABLED
```

### Phase 2: Check DLQ
```bash
aws sqs receive-message \
  --queue-url https://sqs.us-east-1.amazonaws.com/.../toast-menu-update-dlq \
  --max-number-of-messages 10
```

### Phase 3: Manual Trigger (Old Endpoint)
```bash
curl -X POST https://api.pal.com/v1/integrations/toast/refresh-dining-options
```

### Phase 4: Rollback Code
```bash
git revert <commit-hash>
./scripts/deploy.sh lat
```

## Future Enhancements

1. **Smart Updates** - Only update if menu.lastUpdated changed
2. **Incremental Updates** - Update only changed menu items
3. **Multi-Location** - Handle restaurants with multiple locations
4. **Menu Versioning** - Track menu history in database
5. **Diff Visualization** - Show what changed in menu
6. **Agent Notifications** - Notify agents when menu updates

## References

- Current Implementation: `/api/routes/integrations/toast/_implementation.py:339-365`
- Menu Processor: `/services/knowledge_service/toast/_implementation.py`
- Toast API Docs: https://doc.toasttab.com/
- EventBridge EventBridge: https://docs.aws.amazon.com/eventbridge/
