import asyncio

from . import _eventbridge
from .schema import (
    BaseEvent,
    CateringRequestCancelled,
    CateringRequestCreated,
    CateringRequestUpdated,
    DatasetGenerationRequested,
    GoogleBusinessHoursUpdateRequested,
    KnowledgeUpdateRequested,
    RoutineExecutionGenerationRequested,
    RoutineScheduleUpdated,
    SampleEvent,
)

# Fixed source for all events from pal-mono
EVENT_SOURCE = "pal-mono"


async def publish_event(event: BaseEvent) -> bool:
    """
    Publish an event to AWS EventBridge.

    This is the main gateway for publishing events to AWS EventBridge.
    All events go through this service to ensure consistent logging,
    error handling, and event formatting.

    All events are published with source='pal-mono'. The DetailType is embedded
    in the event class and included in the detail payload.

    The EventBridge bus name is read from the EVENT_BUS_NAME environment
    variable (required - will raise ValueError if not set).

    Args:
        event (BaseEvent): The event to publish

    Returns:
        bool: True if event was published successfully, False otherwise

    Example:
        >>> from events import CateringRequestCreated, publish_event
        >>> from datetime import datetime
        >>> from uuid import UUID
        >>>
        >>> event = CateringRequestCreated(
        ...     catering_request_id=UUID('...'),
        ...     account_id=UUID('...'),
        ...     event_date=datetime(2025, 1, 15),
        ...     guest_count=50,
        ...     idempotency_key='unique-key',
        ...     created_at=datetime.utcnow()
        ... )
        >>> await publish_event(event)
        True
    """
    # Get the DetailType from the event class
    detail_type = event.detail_type

    # Convert event to detail dictionary (includes detail_type)
    detail = event.to_detail()

    # Run blocking boto3 call in thread to avoid blocking event loop
    return await asyncio.to_thread(
        _eventbridge.publish_event,
        EVENT_SOURCE,
        detail_type,
        detail,
    )


__all__ = [
    # Main function
    "publish_event",
    # Event classes
    "SampleEvent",
    "CateringRequestCreated",
    "CateringRequestUpdated",
    "CateringRequestCancelled",
    "DatasetGenerationRequested",
    "GoogleBusinessHoursUpdateRequested",
    "KnowledgeUpdateRequested",
    "RoutineExecutionGenerationRequested",
    "RoutineScheduleUpdated",
]
