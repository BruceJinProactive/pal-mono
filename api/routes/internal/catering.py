"""Internal API endpoints for catering events from Lambda processors."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.routes.catering._implementation import handle_catering_event
from api.schemas.catering.catering import CateringReminderResponse, EventBridgeEvent
from services.catering_service import send_catering_inquiry_reminders

catering_router = APIRouter(prefix="/catering", tags=["internal-catering"])


@catering_router.post("/events", status_code=status.HTTP_200_OK)
async def handle_internal_catering_event(
    event: EventBridgeEvent,
    session: AsyncSession = Depends(db.get_db_async),
):
    """
    Handle catering events from internal Lambda processors.

    This endpoint is called by the pal-catering-processor Lambda through
    the internal API Gateway with IAM authentication (SigV4 signing).
    It reuses the same implementation as the public /v1/catering/events endpoint.
    """
    return await handle_catering_event(event, session)


@catering_router.post(
    "/inquiry-reminders",
    status_code=status.HTTP_200_OK,
    response_model=CateringReminderResponse,
)
async def process_inquiry_reminders(
    session: AsyncSession = Depends(db.get_db_async),
) -> CateringReminderResponse:
    """
    Send reminder SMS for catering inquiries that are exactly 2 days old.

    Called daily by EventBridge Scheduler. Processes all projects in one pass,
    sending one reminder SMS per project to the catering manager for any
    INQUIRY requests whose event hasn't passed.
    """
    result = await send_catering_inquiry_reminders(session)
    return CateringReminderResponse(
        success=result.success,
        projects_checked=result.projects_checked,
        reminders_sent=result.reminders_sent,
        errors=result.errors,
    )
