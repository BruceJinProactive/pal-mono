"""Vision Rule Event API Routes Implementation."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.vision_rule_event import (
    ListVisionRuleEventsResponse,
    UpdateVisionRuleEventRequest,
    VisionRuleEventResponse,
    VisionRuleEventVideo,
    VisionRuleEventVideoLookupResponse,
)
from db.pal_repository.data_classes.vision_rule_event import VisionRuleEventData
from services import vision_event_service
from services.vision_event_service import (
    RuleEventDurationLimitError,
    RuleEventVideoData,
    RuleEventVideoLookupData,
)
from utils.log import logger
from utils.otel import traced


def _rule_event_response(data: VisionRuleEventData) -> VisionRuleEventResponse:
    return VisionRuleEventResponse(
        id=data.id,
        rule_id=data.rule_id,
        entity_id=data.entity_id,
        state_change_event_id=data.state_change_event_id,
        severity=data.severity,
        duration=data.duration,
        manually_adjusted=data.manually_adjusted,
        triggered_at=data.triggered_at,
        event_metadata=data.event_metadata,
    )


def _list_rule_events_response(
    events: list[VisionRuleEventData],
) -> ListVisionRuleEventsResponse:
    items = [_rule_event_response(event) for event in events]
    return ListVisionRuleEventsResponse(items=items, total=len(items))


def _video_response(data: RuleEventVideoData) -> VisionRuleEventVideo:
    return VisionRuleEventVideo(
        s3_key=data.s3_key,
        url=data.url,
        segment_start_time=data.segment_start_time,
        segment_end_time=data.segment_end_time,
    )


def _video_lookup_response(
    data: RuleEventVideoLookupData,
) -> VisionRuleEventVideoLookupResponse:
    videos = [_video_response(video) for video in data.videos]
    return VisionRuleEventVideoLookupResponse(
        rule_event_id=data.rule_event_id,
        state_change_event_id=data.state_change_event_id,
        videos=videos,
        video_count=len(videos),
    )


@traced("vision_rule_event.get")
async def get_rule_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    account_name: str,
) -> VisionRuleEventResponse:
    try:
        data = await vision_event_service.get_rule_event(
            session=session,
            event_id=event_id,
            account_name=account_name,
        )
        return _rule_event_response(data)
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
    manually_adjusted: bool | None = None,
) -> ListVisionRuleEventsResponse:
    try:
        events = await vision_event_service.list_rule_events(
            session=session,
            account_name=account_name,
            rule_id=rule_id,
            entity_id=entity_id,
            start=start,
            end=end,
            manually_adjusted=manually_adjusted,
        )
        return _list_rule_events_response(events)
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


@traced("vision_rule_event.lookup_videos")
async def lookup_rule_event_videos(
    session: AsyncSession,
    event_id: uuid.UUID,
    account_name: str,
) -> VisionRuleEventVideoLookupResponse:
    try:
        data = await vision_event_service.lookup_rule_event_videos(
            session=session,
            event_id=event_id,
            account_name=account_name,
        )
        return _video_lookup_response(data)
    except RuleEventDurationLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision RuleEvent] Failed to lookup event videos",
            exc_info=True,
            extra={"event_id": str(event_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to lookup rule event videos",
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


@traced("vision_rule_event.update")
async def update_rule_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    account_name: str,
    request: UpdateVisionRuleEventRequest,
) -> VisionRuleEventResponse:
    try:
        data = await vision_event_service.update_rule_event(
            session=session,
            event_id=event_id,
            triggered_at=request.triggered_at,
            duration=request.duration,
            manually_adjusted=request.manually_adjusted,
            account_name=account_name,
        )
        return _rule_event_response(data)
    except RuleEventDurationLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception:
        logger.error(
            "[Vision RuleEvent] Failed to update event",
            exc_info=True,
            extra={"event_id": str(event_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update rule event",
            headers={"Content-Type": "application/json"},
        )
