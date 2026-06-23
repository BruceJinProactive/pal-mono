"""Tests for vision_event_service state change event operations."""

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas.operations.vision_state_change_event import (
    CreateStateChangeEventRequest,
)
from db.pal_repository.data_classes.vision_state_change_event import (
    VisionStateChangeEventData,
    VisionStateChangeEventPage,
)
from services.monitoring_service._video import CameraVideoSegment
from services.vision_event_service._implementation import _presign_frame_s3_key

MODULE = "services.vision_event_service._implementation"

ENTITY_ID = uuid.uuid4()
NEW_STATE_ID = uuid.uuid4()
ACCOUNT_NAME = "test-account"
ACCOUNT_ID = uuid.uuid4()


def _mock_account() -> Any:
    mock = MagicMock()
    mock.id = ACCOUNT_ID
    return mock


def _make_event_data(**overrides: object) -> VisionStateChangeEventData:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "entity_id": ENTITY_ID,
        "new_state_id": NEW_STATE_ID,
        "observed_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "event_metadata": {},
        "camera_config_id": None,
        "previous_state_id": None,
        "confidence": None,
        "frame_s3_key": None,
    }
    defaults.update(overrides)
    return VisionStateChangeEventData(**defaults)  # type: ignore[arg-type]


def _make_video_segment() -> CameraVideoSegment:
    segment_start_time = datetime(2026, 6, 23, 14, 5, 3, tzinfo=timezone.utc)
    return CameraVideoSegment(
        s3_key=(
            "security/cameras/account/project/camera/videos/"
            "2026-06-23/2026-06-23_14-05-03.mp4"
        ),
        url="https://example.com/video.mp4",
        segment_start_time=segment_start_time,
        segment_end_time=datetime(2026, 6, 23, 14, 6, 3, tzinfo=timezone.utc),
    )


