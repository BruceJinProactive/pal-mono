from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.vision_rule_event import (
    ListVisionRuleEventsResponse,
    UpdateVisionRuleEventRequest,
    VisionRuleEventResponse,
)
from db.pal_repository import VisionRuleEventRepository
from db.pal_repository.data_classes.vision_rule_event import VisionRuleEventData
from services import account_service
from utils.log import logger


def _build_response(data: VisionRuleEventData) -> VisionRuleEventResponse:
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


async def get_rule_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    account_name: str,
) -> VisionRuleEventResponse:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionRuleEventRepository(session)
    data = await repo.get_by_id_for_account(event_id, account.id)
    if not data:
        raise ValueError(f"Rule event {event_id} not found")
    return _build_response(data)


async def list_rule_events(
    session: AsyncSession,
    account_name: str,
    rule_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> ListVisionRuleEventsResponse:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionRuleEventRepository(session)
    events = await repo.list_by_account(
        account_id=account.id,
        rule_id=rule_id,
        entity_id=entity_id,
        start=start,
        end=end,
    )
    items = [_build_response(e) for e in events]
    return ListVisionRuleEventsResponse(items=items, total=len(items))


async def delete_rule_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    account_name: str,
) -> None:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionRuleEventRepository(session)
    deleted = await repo.delete_for_account(event_id, account.id)
    if not deleted:
        raise ValueError(f"Rule event {event_id} not found")
    logger.info(
        "[Vision Event] Deleted rule event",
        extra={"event_id": str(event_id)},
    )


async def update_rule_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    request: UpdateVisionRuleEventRequest,
    account_name: str,
) -> VisionRuleEventResponse:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionRuleEventRepository(session)
    data = await repo.update_for_account(
        event_id=event_id,
        account_id=account.id,
        triggered_at=request.triggered_at,
        duration=request.duration,
        manually_adjusted=request.manually_adjusted,
    )
    if not data:
        raise ValueError(f"Rule event {event_id} not found")

    logger.info(
        "[Vision Event] Updated rule event",
        extra={"event_id": str(event_id)},
    )
    return _build_response(data)
