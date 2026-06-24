"""Vision State Change Event API Routes Implementation."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.vision_state_change_event import (
    CreateStateChangeEventRequest,
    ListStateChangeEventsResponse,
    StateChangeEventResponse,
    UpdateStateChangeEventRequest,
)
from services import vision_event_service
from utils.log import logger
from utils.otel import traced


@traced("vision_state_change_event.create")
async def create_state_change_event(
    session: AsyncSession,
    request: CreateStateChangeEventRequest,
    account_name: str,
) -> StateChangeEventResponse:
    try:
        return await vision_event_service.create_state_change_event(
            session=session,
            request=request,
            account_name=account_name,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision StateChangeEvent] Failed to create event",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create state change event",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_state_change_event.get")
async def get_state_change_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    account_name: str,
) -> StateChangeEventResponse:
    try:
        return await vision_event_service.get_state_change_event(
            session=session,
            event_id=event_id,
            account_name=account_name,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision StateChangeEvent] Failed to get event",
            exc_info=True,
            extra={"event_id": str(event_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get state change event",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_state_change_event.list")
async def list_state_change_events(
    session: AsyncSession,
    account_name: str,
    project_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    page: int = 1,
    limit: int = 100,
) -> ListStateChangeEventsResponse:
    try:
        return await vision_event_service.list_state_change_events(
            session=session,
            account_name=account_name,
            project_id=project_id,
            entity_id=entity_id,
            start=start,
            end=end,
            page=page,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision StateChangeEvent] Failed to list events",
            exc_info=True,
            extra={
                "account_name": account_name,
                "project_id": str(project_id),
                "entity_id": str(entity_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list state change events",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_state_change_event.update")
async def update_state_change_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    request: UpdateStateChangeEventRequest,
    account_name: str,
) -> StateChangeEventResponse:
    try:
        return await vision_event_service.update_state_change_event(
            session=session,
            event_id=event_id,
            request=request,
            account_name=account_name,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision StateChangeEvent] Failed to update event",
            exc_info=True,
            extra={"event_id": str(event_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update state change event",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_state_change_event.delete")
async def delete_state_change_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    account_name: str,
) -> None:
    try:
        await vision_event_service.delete_state_change_event(
            session=session,
            event_id=event_id,
            account_name=account_name,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision StateChangeEvent] Failed to delete event",
            exc_info=True,
            extra={"event_id": str(event_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete state change event",
            headers={"Content-Type": "application/json"},
        )
