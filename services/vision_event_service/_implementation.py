from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.vision_state_change_event import (
    CreateStateChangeEventRequest,
    ListStateChangeEventsResponse,
    StateChangeEventResponse,
    UpdateStateChangeEventRequest,
)
from db.pal_repository import (
    VisionEntityRepository,
    VisionEntityStateDefinitionRepository,
    VisionStateChangeEventRepository,
)
from db.pal_repository.data_classes.vision_state_change_event import (
    VisionStateChangeEventData,
)
from services import account_service
from services.asset_service._utils import map_uri_to_s3_url
from services.vision_observation_service._workflow import handle_state_change_rules
from utils.log import logger


async def _presign_asset_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    if uri.startswith(("http://", "https://")):
        return uri
    try:
        url = await asyncio.to_thread(map_uri_to_s3_url, uri)
        return url or None
    except Exception:
        return None


async def _presign_frame_s3_key(frame_s3_key: str | None) -> str | None:
    return await _presign_asset_uri(frame_s3_key)


def _metadata_video_url(metadata: dict[str, Any]) -> str | None:
    video_url = metadata.get("video_url")
    return video_url if isinstance(video_url, str) else None


def _video_uri_for_frame_s3_key(frame_s3_key: str | None) -> str | None:
    if not frame_s3_key or "/images/" not in frame_s3_key:
        return None

    path, filename = frame_s3_key.rsplit("/", 1)
    stem, _, _extension = filename.rpartition(".")
    try:
        captured_at = datetime.strptime(stem, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None

    video_start = captured_at.replace(second=0, microsecond=0)
    video_path = path.replace("/images/", "/videos/", 1)
    video_filename = f"{video_start.strftime('%Y-%m-%d_%H-%M')}-00.mp4"
    return f"{video_path}/{video_filename}"


async def _video_url_for_event(
    data: VisionStateChangeEventData,
    metadata: dict[str, Any],
) -> str | None:
    video_uri = _metadata_video_url(metadata) or _video_uri_for_frame_s3_key(
        data.frame_s3_key
    )
    return await _presign_asset_uri(video_uri)


async def _build_response(
    data: VisionStateChangeEventData,
    include_video: bool = False,
) -> StateChangeEventResponse:
    frame_url = await _presign_frame_s3_key(data.frame_s3_key)
    metadata = data.event_metadata
    video_url = await _video_url_for_event(data, metadata) if include_video else None
    return StateChangeEventResponse(
        id=data.id,
        entity_id=data.entity_id,
        new_state_id=data.new_state_id,
        observed_at=data.observed_at,
        camera_config_id=data.camera_config_id,
        previous_state_id=data.previous_state_id,
        confidence=data.confidence,
        frame_s3_key=frame_url,
        video_url=video_url,
        event_metadata=metadata,
        is_test=metadata.get("is_test"),
        test_group=metadata.get("test_group"),
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

    entity_repo = VisionEntityRepository(session)
    entity = await entity_repo.get_by_id(request.entity_id)

    sd_repo = VisionEntityStateDefinitionRepository(session)
    state_def = await sd_repo.get_by_id(request.new_state_id) if entity else None
    previous_state_def = (
        await sd_repo.get_by_id(request.previous_state_id)
        if entity and request.previous_state_id
        else None
    )

    metadata = dict(request.event_metadata)
    if request.is_test is not None:
        metadata["is_test"] = request.is_test
    if request.test_group is not None:
        metadata["test_group"] = request.test_group

    record = VisionStateChangeEventData(
        id=uuid.uuid4(),
        entity_id=request.entity_id,
        new_state_id=request.new_state_id,
        observed_at=request.observed_at or datetime.now(timezone.utc),
        event_metadata=metadata,
        camera_config_id=request.camera_config_id,
        previous_state_id=request.previous_state_id,
        confidence=request.confidence,
        frame_s3_key=request.frame_s3_key,
    )

    await repo.create(record)
    if (
        entity is not None
        and state_def is not None
        and state_def.entity_type_id == entity.entity_type_id
    ):
        await handle_state_change_rules(
            session=session,
            entity=entity,
            state_change_event=record,
            state_name=state_def.name,
            previous_state_name=(
                previous_state_def.name
                if previous_state_def
                and previous_state_def.entity_type_id == entity.entity_type_id
                else None
            ),
        )
    logger.info(
        "[Vision Event] Created state change event",
        extra={"event_id": str(record.id), "entity_id": str(record.entity_id)},
    )
    return await _build_response(record)


async def get_state_change_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    account_name: str,
    include_video: bool = False,
) -> StateChangeEventResponse:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionStateChangeEventRepository(session)
    data = await repo.get_by_id_for_account(event_id, account.id)
    if not data:
        raise ValueError(f"State change event {event_id} not found")
    return await _build_response(data, include_video=include_video)


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
        page=page,
        limit=limit,
    )
    items = await asyncio.gather(*[_build_response(e) for e in events.items])
    return ListStateChangeEventsResponse(
        items=list(items),
        total=events.total,
        page=page,
        page_size=limit,
    )


async def update_state_change_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    request: UpdateStateChangeEventRequest,
    account_name: str,
) -> StateChangeEventResponse:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    account_id = account.id
    repo = VisionStateChangeEventRepository(session)
    data = await repo.get_by_id_for_account(event_id, account_id)
    if not data:
        raise ValueError(f"State change event {event_id} not found")

    updated_metadata = dict(data.event_metadata)
    if request.event_metadata is not None:
        updated_metadata.update(request.event_metadata)
    if request.is_test is not None:
        updated_metadata["is_test"] = request.is_test
    if request.test_group is not None:
        updated_metadata["test_group"] = request.test_group

    await repo.update_metadata(event_id, data.observed_at, updated_metadata)
    updated_data = await repo.get_by_id_for_account(event_id, account_id)
    if not updated_data:
        raise ValueError(f"State change event {event_id} not found after update")

    logger.info(
        "[Vision Event] Updated state change event metadata",
        extra={"event_id": str(event_id)},
    )
    return await _build_response(updated_data)


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
