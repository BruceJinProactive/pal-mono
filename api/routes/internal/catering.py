"""Internal API endpoints for catering events from Lambda processors."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.routes.catering._implementation import handle_catering_event
from api.schemas.catering.catering import EventBridgeEvent

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
