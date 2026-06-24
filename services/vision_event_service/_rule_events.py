from __future__ import annotations

import asyncio
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository import (
    VisionRuleEventRepository,
    VisionStateChangeEventRepository,
)
from db.pal_repository.data_classes.vision_rule_event import VisionRuleEventData
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
from services.vision_event_service.limits import (
    RULE_EVENT_VIDEO_LOOKUP_MAX_DURATION_MINUTES,
    RULE_EVENT_VIDEO_LOOKUP_MAX_SEGMENTS,
)
from utils.log import logger

_VIDEO_FILE_EXTENSIONS = (".mp4", ".mov", ".mkv", ".avi", ".webm")


@dataclass(frozen=True)
class RuleEventVideoData:
    s3_key: str
    url: str
    segment_start_time: datetime
    segment_end_time: datetime


@dataclass(frozen=True)
class RuleEventVideoLookupData:
    rule_event_id: uuid.UUID
    state_change_event_id: uuid.UUID
    videos: list[RuleEventVideoData]

    @property
    def video_count(self) -> int:
        return len(self.videos)


class RuleEventDurationLimitError(ValueError):
    """Raised when a rule event duration would produce an unsafe video lookup."""


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


def _as_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _floor_to_minute(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def _ceil_to_minute(value: datetime) -> datetime:
    floored_value = _floor_to_minute(value)
    if value == floored_value:
        return value
    return floored_value + timedelta(minutes=1)


def _validate_rule_event_duration(duration: Decimal) -> None:
    if duration < 0:
        raise RuleEventDurationLimitError("Rule event duration must be non-negative")
    if duration > RULE_EVENT_VIDEO_LOOKUP_MAX_DURATION_MINUTES:
        raise RuleEventDurationLimitError(
            "Rule event duration must be at most "
            f"{RULE_EVENT_VIDEO_LOOKUP_MAX_DURATION_MINUTES} minutes"
        )


def _estimated_video_segment_count(start_time: datetime, end_time: datetime) -> int:
    window_seconds = (end_time - start_time).total_seconds()
    return math.ceil(window_seconds / ONE_MINUTE_VIDEO_SECONDS)


def _video_prefix_for_frame_s3_key(frame_s3_key: str | None) -> str | None:
    if not frame_s3_key:
        return None

    if "/images/" in frame_s3_key:
        camera_prefix, _separator, _image_path = frame_s3_key.partition("/images/")
        return f"{camera_prefix}/videos/"

    if "/videos/" in frame_s3_key:
        camera_prefix, _separator, _video_path = frame_s3_key.partition("/videos/")
        return f"{camera_prefix}/videos/"

    return None


def _video_key_for_frame_s3_key(frame_s3_key: str | None) -> str | None:
    if not frame_s3_key or "/videos/" not in frame_s3_key:
        return None

    filename = frame_s3_key.rsplit("/", 1)[-1]
    if not filename.lower().endswith(_VIDEO_FILE_EXTENSIONS):
        return None

    return frame_s3_key


def _video_segment_start_time_for_key(video_key: str) -> datetime | None:
    filename = video_key.rsplit("/", 1)[-1]
    stem, _separator, _extension = filename.rpartition(".")
    try:
        return datetime.strptime(stem, "%Y-%m-%d_%H-%M-%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _video_lookup_window_for_rule_event(
    rule_event: VisionRuleEventData,
) -> tuple[datetime, datetime] | None:
    _validate_rule_event_duration(rule_event.duration)
    if rule_event.duration == 0:
        return None

    window_end_time = _as_utc_datetime(rule_event.triggered_at)
    window_start_time = window_end_time - timedelta(minutes=float(rule_event.duration))
    lookup_start_time = _floor_to_minute(window_start_time)
    lookup_end_time = _ceil_to_minute(window_end_time)
    estimated_segment_count = _estimated_video_segment_count(
        lookup_start_time,
        lookup_end_time,
    )
    if estimated_segment_count > RULE_EVENT_VIDEO_LOOKUP_MAX_SEGMENTS:
        raise RuleEventDurationLimitError(
            "Rule event video lookup would exceed "
            f"{RULE_EVENT_VIDEO_LOOKUP_MAX_SEGMENTS} video segments"
        )
    return lookup_start_time, lookup_end_time


def _video_response(segment: CameraVideoSegment) -> RuleEventVideoData:
    return RuleEventVideoData(
        s3_key=segment.s3_key,
        url=segment.url,
        segment_start_time=segment.segment_start_time,
        segment_end_time=segment.segment_end_time,
    )


async def _direct_video_response_for_key(
    video_key: str | None,
) -> RuleEventVideoData | None:
    if video_key is None:
        return None

    segment_start_time = _video_segment_start_time_for_key(video_key)
    if segment_start_time is None:
        return None

    url = await _presign_asset_uri(video_key)
    if not url:
        return None

    return RuleEventVideoData(
        s3_key=video_key,
        url=url,
        segment_start_time=segment_start_time,
        segment_end_time=segment_start_time
        + timedelta(seconds=ONE_MINUTE_VIDEO_SECONDS),
    )


async def _lookup_rule_event_videos(
    rule_event: VisionRuleEventData,
    state_change_event: VisionStateChangeEventData,
) -> list[RuleEventVideoData]:
    video_prefix = _video_prefix_for_frame_s3_key(state_change_event.frame_s3_key)
    if video_prefix is None:
        return []

    videos: list[RuleEventVideoData] = []
    video_window = _video_lookup_window_for_rule_event(rule_event)
    if video_window is not None:
        start_time, end_time = video_window
        segments = await lookup_camera_video_segments(
            video_prefix=video_prefix,
            start_time=start_time,
            end_time=end_time,
            max_segments=RULE_EVENT_VIDEO_LOOKUP_MAX_SEGMENTS,
        )
        videos = [_video_response(segment) for segment in segments]

    direct_video = await _direct_video_response_for_key(
        _video_key_for_frame_s3_key(state_change_event.frame_s3_key)
    )
    if direct_video is not None and all(
        video.s3_key != direct_video.s3_key for video in videos
    ):
        videos.append(direct_video)

    return sorted(videos, key=lambda video: (video.segment_start_time, video.s3_key))[
        :RULE_EVENT_VIDEO_LOOKUP_MAX_SEGMENTS
    ]


async def get_rule_event(
    session: AsyncSession,
    event_id: uuid.UUID,
    account_name: str,
) -> VisionRuleEventData:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionRuleEventRepository(session)
    data = await repo.get_by_id_for_account(event_id, account.id)
    if not data:
        raise ValueError(f"Rule event {event_id} not found")
    return data


async def lookup_rule_event_videos(
    session: AsyncSession,
    event_id: uuid.UUID,
    account_name: str,
) -> RuleEventVideoLookupData:
    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    rule_event_repo = VisionRuleEventRepository(session)
    rule_event = await rule_event_repo.get_by_id_for_account(event_id, account.id)
    if not rule_event:
        raise ValueError(f"Rule event {event_id} not found")

    state_event_repo = VisionStateChangeEventRepository(session)
    state_change_event = await state_event_repo.get_by_id_for_account(
        rule_event.state_change_event_id,
        account.id,
    )
    if not state_change_event:
        raise ValueError(
            f"State change event {rule_event.state_change_event_id} not found"
        )

    videos = await _lookup_rule_event_videos(rule_event, state_change_event)
    return RuleEventVideoLookupData(
        rule_event_id=rule_event.id,
        state_change_event_id=state_change_event.id,
        videos=videos,
    )


async def list_rule_events(
    session: AsyncSession,
    account_name: str,
    rule_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    manually_adjusted: bool | None = None,
) -> list[VisionRuleEventData]:
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
        manually_adjusted=manually_adjusted,
    )
    return events


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
    triggered_at: datetime,
    duration: Decimal,
    manually_adjusted: bool,
    account_name: str,
) -> VisionRuleEventData:
    _validate_rule_event_duration(duration)

    account = await account_service.get_account_async(session, account_name)
    if not account:
        raise ValueError(f"Account {account_name} not found")

    repo = VisionRuleEventRepository(session)
    data = await repo.update_for_account(
        event_id=event_id,
        account_id=account.id,
        triggered_at=triggered_at,
        duration=duration,
        manually_adjusted=manually_adjusted,
    )
    if not data:
        raise ValueError(f"Rule event {event_id} not found")

    logger.info(
        "[Vision Event] Updated rule event",
        extra={"event_id": str(event_id)},
    )
    return data
