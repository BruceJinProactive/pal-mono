"""Internal API endpoints for catering events from Lambda processors."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.routes.catering._implementation import handle_catering_event
from api.schemas.catering.catering import CateringReminderResponse, EventBridgeEvent
from services.catering_service import (
    send_catering_inquiry_apologies,
    send_catering_inquiry_reminders,
)

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
    Send reminder SMS for lead-stage catering requests that are exactly 2 days old.

    Called daily by EventBridge Scheduler. Processes all projects in one pass,
    sending one reminder SMS per project to the catering manager for any
    LEAD or legacy INQUIRY requests whose event hasn't passed.
    """
    reminder_result = await send_catering_inquiry_reminders(session)
    apology_result = await send_catering_inquiry_apologies(session)

    combined_errors = reminder_result.errors + apology_result.errors
    return CateringReminderResponse(
        success=len(combined_errors) == 0,
        projects_checked=reminder_result.projects_checked
        + apology_result.projects_checked,
        reminders_sent=reminder_result.reminders_sent,
        apologies_sent=apology_result.apologies_sent,
        errors=combined_errors,
    )