class TestCreateStateChangeEvent:

    @pytest.mark.asyncio
    async def test_creates_event(self) -> None:
        session = AsyncMock()
        request = CreateStateChangeEventRequest(
            entity_id=ENTITY_ID,
            new_state_id=NEW_STATE_ID,
            confidence=0.95,
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.verify_entity_belongs_to_account.return_value = True
            repo.create.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                create_state_change_event,
            )

            result = await create_state_change_event(session, request, ACCOUNT_NAME)

            assert result.entity_id == ENTITY_ID
            assert result.new_state_id == NEW_STATE_ID
            assert result.confidence == 0.95
            repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_rule_events_for_matching_state_definition(self) -> None:
        session = AsyncMock()
        entity_type_id = uuid.uuid4()
        entity = MagicMock()
        entity.id = ENTITY_ID
        entity.entity_type_id = entity_type_id
        state_def = MagicMock()
        state_def.id = NEW_STATE_ID
        state_def.entity_type_id = entity_type_id
        state_def.name = "clean"
        previous_state_id = uuid.uuid4()
        previous_state_def = MagicMock()
        previous_state_def.id = previous_state_id
        previous_state_def.entity_type_id = entity_type_id
        previous_state_def.name = "dirty"
        request = CreateStateChangeEventRequest(
            entity_id=ENTITY_ID,
            new_state_id=NEW_STATE_ID,
            previous_state_id=previous_state_id,
            confidence=0.95,
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_repo_cls,
            patch(
                f"{MODULE}.VisionEntityStateDefinitionRepository"
            ) as mock_sd_repo_cls,
            patch(
                f"{MODULE}.handle_state_change_rules",
                new_callable=AsyncMock,
            ) as mock_handle_rules,
        ):
            repo = AsyncMock()
            repo.verify_entity_belongs_to_account.return_value = True
            repo.create.return_value = None
            mock_repo_cls.return_value = repo
            mock_entity_repo_cls.return_value.get_by_id = AsyncMock(return_value=entity)
            mock_sd_repo_cls.return_value.get_by_id = AsyncMock(
                side_effect=[state_def, previous_state_def]
            )

            from services.vision_event_service._implementation import (
                create_state_change_event,
            )

            await create_state_change_event(session, request, ACCOUNT_NAME)

            mock_handle_rules.assert_awaited_once()
            call_kwargs = mock_handle_rules.call_args.kwargs
            assert call_kwargs["entity"] == entity
            assert call_kwargs["state_name"] == "clean"
            assert call_kwargs["previous_state_name"] == "dirty"
            assert call_kwargs["manually_adjusted"] is False

    @pytest.mark.asyncio
    async def test_manual_state_change_marks_generated_rule_events_manual(self) -> None:
        session = AsyncMock()
        entity_type_id = uuid.uuid4()
        entity = MagicMock()
        entity.id = ENTITY_ID
        entity.entity_type_id = entity_type_id
        state_def = MagicMock()
        state_def.id = NEW_STATE_ID
        state_def.entity_type_id = entity_type_id
        state_def.name = "clean"
        request = CreateStateChangeEventRequest(
            entity_id=ENTITY_ID,
            new_state_id=NEW_STATE_ID,
            manually_adjusted=True,
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_repo_cls,
            patch(
                f"{MODULE}.VisionEntityStateDefinitionRepository"
            ) as mock_sd_repo_cls,
            patch(
                f"{MODULE}.handle_state_change_rules",
                new_callable=AsyncMock,
            ) as mock_handle_rules,
        ):
            repo = AsyncMock()
            repo.verify_entity_belongs_to_account.return_value = True
            repo.create.return_value = None
            mock_repo_cls.return_value = repo
            mock_entity_repo_cls.return_value.get_by_id = AsyncMock(return_value=entity)
            mock_sd_repo_cls.return_value.get_by_id = AsyncMock(return_value=state_def)

            from services.vision_event_service._implementation import (
                create_state_change_event,
            )

            await create_state_change_event(session, request, ACCOUNT_NAME)

            mock_handle_rules.assert_awaited_once()
            assert mock_handle_rules.call_args.kwargs["manually_adjusted"] is True

    @pytest.mark.asyncio
    async def test_uses_provided_observed_at(self) -> None:
        session = AsyncMock()
        ts = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        request = CreateStateChangeEventRequest(
            entity_id=ENTITY_ID,
            new_state_id=NEW_STATE_ID,
            observed_at=ts,
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.verify_entity_belongs_to_account.return_value = True
            repo.create.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                create_state_change_event,
            )

            result = await create_state_change_event(session, request, ACCOUNT_NAME)

            assert result.observed_at == ts

    @pytest.mark.asyncio
    async def test_entity_not_owned_raises(self) -> None:
        session = AsyncMock()
        request = CreateStateChangeEventRequest(
            entity_id=ENTITY_ID,
            new_state_id=NEW_STATE_ID,
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.verify_entity_belongs_to_account.return_value = False
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                create_state_change_event,
            )

            with pytest.raises(ValueError, match="does not belong"):
                await create_state_change_event(session, request, ACCOUNT_NAME)


