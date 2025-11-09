"""Internal API endpoints for EventBridge event publishing."""

from datetime import datetime, timezone

from fastapi import APIRouter

from events import SampleEvent, publish_event

events_router = APIRouter(prefix="/events")


@events_router.post("/sample")
async def publish_sample_event():
    """
    Publish a sample event to EventBridge.

    This is for internal validation purposes. It publishes a SampleEvent
    to verify EventBridge integration is working correctly.

    Returns:
        dict: Success status and event details
    """
    event = SampleEvent(
        message="Sample event from internal API",
        timestamp=datetime.now(timezone.utc),
    )

    # publish_event is now async
    success = await publish_event(event)

    return {
        "success": success,
        "event": {
            "detail_type": event.detail_type,
            "message": event.message,
            "timestamp": event.timestamp.isoformat(),
        },
    }
