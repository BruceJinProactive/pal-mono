"""Tests for api.routes.operation._vision_rule_events API handlers."""

import dataclasses
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.schemas.operations.vision_rule_event import (
    UpdateVisionRuleEventRequest,
    VisionRuleEventVideo,
    VisionRuleEventVideoLookupResponse,
)
from db.pal_repository.data_classes.vision_rule_event import VisionRuleEventData
from services.auth_types import UserContext, UserRole
from services.vision_event_service import (
    RuleEventDurationLimitError,
    RuleEventVideoData,
    RuleEventVideoLookupData,
)
from services.vision_event_service.limits import (
    RULE_EVENT_VIDEO_LOOKUP_MAX_DURATION_MINUTES,
)

MODULE = "api.routes.operation._vision_rule_events"

ACCOUNT_NAME = "test-account"
RULE_ID = uuid.uuid4()
ENTITY_ID = uuid.uuid4()


def _make_event_data(**overrides: object) -> VisionRuleEventData:
    data = VisionRuleEventData(
        id=uuid.uuid4(),
        rule_id=RULE_ID,
        entity_id=ENTITY_ID,
        state_change_event_id=uuid.uuid4(),
        severity="high",
        duration=Decimal("3.7500"),
        manually_adjusted=False,
        triggered_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        event_metadata={},
    )
    return dataclasses.replace(data, **overrides)


def _make_video_lookup_data(
    rule_event_id: uuid.UUID | None = None,
    state_change_event_id: uuid.UUID | None = None,
    videos: list[RuleEventVideoData] | None = None,
) -> RuleEventVideoLookupData:
    video = RuleEventVideoData(
        s3_key=(
            "security/cameras/account/project/camera/videos/"
            "2026-06-23/2026-06-23_14-05-03.mp4"
        ),
        url="https://example.com/video.mp4",
        segment_start_time=datetime(2026, 6, 23, 14, 5, 3, tzinfo=timezone.utc),
        segment_end_time=datetime(2026, 6, 23, 14, 6, 3, tzinfo=timezone.utc),
    )
    response_videos = [video] if videos is None else videos
    return RuleEventVideoLookupData(
        rule_event_id=rule_event_id or uuid.uuid4(),
        state_change_event_id=state_change_event_id or uuid.uuid4(),
        videos=response_videos,
    )


def _make_video_lookup_response(
    rule_event_id: uuid.UUID | None = None,
    state_change_event_id: uuid.UUID | None = None,
    videos: list[VisionRuleEventVideo] | None = None,
    video_count: int | None = None,
) -> VisionRuleEventVideoLookupResponse:
    video = VisionRuleEventVideo(
        s3_key=(
            "security/cameras/account/project/camera/videos/"
            "2026-06-23/2026-06-23_14-05-03.mp4"
        ),
        url="https://example.com/video.mp4",
        segment_start_time=datetime(2026, 6, 23, 14, 5, 3, tzinfo=timezone.utc),
        segment_end_time=datetime(2026, 6, 23, 14, 6, 3, tzinfo=timezone.utc),
    )
    response_videos = [video] if videos is None else videos
    return VisionRuleEventVideoLookupResponse(
        rule_event_id=rule_event_id or uuid.uuid4(),
        state_change_event_id=state_change_event_id or uuid.uuid4(),
        videos=response_videos,
        video_count=len(response_videos) if video_count is None else video_count,
    )