class TestGetStateChangeEvent:

    @pytest.mark.asyncio
    async def test_returns_event(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        event_data = _make_event_data(
            id=event_id,
            event_metadata={"video_url": "security/cameras/video.mp4"},
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
            patch(f"{MODULE}.map_uri_to_s3_url") as mock_map_uri,
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
            ) as mock_lookup,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = event_data
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                get_state_change_event,
            )

            result = await get_state_change_event(session, event_id, ACCOUNT_NAME)

            assert result.id == event_id
            assert result.videos == []
            assert result.video_count == 0
            mock_map_uri.assert_not_called()
            mock_lookup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_omits_videos_by_default(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        event_data = _make_event_data(
            id=event_id,
            frame_s3_key=(
                "security/cameras/account/project/camera/"
                "images/2026-06-23/2026-06-23_14-05-37.jpg"
            ),
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
            patch(
                f"{MODULE}.map_uri_to_s3_url",
                return_value="https://example.com/frame.jpg",
            ),
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
                return_value=[_make_video_segment()],
            ) as mock_lookup,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = event_data
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                get_state_change_event,
            )

            result = await get_state_change_event(session, event_id, ACCOUNT_NAME)

            assert result.videos == []
            assert result.video_count == 0
            mock_lookup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_presigned_video_list_when_included(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        event_data = _make_event_data(
            id=event_id,
            frame_s3_key=(
                "security/cameras/account/project/camera/"
                "images/2026-06-23/2026-06-23_14-05-37.jpg"
            ),
            event_metadata={
                "start_time": "2026-06-23T14:05:37Z",
                "duration_seconds": 1026,
            },
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
            patch(
                f"{MODULE}.map_uri_to_s3_url",
                return_value="https://example.com/frame.jpg",
            ),
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
                return_value=[_make_video_segment()],
            ) as mock_lookup,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = event_data
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                get_state_change_event,
            )

            result = await get_state_change_event(
                session,
                event_id,
                ACCOUNT_NAME,
                include_video=True,
            )

            assert result.video_count == 1
            assert len(result.videos) == 1
            assert result.videos[0].s3_key.endswith("2026-06-23_14-05-03.mp4")
            assert result.videos[0].url == "https://example.com/video.mp4"
            mock_lookup.assert_awaited_once()
            lookup_args = mock_lookup.await_args
            assert lookup_args is not None
            lookup_kwargs = lookup_args.kwargs
            assert lookup_kwargs["video_prefix"] == (
                "security/cameras/account/project/camera/videos/"
            )
            assert lookup_kwargs["start_time"] == datetime(
                2026,
                6,
                23,
                14,
                5,
                37,
                tzinfo=timezone.utc,
            )
            assert lookup_kwargs["end_time"] == datetime(
                2026,
                6,
                23,
                14,
                22,
                43,
                tzinfo=timezone.utc,
            )

    @pytest.mark.asyncio
    async def test_uses_metadata_datetime_end_time_window(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        event_data = _make_event_data(
            id=event_id,
            frame_s3_key=(
                "security/cameras/account/project/camera/"
                "images/2026-06-23/2026-06-23_14-05-37.jpg"
            ),
            event_metadata={
                "start_time": datetime(2026, 6, 23, 14, 5, 37),
                "end_time": datetime(2026, 6, 23, 14, 22, 43, tzinfo=timezone.utc),
            },
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
            patch(
                f"{MODULE}.map_uri_to_s3_url",
                return_value="https://example.com/frame.jpg",
            ),
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_lookup,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = event_data
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                get_state_change_event,
            )

            result = await get_state_change_event(
                session,
                event_id,
                ACCOUNT_NAME,
                include_video=True,
            )

            assert result.video_count == 0
            mock_lookup.assert_awaited_once()
            lookup_args = mock_lookup.await_args
            assert lookup_args is not None
            lookup_kwargs = lookup_args.kwargs
            assert lookup_kwargs["start_time"] == datetime(
                2026,
                6,
                23,
                14,
                5,
                37,
                tzinfo=timezone.utc,
            )
            assert lookup_kwargs["end_time"] == datetime(
                2026,
                6,
                23,
                14,
                22,
                43,
                tzinfo=timezone.utc,
            )

    @pytest.mark.asyncio
    async def test_uses_start_plus_duration_when_end_time_also_present(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        event_data = _make_event_data(
            id=event_id,
            frame_s3_key=(
                "security/cameras/account/project/camera/"
                "images/2026-06-23/2026-06-23_14-05-37.jpg"
            ),
            event_metadata={
                "start_time": "2026-06-23T14:05:37Z",
                "duration_seconds": 120,
                "end_time": "2026-06-23T14:30:00Z",
            },
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
            patch(
                f"{MODULE}.map_uri_to_s3_url",
                return_value="https://example.com/frame.jpg",
            ),
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_lookup,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = event_data
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                get_state_change_event,
            )

            result = await get_state_change_event(
                session,
                event_id,
                ACCOUNT_NAME,
                include_video=True,
            )

            assert result.video_count == 0
            mock_lookup.assert_awaited_once()
            lookup_args = mock_lookup.await_args
            assert lookup_args is not None
            lookup_kwargs = lookup_args.kwargs
            assert lookup_kwargs["start_time"] == datetime(
                2026,
                6,
                23,
                14,
                5,
                37,
                tzinfo=timezone.utc,
            )
            assert lookup_kwargs["end_time"] == datetime(
                2026,
                6,
                23,
                14,
                7,
                37,
                tzinfo=timezone.utc,
            )

    @pytest.mark.asyncio
    async def test_invalid_metadata_window_falls_back_to_observed_minute(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        event_data = _make_event_data(
            id=event_id,
            observed_at=datetime(2026, 6, 23, 14, 5, 37, tzinfo=timezone.utc),
            frame_s3_key=(
                "security/cameras/account/project/camera/"
                "images/2026-06-23/2026-06-23_14-05-37.jpg"
            ),
            event_metadata={
                "start_time": "not-a-date",
                "duration_seconds": "not-a-duration",
            },
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
            patch(
                f"{MODULE}.map_uri_to_s3_url",
                return_value="https://example.com/frame.jpg",
            ),
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_lookup,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = event_data
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                get_state_change_event,
            )

            result = await get_state_change_event(
                session,
                event_id,
                ACCOUNT_NAME,
                include_video=True,
            )

            assert result.video_count == 0
            mock_lookup.assert_awaited_once()
            lookup_args = mock_lookup.await_args
            assert lookup_args is not None
            lookup_kwargs = lookup_args.kwargs
            assert lookup_kwargs["start_time"] == datetime(
                2026,
                6,
                23,
                14,
                5,
                tzinfo=timezone.utc,
            )
            assert lookup_kwargs["end_time"] == datetime(
                2026,
                6,
                23,
                14,
                6,
                tzinfo=timezone.utc,
            )

    @pytest.mark.asyncio
    async def test_uses_string_duration_for_observed_window(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        event_data = _make_event_data(
            id=event_id,
            observed_at=datetime(2026, 6, 23, 14, 5, 37, tzinfo=timezone.utc),
            frame_s3_key=(
                "security/cameras/account/project/camera/"
                "images/2026-06-23/2026-06-23_14-05-37.jpg"
            ),
            event_metadata={"duration_seconds": "90"},
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
            patch(
                f"{MODULE}.map_uri_to_s3_url",
                return_value="https://example.com/frame.jpg",
            ),
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_lookup,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = event_data
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                get_state_change_event,
            )

            result = await get_state_change_event(
                session,
                event_id,
                ACCOUNT_NAME,
                include_video=True,
            )

            assert result.video_count == 0
            mock_lookup.assert_awaited_once()
            lookup_args = mock_lookup.await_args
            assert lookup_args is not None
            lookup_kwargs = lookup_args.kwargs
            assert lookup_kwargs["end_time"] == datetime(
                2026,
                6,
                23,
                14,
                6,
                30,
                tzinfo=timezone.utc,
            )

    @pytest.mark.asyncio
    async def test_ignores_metadata_video_url_when_included(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        event_data = _make_event_data(
            id=event_id,
            event_metadata={"video_url": "security/cameras/video.mp4"},
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
            patch(f"{MODULE}.map_uri_to_s3_url") as mock_map_uri,
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
            ) as mock_lookup,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = event_data
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                get_state_change_event,
            )

            result = await get_state_change_event(
                session,
                event_id,
                ACCOUNT_NAME,
                include_video=True,
            )

            assert result.videos == []
            assert result.video_count == 0
            mock_map_uri.assert_not_called()
            mock_lookup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_uses_observed_minute_when_metadata_window_missing(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        event_data = _make_event_data(
            id=event_id,
            observed_at=datetime(2026, 6, 23, 14, 5, 37, tzinfo=timezone.utc),
            frame_s3_key=(
                "security/cameras/account/project/camera/"
                "images/2026-06-23/2026-06-23_14-05-37.jpg"
            ),
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
            patch(
                f"{MODULE}.map_uri_to_s3_url",
                return_value="https://example.com/frame.jpg",
            ),
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_lookup,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = event_data
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                get_state_change_event,
            )

            result = await get_state_change_event(
                session,
                event_id,
                ACCOUNT_NAME,
                include_video=True,
            )

            assert result.video_count == 0
            mock_lookup.assert_awaited_once()
            lookup_args = mock_lookup.await_args
            assert lookup_args is not None
            lookup_kwargs = lookup_args.kwargs
            assert lookup_kwargs["start_time"] == datetime(
                2026,
                6,
                23,
                14,
                5,
                tzinfo=timezone.utc,
            )
            assert lookup_kwargs["end_time"] == datetime(
                2026,
                6,
                23,
                14,
                6,
                tzinfo=timezone.utc,
            )

    @pytest.mark.asyncio
    async def test_returns_video_frame_key_when_lookup_is_empty(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        video_key = (
            "security/cameras/account/project/camera/"
            "videos/2026-06-23/2026-06-23_14-05-03.mp4"
        )
        event_data = _make_event_data(
            id=event_id,
            observed_at=datetime(2026, 6, 23, 14, 5, 37, tzinfo=timezone.utc),
            frame_s3_key=video_key,
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
            patch(
                f"{MODULE}.map_uri_to_s3_url",
                return_value="https://example.com/video.mp4",
            ),
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_lookup,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = event_data
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                get_state_change_event,
            )

            result = await get_state_change_event(
                session,
                event_id,
                ACCOUNT_NAME,
                include_video=True,
            )

            assert result.video_count == 1
            assert result.videos[0].s3_key == video_key
            assert result.videos[0].url == "https://example.com/video.mp4"
            assert result.videos[0].segment_start_time == datetime(
                2026,
                6,
                23,
                14,
                5,
                3,
                tzinfo=timezone.utc,
            )
            mock_lookup.assert_awaited_once()
            lookup_args = mock_lookup.await_args
            assert lookup_args is not None
            lookup_kwargs = lookup_args.kwargs
            assert lookup_kwargs["video_prefix"] == (
                "security/cameras/account/project/camera/videos/"
            )
            assert lookup_kwargs["start_time"] == datetime(
                2026,
                6,
                23,
                14,
                5,
                tzinfo=timezone.utc,
            )

    @pytest.mark.asyncio
    async def test_returns_empty_for_non_image_frame_key_when_included(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        event_data = _make_event_data(
            id=event_id,
            frame_s3_key="security/cameras/account/project/camera/video.mp4",
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
            patch(
                f"{MODULE}.map_uri_to_s3_url",
                return_value="https://example.com/frame.jpg",
            ),
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
            ) as mock_lookup,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = event_data
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                get_state_change_event,
            )

            result = await get_state_change_event(
                session,
                event_id,
                ACCOUNT_NAME,
                include_video=True,
            )

            assert result.videos == []
            assert result.video_count == 0
            mock_lookup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                get_state_change_event,
            )

            with pytest.raises(ValueError, match="not found"):
                await get_state_change_event(session, event_id, ACCOUNT_NAME)


class TestListStateChangeEvents:

    @pytest.mark.asyncio
    async def test_returns_events(self) -> None:
        session = AsyncMock()
        event_data = _make_event_data()

        mock_account = MagicMock()
        mock_account.id = ACCOUNT_ID

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=mock_account,
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.list_by_account.return_value = VisionStateChangeEventPage(
                items=[event_data],
                total=7,
            )
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                list_state_change_events,
            )

            result = await list_state_change_events(session, ACCOUNT_NAME)

            assert result.total == 7
            assert result.page == 1
            assert result.page_size == 100
            assert len(result.items) == 1

    @pytest.mark.asyncio
    async def test_account_not_found_raises(self) -> None:
        session = AsyncMock()

        with patch(
            f"{MODULE}.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from services.vision_event_service._implementation import (
                list_state_change_events,
            )

            with pytest.raises(ValueError, match="not found"):
                await list_state_change_events(session, "bad-account")

    @pytest.mark.asyncio
    async def test_passes_filters(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 12, 31, tzinfo=timezone.utc)

        mock_account = MagicMock()
        mock_account.id = ACCOUNT_ID

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=mock_account,
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.list_by_account.return_value = VisionStateChangeEventPage(
                items=[],
                total=0,
            )
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                list_state_change_events,
            )

            result = await list_state_change_events(
                session,
                ACCOUNT_NAME,
                project_id=project_id,
                entity_id=entity_id,
                start=start,
                end=end,
            )

            assert result.total == 0
            assert result.page == 1
            assert result.page_size == 100
            repo.list_by_account.assert_awaited_once_with(
                account_id=ACCOUNT_ID,
                project_id=project_id,
                entity_id=entity_id,
                start=start,
                end=end,
                page=1,
                limit=100,
            )

    @pytest.mark.asyncio
    async def test_passes_page_and_limit(self) -> None:
        session = AsyncMock()
        mock_account = MagicMock()
        mock_account.id = ACCOUNT_ID

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=mock_account,
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.list_by_account.return_value = VisionStateChangeEventPage(
                items=[],
                total=0,
            )
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                list_state_change_events,
            )

            result = await list_state_change_events(
                session,
                ACCOUNT_NAME,
                page=3,
                limit=25,
            )

            assert result.page == 3
            assert result.page_size == 25
            repo.list_by_account.assert_awaited_once_with(
                account_id=ACCOUNT_ID,
                project_id=None,
                entity_id=None,
                start=None,
                end=None,
                page=3,
                limit=25,
            )


class TestDeleteStateChangeEvent:

    @pytest.mark.asyncio
    async def test_deletes_event(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.delete_for_account.return_value = True
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                delete_state_change_event,
            )

            await delete_state_change_event(session, event_id, ACCOUNT_NAME)

            repo.delete_for_account.assert_awaited_once_with(event_id, ACCOUNT_ID)

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.delete_for_account.return_value = False
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                delete_state_change_event,
            )

            with pytest.raises(ValueError, match="not found"):
                await delete_state_change_event(session, event_id, ACCOUNT_NAME)


class TestCreateWithTestMetadata:

    @pytest.mark.asyncio
    async def test_is_test_merged_into_metadata(self) -> None:
        session = AsyncMock()
        request = CreateStateChangeEventRequest(
            entity_id=ENTITY_ID,
            new_state_id=NEW_STATE_ID,
            is_test=True,
            test_group="group-a",
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.verify_entity_belongs_to_account.return_value = True
            repo.create.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                create_state_change_event,
            )

            result = await create_state_change_event(session, request, ACCOUNT_NAME)

            assert result.is_test is True
            assert result.test_group == "group-a"
            assert result.event_metadata["is_test"] is True
            assert result.event_metadata["test_group"] == "group-a"

    @pytest.mark.asyncio
    async def test_is_test_none_not_merged(self) -> None:
        session = AsyncMock()
        request = CreateStateChangeEventRequest(
            entity_id=ENTITY_ID,
            new_state_id=NEW_STATE_ID,
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.verify_entity_belongs_to_account.return_value = True
            repo.create.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                create_state_change_event,
            )

            result = await create_state_change_event(session, request, ACCOUNT_NAME)

            assert result.is_test is None
            assert result.test_group is None
            assert "is_test" not in result.event_metadata


class TestUpdateStateChangeEvent:

    @pytest.mark.asyncio
    async def test_updates_metadata(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        original_data = _make_event_data(id=event_id, event_metadata={"foo": "bar"})
        updated_data = _make_event_data(
            id=event_id,
            event_metadata={"foo": "bar", "is_test": True, "test_group": "g1"},
        )

        from api.schemas.operations.vision_state_change_event import (
            UpdateStateChangeEventRequest,
        )

        request = UpdateStateChangeEventRequest(is_test=True, test_group="g1")

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.side_effect = [original_data, updated_data]
            repo.update_metadata.return_value = True
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                update_state_change_event,
            )

            result = await update_state_change_event(
                session, event_id, request, ACCOUNT_NAME
            )

            assert result.is_test is True
            assert result.test_group == "g1"
            repo.update_metadata.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_account_not_found_raises(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()

        from api.schemas.operations.vision_state_change_event import (
            UpdateStateChangeEventRequest,
        )

        request = UpdateStateChangeEventRequest(is_test=True)

        with patch(
            f"{MODULE}.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from services.vision_event_service._implementation import (
                update_state_change_event,
            )

            with pytest.raises(ValueError, match="not found"):
                await update_state_change_event(
                    session, event_id, request, ACCOUNT_NAME
                )

    @pytest.mark.asyncio
    async def test_event_not_found_raises(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()

        from api.schemas.operations.vision_state_change_event import (
            UpdateStateChangeEventRequest,
        )

        request = UpdateStateChangeEventRequest(is_test=True)

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                update_state_change_event,
            )

            with pytest.raises(ValueError, match="not found"):
                await update_state_change_event(
                    session, event_id, request, ACCOUNT_NAME
                )

    @pytest.mark.asyncio
    async def test_merges_event_metadata(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        original_data = _make_event_data(id=event_id, event_metadata={"existing": 1})
        updated_data = _make_event_data(
            id=event_id,
            event_metadata={"existing": 1, "new_key": "val", "is_test": True},
        )

        from api.schemas.operations.vision_state_change_event import (
            UpdateStateChangeEventRequest,
        )

        request = UpdateStateChangeEventRequest(
            is_test=True, event_metadata={"new_key": "val"}
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.side_effect = [original_data, updated_data]
            repo.update_metadata.return_value = True
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                update_state_change_event,
            )

            result = await update_state_change_event(
                session, event_id, request, ACCOUNT_NAME
            )

            assert result.is_test is True
            call_args = repo.update_metadata.call_args[0]
            merged = call_args[2]
            assert merged["existing"] == 1
            assert merged["new_key"] == "val"
            assert merged["is_test"] is True


class TestPresignFrameS3Key:

    @pytest.mark.asyncio
    async def test_returns_none_when_key_is_none(self) -> None:
        result = await _presign_frame_s3_key(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_presigned_url(self) -> None:
        with patch(
            f"{MODULE}.map_uri_to_s3_url",
            return_value="https://s3.amazonaws.com/bucket/key?X-Amz-Signature=abc",
        ):
            result = await _presign_frame_s3_key("vision/frames/test.jpg")
            assert result == "https://s3.amazonaws.com/bucket/key?X-Amz-Signature=abc"

    @pytest.mark.asyncio
    async def test_returns_none_when_map_returns_empty(self) -> None:
        with patch(f"{MODULE}.map_uri_to_s3_url", return_value=""):
            result = await _presign_frame_s3_key("vision/frames/test.jpg")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self) -> None:
        with patch(
            f"{MODULE}.map_uri_to_s3_url",
            side_effect=RuntimeError("S3 error"),
        ):
            result = await _presign_frame_s3_key("vision/frames/test.jpg")
            assert result is None
