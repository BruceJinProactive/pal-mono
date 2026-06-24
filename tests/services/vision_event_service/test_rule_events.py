"""Tests for vision_event_service rule event operations."""

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.pal_repository.data_classes.vision_rule_event import VisionRuleEventData
from db.pal_repository.data_classes.vision_state_change_event import (
    VisionStateChangeEventData,
)
from services.monitoring_service._video import CameraVideoSegment
from services.vision_event_service import RuleEventDurationLimitError
from services.vision_event_service.limits import (
    RULE_EVENT_VIDEO_LOOKUP_MAX_DURATION_MINUTES,
    RULE_EVENT_VIDEO_LOOKUP_MAX_SEGMENTS,
)

MODULE = "services.vision_event_service._rule_events"

ACCOUNT_NAME = "test-account"
ACCOUNT_ID = uuid.uuid4()
RULE_ID = uuid.uuid4()
ENTITY_ID = uuid.uuid4()


def _mock_account() -> Any:
    mock = MagicMock()
    mock.id = ACCOUNT_ID
    return mock


def _make_event_data(**overrides: object) -> VisionRuleEventData:
    data = VisionRuleEventData(
        id=uuid.uuid4(),
        rule_id=RULE_ID,
        entity_id=ENTITY_ID,
        state_change_event_id=uuid.uuid4(),
        severity="high",
        duration=Decimal("4.2500"),
        manually_adjusted=False,
        triggered_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        event_metadata={},
    )
    return replace(data, **overrides)


def _make_state_change_event_data(
    **overrides: object,
) -> VisionStateChangeEventData:
    data = VisionStateChangeEventData(
        id=uuid.uuid4(),
        entity_id=ENTITY_ID,
        new_state_id=uuid.uuid4(),
        observed_at=datetime(2026, 6, 23, 14, 22, 43, tzinfo=timezone.utc),
        event_metadata={},
        camera_config_id=None,
        previous_state_id=None,
        confidence=None,
        frame_s3_key=(
            "security/cameras/account/project/camera/"
            "images/2026-06-23/2026-06-23_14-22-43.jpg"
        ),
    )
    return replace(data, **overrides)


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