class TestGetRuleEvent:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_rule_events import get_rule_event

        session = AsyncMock()
        event_id = uuid.uuid4()
        expected = _make_event_data(id=event_id)

        with patch(
            f"{MODULE}.vision_event_service.get_rule_event",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await get_rule_event(session, event_id, ACCOUNT_NAME)

        assert result.id == event_id
        assert result.duration == Decimal("3.7500")

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_rule_events import get_rule_event

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_event_service.get_rule_event",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_rule_event(session, uuid.uuid4(), ACCOUNT_NAME)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_rule_events import get_rule_event

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_event_service.get_rule_event",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_rule_event(session, uuid.uuid4(), ACCOUNT_NAME)
            assert exc_info.value.status_code == 500


class TestLookupRuleEventVideos:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_rule_events import lookup_rule_event_videos

        session = AsyncMock()
        event_id = uuid.uuid4()
        expected = _make_video_lookup_data(rule_event_id=event_id)

        with patch(
            f"{MODULE}.vision_event_service.lookup_rule_event_videos",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_lookup:
            result = await lookup_rule_event_videos(session, event_id, ACCOUNT_NAME)

        assert result.rule_event_id == event_id
        assert result.video_count == 1
        mock_lookup.assert_awaited_once_with(
            session=session,
            event_id=event_id,
            account_name=ACCOUNT_NAME,
        )

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_rule_events import lookup_rule_event_videos

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_event_service.lookup_rule_event_videos",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await lookup_rule_event_videos(session, uuid.uuid4(), ACCOUNT_NAME)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_duration_limit_returns_400(self) -> None:
        from api.routes.operation._vision_rule_events import lookup_rule_event_videos

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_event_service.lookup_rule_event_videos",
            new_callable=AsyncMock,
            side_effect=RuleEventDurationLimitError("duration too large"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await lookup_rule_event_videos(session, uuid.uuid4(), ACCOUNT_NAME)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_rule_events import lookup_rule_event_videos

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_event_service.lookup_rule_event_videos",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await lookup_rule_event_videos(session, uuid.uuid4(), ACCOUNT_NAME)
            assert exc_info.value.status_code == 500


class TestOperationRouteLookupRuleEventVideos:
    @pytest.mark.asyncio
    async def test_forwards_to_rule_event_handler(self) -> None:
        from api.routes import operation

        session = AsyncMock()
        event_id = uuid.uuid4()
        context = UserContext(
            username=str(uuid.uuid4()),
            email="operator@example.com",
            groups=[],
            display_name="Operator",
            role=UserRole.AccountManager,
        )
        expected = _make_video_lookup_response(rule_event_id=event_id)

        with patch(
            "api.routes.operation._vision_rule_events.lookup_rule_event_videos",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_lookup:
            result = await operation.lookup_rule_event_videos(
                account_name=ACCOUNT_NAME,
                event_id=event_id,
                context=context,
                session=session,
            )

        assert result.rule_event_id == event_id
        mock_lookup.assert_awaited_once_with(
            session=session,
            event_id=event_id,
            account_name=ACCOUNT_NAME,
        )


class TestListRuleEvents:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_rule_events import list_rule_events

        session = AsyncMock()
        expected: list[VisionRuleEventData] = []

        with patch(
            f"{MODULE}.vision_event_service.list_rule_events",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_list:
            result = await list_rule_events(session, ACCOUNT_NAME)

        assert result.total == 0
        mock_list.assert_awaited_once_with(
            session=session,
            account_name=ACCOUNT_NAME,
            rule_id=None,
            entity_id=None,
            start=None,
            end=None,
            manually_adjusted=None,
        )

    @pytest.mark.asyncio
    async def test_passes_manual_adjustment_filter(self) -> None:
        from api.routes.operation._vision_rule_events import list_rule_events

        session = AsyncMock()
        expected: list[VisionRuleEventData] = []

        with patch(
            f"{MODULE}.vision_event_service.list_rule_events",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_list:
            result = await list_rule_events(
                session=session,
                account_name=ACCOUNT_NAME,
                manually_adjusted=True,
            )

        assert result.total == 0
        mock_list.assert_awaited_once_with(
            session=session,
            account_name=ACCOUNT_NAME,
            rule_id=None,
            entity_id=None,
            start=None,
            end=None,
            manually_adjusted=True,
        )

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_rule_events import list_rule_events

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_event_service.list_rule_events",
            new_callable=AsyncMock,
            side_effect=ValueError("Account not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_rule_events(session, "bad-account")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_rule_events import list_rule_events

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_event_service.list_rule_events",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_rule_events(session, ACCOUNT_NAME)
            assert exc_info.value.status_code == 500


class TestDeleteRuleEvent:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_rule_events import delete_rule_event

        session = AsyncMock()
        event_id = uuid.uuid4()

        with patch(
            f"{MODULE}.vision_event_service.delete_rule_event",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await delete_rule_event(session, event_id, ACCOUNT_NAME)

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_rule_events import delete_rule_event

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_event_service.delete_rule_event",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_rule_event(session, uuid.uuid4(), ACCOUNT_NAME)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_rule_events import delete_rule_event

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_event_service.delete_rule_event",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_rule_event(session, uuid.uuid4(), ACCOUNT_NAME)
            assert exc_info.value.status_code == 500


class TestUpdateRuleEvent:
    def test_request_rejects_duration_over_limit(self) -> None:
        with pytest.raises(ValidationError):
            UpdateVisionRuleEventRequest(
                triggered_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                duration=RULE_EVENT_VIDEO_LOOKUP_MAX_DURATION_MINUTES + Decimal("1.0"),
            )

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_rule_events import update_rule_event

        session = AsyncMock()
        event_id = uuid.uuid4()
        request = UpdateVisionRuleEventRequest(
            triggered_at=datetime(2026, 5, 1, 12, 30, tzinfo=timezone.utc),
            duration=Decimal("2.5000"),
        )
        expected = _make_event_data(
            id=event_id,
            triggered_at=request.triggered_at,
            duration=request.duration,
        )

        with patch(
            f"{MODULE}.vision_event_service.update_rule_event",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_update:
            result = await update_rule_event(
                session=session,
                event_id=event_id,
                account_name=ACCOUNT_NAME,
                request=request,
            )

        assert result.id == event_id
        assert result.duration == Decimal("2.5000")
        mock_update.assert_awaited_once_with(
            session=session,
            event_id=event_id,
            triggered_at=request.triggered_at,
            duration=request.duration,
            manually_adjusted=request.manually_adjusted,
            account_name=ACCOUNT_NAME,
        )

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_rule_events import update_rule_event

        session = AsyncMock()
        request = UpdateVisionRuleEventRequest(
            triggered_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            duration=Decimal("1.0000"),
        )

        with patch(
            f"{MODULE}.vision_event_service.update_rule_event",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_rule_event(
                    session=session,
                    event_id=uuid.uuid4(),
                    account_name=ACCOUNT_NAME,
                    request=request,
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_duration_limit_returns_400(self) -> None:
        from api.routes.operation._vision_rule_events import update_rule_event

        session = AsyncMock()
        request = UpdateVisionRuleEventRequest(
            triggered_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            duration=RULE_EVENT_VIDEO_LOOKUP_MAX_DURATION_MINUTES,
        )

        with patch(
            f"{MODULE}.vision_event_service.update_rule_event",
            new_callable=AsyncMock,
            side_effect=RuleEventDurationLimitError("duration too large"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_rule_event(
                    session=session,
                    event_id=uuid.uuid4(),
                    account_name=ACCOUNT_NAME,
                    request=request,
                )
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_rule_events import update_rule_event

        session = AsyncMock()
        request = UpdateVisionRuleEventRequest(
            triggered_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            duration=Decimal("1.0000"),
        )

        with patch(
            f"{MODULE}.vision_event_service.update_rule_event",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_rule_event(
                    session=session,
                    event_id=uuid.uuid4(),
                    account_name=ACCOUNT_NAME,
                    request=request,
                )
            assert exc_info.value.status_code == 500
