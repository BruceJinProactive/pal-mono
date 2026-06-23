from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.operations.vision_state_change_event import (
    CreateStateChangeEventRequest,
    ListStateChangeEventsResponse,
    StateChangeEventResponse,
    StateChangeEventVideo,
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
from services.monitoring_service._video import (
    ONE_MINUTE_VIDEO_SECONDS,
    CameraVideoSegment,
    lookup_camera_video_segments,
)
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


def _parse_metadata_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _parse_metadata_duration_seconds(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float) and value > 0:
        return float(value)
    if isinstance(value, str):
        try:
            parsed_value = float(value)
        except ValueError:
            return None
        return parsed_value if parsed_value > 0 else None
    return None


def _metadata_datetime(
    metadata: dict[str, Any],
    keys: tuple[str, ...],
) -> datetime | None:
    for key in keys:
        parsed_value = _parse_metadata_datetime(metadata.get(key))
        if parsed_value is not None:
            return parsed_value
    return None


def _metadata_duration_seconds(metadata: dict[str, Any]) -> float | None:
    for key in ("duration_seconds", "duration", "event_duration_seconds"):
        parsed_value = _parse_metadata_duration_seconds(metadata.get(key))
        if parsed_value is not None:
            return parsed_value
    return None


def _as_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _video_prefix_for_frame_s3_key(frame_s3_key: str | None) -> str | None:
    if not frame_s3_key or "/images/" not in frame_s3_key:
        return None

    camera_prefix, _separator, _image_path = frame_s3_key.partition("/images/")
    return f"{camera_prefix}/videos/"


def _video_window_for_event(
    data: VisionStateChangeEventData,
    metadata: dict[str, Any],
) -> tuple[datetime, datetime]:
    start_time = _metadata_datetime(
        metadata,
        (
            "start_time",
            "event_start_time",
            "duration_start_time",
            "duration_started_at",
        ),
    )
    end_time = _metadata_datetime(
        metadata,
        ("end_time", "event_end_time", "duration_end_time", "duration_ended_at"),
    )
    duration_seconds = _metadata_duration_seconds(metadata)

    if start_time is not None:
        window_start_time = _as_utc_datetime(start_time)
        if end_time is not None:
            window_end_time = _as_utc_datetime(end_time)
            if window_start_time < window_end_time:
                return window_start_time, window_end_time
        if duration_seconds is not None:
            return (
                window_start_time,
                window_start_time + timedelta(seconds=duration_seconds),
            )

    observed_at = _as_utc_datetime(data.observed_at)
    window_start_time = observed_at.replace(second=0, microsecond=0)
    window_duration_seconds = duration_seconds or ONE_MINUTE_VIDEO_SECONDS
    return (
        window_start_time,
        window_start_time + timedelta(seconds=window_duration_seconds),
    )


def _video_response(segment: CameraVideoSegment) -> StateChangeEventVideo:
    return StateChangeEventVideo(
        s3_key=segment.s3_key,
        url=segment.url,
        segment_start_time=segment.segment_start_time,
        segment_end_time=segment.segment_end_time,
    )


async def _videos_for_event(
    data: VisionStateChangeEventData,
    metadata: dict[str, Any],
) -> list[StateChangeEventVideo]:
    video_prefix = _video_prefix_for_frame_s3_key(data.frame_s3_key)
    if video_prefix is None:
        return []

    start_time, end_time = _video_window_for_event(data, metadata)
    segments = await lookup_camera_video_segments(
        video_prefix=video_prefix,
        start_time=start_time,
        end_time=end_time,
    )
    return [_video_response(segment) for segment in segments]


async def _build_response(
    data: VisionStateChangeEventData,
    include_video: bool = False,
) -> StateChangeEventResponse:
    frame_url = await _presign_frame_s3_key(data.frame_s3_key)
    metadata = data.event_metadata
    videos = await _videos_for_event(data, metadata) if include_video else []
    return StateChangeEventResponse(
        id=data.id,
        entity_id=data.entity_id,
        new_state_id=data.new_state_id,
        observed_at=data.observed_at,
        camera_config_id=data.camera_config_id,
        previous_state_id=data.previous_state_id,
        confidence=data.confidence,
        frame_s3_key=frame_url,
        videos=videos,
        video_count=len(videos),
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
    manually_adjusted = request.manually_adjusted or (
        metadata.get("manually_adjusted") is True
    )

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
            manually_adjusted=manually_adjusted,
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
