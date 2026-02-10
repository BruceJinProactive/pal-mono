"""
Event definitions for AWS EventBridge.

All events must inherit from BaseEvent and define their structure and DetailType.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, ClassVar, Dict
from uuid import UUID


@dataclass
class BaseEvent:
    """
    Base class for all events.

    All events must inherit from this class and define:
    - detail_type: The EventBridge DetailType (class variable)
    - Event-specific fields as instance variables
    """

    # Subclasses must override this
    detail_type: ClassVar[str]

    def to_detail(self) -> Dict[str, Any]:
        """
        Convert the event to a dictionary for EventBridge detail.

        Handles UUID and datetime serialization automatically.
        Includes the detail_type in the output.
        """
        detail = {"detail_type": self.detail_type}
        for key, value in asdict(self).items():
            if isinstance(value, UUID):
                detail[key] = str(value)
            elif isinstance(value, datetime):
                detail[key] = value.isoformat()
            else:
                detail[key] = value
        return detail


@dataclass
class SampleEvent(BaseEvent):
    """Simple event for testing or sending basic messages to EventBridge."""

    detail_type: ClassVar[str] = "sample.Message"

    message: str
    timestamp: datetime


@dataclass
class CateringRequestCreated(BaseEvent):
    """Event published when a catering request is created."""

    detail_type: ClassVar[str] = "catering.RequestCreated"

    catering_request_id: UUID
    account_id: UUID
    event_date: datetime
    guest_count: int
    idempotency_key: str
    created_at: datetime


@dataclass
class CateringRequestUpdated(BaseEvent):
    """Event published when a catering request is updated."""

    detail_type: ClassVar[str] = "catering.RequestUpdated"

    catering_request_id: UUID
    account_id: UUID
    updated_fields: list[str]
    updated_at: datetime


@dataclass
class CateringRequestCancelled(BaseEvent):
    """Event published when a catering request is cancelled."""

    detail_type: ClassVar[str] = "catering.RequestCancelled"

    catering_request_id: UUID
    account_id: UUID
    cancellation_reason: str | None
    cancelled_at: datetime


@dataclass
class GoogleBusinessHoursUpdateRequested(BaseEvent):
    """Event published when business hours need updating from Google for a specific store."""

    detail_type: ClassVar[str] = "integration.google.BusinessHoursUpdateRequested"

    # Resource identifiers (required fields first)
    project_id: UUID  # The store/location
    project_name: str
    account_id: UUID  # Parent account (for context)
    account_name: str
    google_place_id: str
    requested_at: datetime

    # Optional fields with defaults
    requested_by: str = "scheduler"  # or "manual"
    last_updated: datetime | None = None  # When hours were last fetched


@dataclass
class KnowledgeUpdateRequested(BaseEvent):
    """Event published when knowledge base needs updating for a project with Adora POS integration."""

    detail_type: ClassVar[str] = "KnowledgeUpdateRequest"

    # Resource identifiers (required fields first)
    project_id: UUID  # The store/location
    account_id: UUID  # Parent account (for context)
    integration_id: UUID  # The integration
    project_integration_id: UUID  # The project integration
    requested_at: datetime


@dataclass
class DatasetGenerationRequested(BaseEvent):
    """Event published when dataset generation is requested from orchestrator."""

    detail_type: ClassVar[str] = "datasets.GenerationRequested"

    job_id: str  # UUID string generated for this job
    agent_id: UUID  # Agent identifier
    project: str  # Project name
    account_name: str  # Account identifier
    actions: Dict[str, Any]  # Dataset actions (create/update/delete/noop)
    requested_at: datetime


@dataclass
class RoutineExecutionGenerationRequested(BaseEvent):
    """Event published when routine execution generation is requested."""

    detail_type: ClassVar[str] = "routine.ExecutionGenerationRequested"

    routine_id: UUID
    schedule_id: UUID
    project_id: UUID
    account_id: UUID
    generation_count: int  # Number of executions to generate (e.g., 30)
    last_execution_date: str | None  # ISO date string of last execution (YYYY-MM-DD)
    requested_at: datetime
    requested_by: str = "scheduler"  # "scheduler" or "api"


@dataclass
class RoutineScheduleUpdated(BaseEvent):
    """Event published when a routine schedule is updated."""

    detail_type: ClassVar[str] = "routine.ScheduleUpdated"

    routine_id: UUID
    schedule_id: UUID
    project_id: UUID
    account_id: UUID
    requires_regeneration: bool
    updated_at: datetime