class TestGetRuleEvent:
    @pytest.mark.asyncio
    async def test_returns_event(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        event_data = _make_event_data(id=event_id)

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = event_data
            mock_repo_cls.return_value = repo

            from services.vision_event_service._rule_events import get_rule_event

            result = await get_rule_event(session, event_id, ACCOUNT_NAME)

            assert result.id == event_id
            assert result.rule_id == RULE_ID
            assert result.duration == Decimal("4.2500")
            assert result.manually_adjusted is False

    @pytest.mark.asyncio
    async def test_raises_when_account_not_found(self) -> None:
        session = AsyncMock()

        with patch(
            f"{MODULE}.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from services.vision_event_service._rule_events import get_rule_event

            with pytest.raises(ValueError, match="not found"):
                await get_rule_event(session, uuid.uuid4(), "bad-account")

    @pytest.mark.asyncio
    async def test_raises_when_event_not_found(self) -> None:
        session = AsyncMock()

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_event_service._rule_events import get_rule_event

            with pytest.raises(ValueError, match="not found"):
                await get_rule_event(session, uuid.uuid4(), ACCOUNT_NAME)


class TestLookupRuleEventVideos:
    @pytest.mark.asyncio
    async def test_presign_asset_uri_returns_none_for_empty_uri(self) -> None:
        from services.vision_event_service._rule_events import _presign_asset_uri

        assert await _presign_asset_uri(None) is None

    @pytest.mark.asyncio
    async def test_returns_presigned_videos(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        state_change_event_id = uuid.uuid4()
        rule_event = _make_event_data(
            id=event_id,
            state_change_event_id=state_change_event_id,
            duration=Decimal("17.1000"),
            triggered_at=datetime(2026, 6, 23, 14, 22, 43, tzinfo=timezone.utc),
        )
        state_change_event = _make_state_change_event_data(
            id=state_change_event_id,
            observed_at=datetime(2026, 6, 23, 15, 22, 43, tzinfo=timezone.utc),
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_rule_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_state_repo_cls,
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
                return_value=[_make_video_segment()],
            ) as mock_lookup,
        ):
            rule_repo = AsyncMock()
            rule_repo.get_by_id_for_account.return_value = rule_event
            mock_rule_repo_cls.return_value = rule_repo
            state_repo = AsyncMock()
            state_repo.get_by_id_for_account.return_value = state_change_event
            mock_state_repo_cls.return_value = state_repo

            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            result = await lookup_rule_event_videos(session, event_id, ACCOUNT_NAME)

            assert result.rule_event_id == event_id
            assert result.state_change_event_id == state_change_event_id
            assert result.video_count == 1
            assert result.videos[0].url == "https://example.com/video.mp4"
            rule_repo.get_by_id_for_account.assert_awaited_once_with(
                event_id,
                ACCOUNT_ID,
            )
            state_repo.get_by_id_for_account.assert_awaited_once_with(
                state_change_event_id,
                ACCOUNT_ID,
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
                0,
                tzinfo=timezone.utc,
            )
            assert lookup_kwargs["end_time"] == datetime(
                2026,
                6,
                23,
                14,
                23,
                0,
                tzinfo=timezone.utc,
            )
            assert lookup_kwargs["max_segments"] == RULE_EVENT_VIDEO_LOOKUP_MAX_SEGMENTS

    @pytest.mark.asyncio
    async def test_raises_before_s3_lookup_when_duration_exceeds_limit(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        state_change_event_id = uuid.uuid4()
        rule_event = _make_event_data(
            id=event_id,
            state_change_event_id=state_change_event_id,
            duration=RULE_EVENT_VIDEO_LOOKUP_MAX_DURATION_MINUTES + Decimal("1.0"),
        )
        state_change_event = _make_state_change_event_data(id=state_change_event_id)

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_rule_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_state_repo_cls,
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
            ) as mock_lookup,
        ):
            rule_repo = AsyncMock()
            rule_repo.get_by_id_for_account.return_value = rule_event
            mock_rule_repo_cls.return_value = rule_repo
            state_repo = AsyncMock()
            state_repo.get_by_id_for_account.return_value = state_change_event
            mock_state_repo_cls.return_value = state_repo

            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            with pytest.raises(RuleEventDurationLimitError, match="at most"):
                await lookup_rule_event_videos(session, event_id, ACCOUNT_NAME)

            mock_lookup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_treats_naive_triggered_at_as_utc(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        state_change_event_id = uuid.uuid4()
        rule_event = _make_event_data(
            id=event_id,
            state_change_event_id=state_change_event_id,
            duration=Decimal("1.0000"),
            triggered_at=datetime(2026, 6, 23, 14, 22, 43),
        )
        state_change_event = _make_state_change_event_data(id=state_change_event_id)

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_rule_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_state_repo_cls,
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_lookup,
        ):
            rule_repo = AsyncMock()
            rule_repo.get_by_id_for_account.return_value = rule_event
            mock_rule_repo_cls.return_value = rule_repo
            state_repo = AsyncMock()
            state_repo.get_by_id_for_account.return_value = state_change_event
            mock_state_repo_cls.return_value = state_repo

            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            await lookup_rule_event_videos(session, event_id, ACCOUNT_NAME)

            lookup_args = mock_lookup.await_args
            assert lookup_args is not None
            assert lookup_args.kwargs["start_time"] == datetime(
                2026,
                6,
                23,
                14,
                21,
                0,
                tzinfo=timezone.utc,
            )
            assert lookup_args.kwargs["end_time"] == datetime(
                2026,
                6,
                23,
                14,
                23,
                0,
                tzinfo=timezone.utc,
            )

    @pytest.mark.asyncio
    async def test_keeps_exact_minute_window_bounds(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        state_change_event_id = uuid.uuid4()
        rule_event = _make_event_data(
            id=event_id,
            state_change_event_id=state_change_event_id,
            duration=Decimal("1.0000"),
            triggered_at=datetime(2026, 6, 23, 14, 22, tzinfo=timezone.utc),
        )
        state_change_event = _make_state_change_event_data(id=state_change_event_id)

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_rule_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_state_repo_cls,
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_lookup,
        ):
            rule_repo = AsyncMock()
            rule_repo.get_by_id_for_account.return_value = rule_event
            mock_rule_repo_cls.return_value = rule_repo
            state_repo = AsyncMock()
            state_repo.get_by_id_for_account.return_value = state_change_event
            mock_state_repo_cls.return_value = state_repo

            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            await lookup_rule_event_videos(session, event_id, ACCOUNT_NAME)

            lookup_args = mock_lookup.await_args
            assert lookup_args is not None
            assert lookup_args.kwargs["start_time"] == datetime(
                2026,
                6,
                23,
                14,
                21,
                tzinfo=timezone.utc,
            )
            assert lookup_args.kwargs["end_time"] == datetime(
                2026,
                6,
                23,
                14,
                22,
                tzinfo=timezone.utc,
            )

    @pytest.mark.asyncio
    async def test_returns_direct_video_from_video_frame_key(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        state_change_event_id = uuid.uuid4()
        rule_event = _make_event_data(
            id=event_id,
            state_change_event_id=state_change_event_id,
            duration=Decimal("0.0"),
        )
        video_key = (
            "security/cameras/account/project/camera/videos/"
            "2026-06-23/2026-06-23_14-05-03.mkv"
        )
        state_change_event = _make_state_change_event_data(
            id=state_change_event_id,
            frame_s3_key=video_key,
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_rule_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_state_repo_cls,
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
            ) as mock_lookup,
            patch(
                f"{MODULE}.map_uri_to_s3_url", return_value="https://example.com/a.mkv"
            ),
        ):
            rule_repo = AsyncMock()
            rule_repo.get_by_id_for_account.return_value = rule_event
            mock_rule_repo_cls.return_value = rule_repo
            state_repo = AsyncMock()
            state_repo.get_by_id_for_account.return_value = state_change_event
            mock_state_repo_cls.return_value = state_repo

            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            result = await lookup_rule_event_videos(session, event_id, ACCOUNT_NAME)

            assert result.video_count == 1
            assert result.videos[0].s3_key == video_key
            assert result.videos[0].url == "https://example.com/a.mkv"
            assert result.videos[0].segment_start_time == datetime(
                2026,
                6,
                23,
                14,
                5,
                3,
                tzinfo=timezone.utc,
            )
            mock_lookup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_keeps_http_direct_video_url(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        state_change_event_id = uuid.uuid4()
        rule_event = _make_event_data(
            id=event_id,
            state_change_event_id=state_change_event_id,
            duration=Decimal("0.0"),
        )
        video_url = (
            "https://example.com/security/cameras/account/project/camera/videos/"
            "2026-06-23/2026-06-23_14-05-03.mp4"
        )
        state_change_event = _make_state_change_event_data(
            id=state_change_event_id,
            frame_s3_key=video_url,
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_rule_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_state_repo_cls,
        ):
            rule_repo = AsyncMock()
            rule_repo.get_by_id_for_account.return_value = rule_event
            mock_rule_repo_cls.return_value = rule_repo
            state_repo = AsyncMock()
            state_repo.get_by_id_for_account.return_value = state_change_event
            mock_state_repo_cls.return_value = state_repo

            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            result = await lookup_rule_event_videos(session, event_id, ACCOUNT_NAME)

            assert result.video_count == 1
            assert result.videos[0].s3_key == video_url
            assert result.videos[0].url == video_url

    @pytest.mark.asyncio
    async def test_returns_empty_when_frame_key_is_missing(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        state_change_event_id = uuid.uuid4()
        rule_event = _make_event_data(
            id=event_id,
            state_change_event_id=state_change_event_id,
        )
        state_change_event = _make_state_change_event_data(
            id=state_change_event_id,
            frame_s3_key=None,
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_rule_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_state_repo_cls,
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
            ) as mock_lookup,
        ):
            rule_repo = AsyncMock()
            rule_repo.get_by_id_for_account.return_value = rule_event
            mock_rule_repo_cls.return_value = rule_repo
            state_repo = AsyncMock()
            state_repo.get_by_id_for_account.return_value = state_change_event
            mock_state_repo_cls.return_value = state_repo

            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            result = await lookup_rule_event_videos(session, event_id, ACCOUNT_NAME)

            assert result.video_count == 0
            assert result.videos == []
            mock_lookup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_empty_when_frame_key_has_no_video_prefix(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        state_change_event_id = uuid.uuid4()
        rule_event = _make_event_data(
            id=event_id,
            state_change_event_id=state_change_event_id,
        )
        state_change_event = _make_state_change_event_data(
            id=state_change_event_id,
            frame_s3_key="security/cameras/account/project/camera/frame.jpg",
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_rule_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_state_repo_cls,
        ):
            rule_repo = AsyncMock()
            rule_repo.get_by_id_for_account.return_value = rule_event
            mock_rule_repo_cls.return_value = rule_repo
            state_repo = AsyncMock()
            state_repo.get_by_id_for_account.return_value = state_change_event
            mock_state_repo_cls.return_value = state_repo

            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            result = await lookup_rule_event_videos(session, event_id, ACCOUNT_NAME)

            assert result.video_count == 0
            assert result.videos == []

    @pytest.mark.asyncio
    async def test_ignores_non_video_key_in_videos_prefix(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        state_change_event_id = uuid.uuid4()
        rule_event = _make_event_data(
            id=event_id,
            state_change_event_id=state_change_event_id,
            duration=Decimal("0.0"),
        )
        state_change_event = _make_state_change_event_data(
            id=state_change_event_id,
            frame_s3_key=(
                "security/cameras/account/project/camera/videos/"
                "2026-06-23/2026-06-23_14-05-03.jpg"
            ),
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_rule_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_state_repo_cls,
        ):
            rule_repo = AsyncMock()
            rule_repo.get_by_id_for_account.return_value = rule_event
            mock_rule_repo_cls.return_value = rule_repo
            state_repo = AsyncMock()
            state_repo.get_by_id_for_account.return_value = state_change_event
            mock_state_repo_cls.return_value = state_repo

            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            result = await lookup_rule_event_videos(session, event_id, ACCOUNT_NAME)

            assert result.video_count == 0
            assert result.videos == []

    @pytest.mark.asyncio
    async def test_ignores_direct_video_with_unparseable_timestamp(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        state_change_event_id = uuid.uuid4()
        rule_event = _make_event_data(
            id=event_id,
            state_change_event_id=state_change_event_id,
            duration=Decimal("0.0"),
        )
        state_change_event = _make_state_change_event_data(
            id=state_change_event_id,
            frame_s3_key=(
                "security/cameras/account/project/camera/videos/"
                "2026-06-23/not-a-timestamp.mp4"
            ),
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_rule_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_state_repo_cls,
        ):
            rule_repo = AsyncMock()
            rule_repo.get_by_id_for_account.return_value = rule_event
            mock_rule_repo_cls.return_value = rule_repo
            state_repo = AsyncMock()
            state_repo.get_by_id_for_account.return_value = state_change_event
            mock_state_repo_cls.return_value = state_repo

            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            result = await lookup_rule_event_videos(session, event_id, ACCOUNT_NAME)

            assert result.video_count == 0
            assert result.videos == []

    @pytest.mark.asyncio
    async def test_ignores_direct_video_when_presign_fails(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        state_change_event_id = uuid.uuid4()
        rule_event = _make_event_data(
            id=event_id,
            state_change_event_id=state_change_event_id,
            duration=Decimal("0.0"),
        )
        state_change_event = _make_state_change_event_data(
            id=state_change_event_id,
            frame_s3_key=(
                "security/cameras/account/project/camera/videos/"
                "2026-06-23/2026-06-23_14-05-03.mp4"
            ),
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_rule_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_state_repo_cls,
            patch(f"{MODULE}.map_uri_to_s3_url", side_effect=RuntimeError("boom")),
        ):
            rule_repo = AsyncMock()
            rule_repo.get_by_id_for_account.return_value = rule_event
            mock_rule_repo_cls.return_value = rule_repo
            state_repo = AsyncMock()
            state_repo.get_by_id_for_account.return_value = state_change_event
            mock_state_repo_cls.return_value = state_repo

            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            result = await lookup_rule_event_videos(session, event_id, ACCOUNT_NAME)

            assert result.video_count == 0
            assert result.videos == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_duration_is_zero(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        state_change_event_id = uuid.uuid4()
        rule_event = _make_event_data(
            id=event_id,
            state_change_event_id=state_change_event_id,
            duration=Decimal("0.0"),
        )
        state_change_event = _make_state_change_event_data(id=state_change_event_id)

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_rule_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_state_repo_cls,
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
            ) as mock_lookup,
        ):
            rule_repo = AsyncMock()
            rule_repo.get_by_id_for_account.return_value = rule_event
            mock_rule_repo_cls.return_value = rule_repo
            state_repo = AsyncMock()
            state_repo.get_by_id_for_account.return_value = state_change_event
            mock_state_repo_cls.return_value = state_repo

            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            result = await lookup_rule_event_videos(session, event_id, ACCOUNT_NAME)

            assert result.video_count == 0
            assert result.videos == []
            mock_lookup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_before_s3_lookup_when_duration_is_negative(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        state_change_event_id = uuid.uuid4()
        rule_event = _make_event_data(
            id=event_id,
            state_change_event_id=state_change_event_id,
            duration=Decimal("-1.0"),
        )
        state_change_event = _make_state_change_event_data(id=state_change_event_id)

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_rule_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_state_repo_cls,
            patch(
                f"{MODULE}.lookup_camera_video_segments",
                new_callable=AsyncMock,
            ) as mock_lookup,
        ):
            rule_repo = AsyncMock()
            rule_repo.get_by_id_for_account.return_value = rule_event
            mock_rule_repo_cls.return_value = rule_repo
            state_repo = AsyncMock()
            state_repo.get_by_id_for_account.return_value = state_change_event
            mock_state_repo_cls.return_value = state_repo

            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            with pytest.raises(RuleEventDurationLimitError, match="non-negative"):
                await lookup_rule_event_videos(session, event_id, ACCOUNT_NAME)

            mock_lookup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_when_account_not_found(self) -> None:
        session = AsyncMock()

        with patch(
            f"{MODULE}.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            with pytest.raises(ValueError, match="Account .* not found"):
                await lookup_rule_event_videos(session, uuid.uuid4(), ACCOUNT_NAME)

    @pytest.mark.asyncio
    async def test_raises_when_rule_event_not_found(self) -> None:
        session = AsyncMock()

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_rule_repo_cls,
        ):
            rule_repo = AsyncMock()
            rule_repo.get_by_id_for_account.return_value = None
            mock_rule_repo_cls.return_value = rule_repo

            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            with pytest.raises(ValueError, match="Rule event .* not found"):
                await lookup_rule_event_videos(session, uuid.uuid4(), ACCOUNT_NAME)

    @pytest.mark.asyncio
    async def test_raises_when_state_change_event_not_found(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        rule_event = _make_event_data(id=event_id)

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_rule_repo_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_state_repo_cls,
        ):
            rule_repo = AsyncMock()
            rule_repo.get_by_id_for_account.return_value = rule_event
            mock_rule_repo_cls.return_value = rule_repo
            state_repo = AsyncMock()
            state_repo.get_by_id_for_account.return_value = None
            mock_state_repo_cls.return_value = state_repo

            from services.vision_event_service._rule_events import (
                lookup_rule_event_videos,
            )

            with pytest.raises(ValueError, match="State change event .* not found"):
                await lookup_rule_event_videos(session, event_id, ACCOUNT_NAME)


class TestListRuleEvents:
    @pytest.mark.asyncio
    async def test_returns_events(self) -> None:
        session = AsyncMock()
        event_data = _make_event_data()

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.list_by_account.return_value = [event_data]
            mock_repo_cls.return_value = repo

            from services.vision_event_service._rule_events import list_rule_events

            result = await list_rule_events(session, ACCOUNT_NAME)

            assert len(result) == 1
            assert result[0].rule_id == RULE_ID
            assert result[0].duration == Decimal("4.2500")
            repo.list_by_account.assert_awaited_once_with(
                account_id=ACCOUNT_ID,
                rule_id=None,
                entity_id=None,
                start=None,
                end=None,
                manually_adjusted=None,
            )

    @pytest.mark.asyncio
    async def test_passes_manual_adjustment_filter(self) -> None:
        session = AsyncMock()
        event_data = _make_event_data(manually_adjusted=True)

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.list_by_account.return_value = [event_data]
            mock_repo_cls.return_value = repo

            from services.vision_event_service._rule_events import list_rule_events

            result = await list_rule_events(
                session,
                ACCOUNT_NAME,
                manually_adjusted=True,
            )

            assert len(result) == 1
            assert result[0].manually_adjusted is True
            repo.list_by_account.assert_awaited_once_with(
                account_id=ACCOUNT_ID,
                rule_id=None,
                entity_id=None,
                start=None,
                end=None,
                manually_adjusted=True,
            )

    @pytest.mark.asyncio
    async def test_raises_when_account_not_found(self) -> None:
        session = AsyncMock()

        with patch(
            f"{MODULE}.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from services.vision_event_service._rule_events import list_rule_events

            with pytest.raises(ValueError, match="not found"):
                await list_rule_events(session, "bad-account")


class TestDeleteRuleEvent:
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
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.delete_for_account.return_value = True
            mock_repo_cls.return_value = repo

            from services.vision_event_service._rule_events import delete_rule_event

            await delete_rule_event(session, event_id, ACCOUNT_NAME)
            repo.delete_for_account.assert_awaited_once_with(event_id, ACCOUNT_ID)

    @pytest.mark.asyncio
    async def test_raises_when_account_not_found(self) -> None:
        session = AsyncMock()

        with patch(
            f"{MODULE}.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from services.vision_event_service._rule_events import delete_rule_event

            with pytest.raises(ValueError, match="not found"):
                await delete_rule_event(session, uuid.uuid4(), "bad-account")

    @pytest.mark.asyncio
    async def test_raises_when_event_not_found(self) -> None:
        session = AsyncMock()

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.delete_for_account.return_value = False
            mock_repo_cls.return_value = repo

            from services.vision_event_service._rule_events import delete_rule_event

            with pytest.raises(ValueError, match="not found"):
                await delete_rule_event(session, uuid.uuid4(), ACCOUNT_NAME)


class TestUpdateRuleEvent:
    @pytest.mark.asyncio
    async def test_updates_event(self) -> None:
        session = AsyncMock()
        event_id = uuid.uuid4()
        triggered_at = datetime(2026, 5, 1, 12, 30, tzinfo=timezone.utc)
        duration = Decimal("2.5000")
        event_data = _make_event_data(
            id=event_id,
            triggered_at=triggered_at,
            duration=duration,
            manually_adjusted=True,
        )

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.update_for_account.return_value = event_data
            mock_repo_cls.return_value = repo

            from services.vision_event_service._rule_events import update_rule_event

            result = await update_rule_event(
                session=session,
                event_id=event_id,
                triggered_at=triggered_at,
                duration=duration,
                manually_adjusted=True,
                account_name=ACCOUNT_NAME,
            )

            assert result.id == event_id
            assert result.triggered_at == triggered_at
            assert result.duration == Decimal("2.5000")
            assert result.manually_adjusted is True
            repo.update_for_account.assert_awaited_once_with(
                event_id=event_id,
                account_id=ACCOUNT_ID,
                triggered_at=triggered_at,
                duration=Decimal("2.5000"),
                manually_adjusted=True,
            )

    @pytest.mark.asyncio
    async def test_raises_when_account_not_found(self) -> None:
        session = AsyncMock()
        triggered_at = datetime(2026, 5, 1, tzinfo=timezone.utc)

        with patch(
            f"{MODULE}.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from services.vision_event_service._rule_events import update_rule_event

            with pytest.raises(ValueError, match="not found"):
                await update_rule_event(
                    session,
                    uuid.uuid4(),
                    triggered_at,
                    Decimal("1.0000"),
                    True,
                    "bad-account",
                )

    @pytest.mark.asyncio
    async def test_raises_when_duration_exceeds_limit(self) -> None:
        session = AsyncMock()

        from services.vision_event_service._rule_events import update_rule_event

        with pytest.raises(RuleEventDurationLimitError, match="at most"):
            await update_rule_event(
                session,
                uuid.uuid4(),
                datetime(2026, 5, 1, tzinfo=timezone.utc),
                RULE_EVENT_VIDEO_LOOKUP_MAX_DURATION_MINUTES + Decimal("1.0"),
                True,
                ACCOUNT_NAME,
            )

    @pytest.mark.asyncio
    async def test_raises_when_event_not_found(self) -> None:
        session = AsyncMock()
        triggered_at = datetime(2026, 5, 1, tzinfo=timezone.utc)

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionRuleEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.update_for_account.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_event_service._rule_events import update_rule_event

            with pytest.raises(ValueError, match="not found"):
                await update_rule_event(
                    session,
                    uuid.uuid4(),
                    triggered_at,
                    Decimal("1.0000"),
                    True,
                    ACCOUNT_NAME,
                )
