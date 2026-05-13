from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.vision_state_change_event import (
    CreateStateChangeEventRequest,
    ListStateChangeEventsResponse,
    StateChangeEventResponse,
)
from db.pal_repository import VisionStateChangeEventRepository
from db.pal_repository.data_classes.vision_state_change_event import (
    VisionStateChangeEventData,
)
from services import account_service
from utils.log import logger


def _build_response(data: VisionStateChangeEventData) -> StateChangeEventResponse:
    return StateChangeEventResponse(
        id=data.id,
        entity_id=data.entity_id,
        new_state_id=data.new_state_id,
        observed_at=data.observed_at,
        camera_config_id=data.camera_config_id,
        previous_state_id=data.previous_state_id,
        confidence=data.confidence,
        frame_s3_key=data.frame_s3_key,
        event_metadata=data.event_metadata,
    )


async def create_state_change_event(
    session: AsyncSession,
    request: CreateStateChangeEventRequest,
    account_name: str,
) -> StateChangeEventResponse:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionStateChangeEventRepository(session)

    owns_entity = await repo.verify_entity_belongs_to_account(
        request.entity_id, account.id
    )
    if not owns_entity:
        raise ValueError(
            f"Entity {request.entity_id} does not belong to account {account_name}"
        )

    record = VisionStateChangeEventData(
        id=uuid.uuid4(),
        entity_id=request.entity_id,
        new_state_id=request.new_state_id,
        observed_at=request.observed_at or datetime.now(timezone.utc),
        event_metadata=request.event_metadata,
        camera_config_id=request.camera_config_id,
        previous_state_id=request.previous_state_id,
        confidence=request.confidence,
        frame_s3_key=request.frame_s3_key,
    )

    await repo.create(record)
    logger.info(
        "[Vision Event] Created state change event",
        extra={"event_id": str(record.id), "entity_id": str(record.entity_id)},
    )
    return _build_response(record)


async def get_state_change_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    account_name: str,
) -> StateChangeEventResponse:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionStateChangeEventRepository(session)
    data = await repo.get_by_id_for_account(event_id, account.id)
    if not data:
        raise ValueError(f"State change event {event_id} not found")
    return _build_response(data)


async def list_state_change_events(
    session: AsyncSession,
    account_name: str,
    project_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 100,
) -> ListStateChangeEventsResponse:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionStateChangeEventRepository(session)
    events = await repo.list_by_account(
        account_id=account.id,
        project_id=project_id,
        entity_id=entity_id,
        start=start,
        end=end,
        limit=limit,
    )
    return ListStateChangeEventsResponse(
        items=[_build_response(e) for e in events],
        total=len(events),
    )


async def delete_state_change_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    account_name: str,
) -> None:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionStateChangeEventRepository(session)
    deleted = await repo.delete_for_account(event_id, account.id)
    if not deleted:
        raise ValueError(f"State change event {event_id} not found")
    logger.info(
        "[Vision Event] Deleted state change event",
        extra={"event_id": str(event_id)},
    )
