"""Vision Rule Event API Routes Implementation."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.vision_rule_event import (
    ListVisionRuleEventsResponse,
    VisionRuleEventResponse,
)
from services import vision_event_service
from utils.log import logger
from utils.otel import traced


@traced("vision_rule_event.get")
async def get_rule_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    account_name: str,
) -> VisionRuleEventResponse:
    try:
        return await vision_event_service.get_rule_event(
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
            "[Vision RuleEvent] Failed to get event",
            exc_info=True,
            extra={"event_id": str(event_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get rule event",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_rule_event.list")
async def list_rule_events(
    session: AsyncSession,
    account_name: str,
    rule_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 100,
) -> ListVisionRuleEventsResponse:
    try:
        return await vision_event_service.list_rule_events(
            session=session,
            account_name=account_name,
            rule_id=rule_id,
            entity_id=entity_id,
            start=start,
            end=end,
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
            "[Vision RuleEvent] Failed to list events",
            exc_info=True,
            extra={"account_name": account_name},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list rule events",
            headers={"Content-Type": "application/json"},
        )


@traced("vision_rule_event.delete")
async def delete_rule_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    account_name: str,
) -> None:
    try:
        await vision_event_service.delete_rule_event(
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
            "[Vision RuleEvent] Failed to delete event",
            exc_info=True,
            extra={"event_id": str(event_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete rule event",
            headers={"Content-Type": "application/json"},
        )
