"""Tests for api.routes.operation._vision_state_change_events API handlers."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.schemas.operations.vision_state_change_event import (
    CreateStateChangeEventRequest,
    ListStateChangeEventsResponse,
    StateChangeEventResponse,
    StateChangeEventVideo,
    UpdateStateChangeEventRequest,
)

MODULE = "api.routes.operation._vision_state_change_events"

ACCOUNT_NAME = "test-account"
ENTITY_ID = uuid.uuid4()
NEW_STATE_ID = uuid.uuid4()


def _make_response(**overrides: object) -> StateChangeEventResponse:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "entity_id": ENTITY_ID,
        "new_state_id": NEW_STATE_ID,
        "observed_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "camera_config_id": None,
        "previous_state_id": None,
        "confidence": None,
        "frame_s3_key": None,
        "event_metadata": {},
    }
    defaults.update(overrides)
    return StateChangeEventResponse(**defaults)  # type: ignore[arg-type]


class TestCreateStateChangeEvent:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            create_state_change_event,
        )

        session = AsyncMock()
        request = CreateStateChangeEventRequest(
            entity_id=ENTITY_ID, new_state_id=NEW_STATE_ID
        )
        expected = _make_response()

        with patch(
            f"{MODULE}.vision_event_service.create_state_change_event",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await create_state_change_event(session, request, ACCOUNT_NAME)

        assert result.entity_id == ENTITY_ID

    @pytest.mark.asyncio
    async def test_value_error_returns_400(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            create_state_change_event,
        )

        session = AsyncMock()
        request = CreateStateChangeEventRequest(
            entity_id=ENTITY_ID, new_state_id=NEW_STATE_ID
        )

        with patch(
            f"{MODULE}.vision_event_service.create_state_change_event",
            new_callable=AsyncMock,
            side_effect=ValueError("invalid entity"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_state_change_event(session, request, ACCOUNT_NAME)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            create_state_change_event,
        )

        session = AsyncMock()
        request = CreateStateChangeEventRequest(
            entity_id=ENTITY_ID, new_state_id=NEW_STATE_ID
        )

        with patch(
            f"{MODULE}.vision_event_service.create_state_change_event",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_state_change_event(session, request, ACCOUNT_NAME)
            assert exc_info.value.status_code == 500


class TestGetStateChangeEvent:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            get_state_change_event,
        )

        session = AsyncMock()
        event_id = uuid.uuid4()
        expected = _make_response(id=event_id)

        with patch(
            f"{MODULE}.vision_event_service.get_state_change_event",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_get:
            result = await get_state_change_event(session, event_id, ACCOUNT_NAME)

        assert result.id == event_id
        mock_get.assert_awaited_once_with(
            session=session,
            event_id=event_id,
            account_name=ACCOUNT_NAME,
            include_video=False,
        )

    @pytest.mark.asyncio
    async def test_passes_include_video(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            get_state_change_event,
        )

        session = AsyncMock()
        event_id = uuid.uuid4()
        video = StateChangeEventVideo(
            s3_key=(
                "security/cameras/account/project/camera/videos/"
                "2026-06-23/2026-06-23_14-05-03.mp4"
            ),
            url="https://example.com/v.mp4",
            segment_start_time=datetime(2026, 6, 23, 14, 5, 3, tzinfo=timezone.utc),
            segment_end_time=datetime(2026, 6, 23, 14, 6, 3, tzinfo=timezone.utc),
        )
        expected = _make_response(id=event_id, videos=[video], video_count=1)

        with patch(
            f"{MODULE}.vision_event_service.get_state_change_event",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_get:
            result = await get_state_change_event(
                session,
                event_id,
                ACCOUNT_NAME,
                include_video=True,
            )

        assert result.video_count == 1
        assert result.videos[0].url == "https://example.com/v.mp4"
        mock_get.assert_awaited_once_with(
            session=session,
            event_id=event_id,
            account_name=ACCOUNT_NAME,
            include_video=True,
        )

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            get_state_change_event,
        )

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_event_service.get_state_change_event",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_state_change_event(session, uuid.uuid4(), ACCOUNT_NAME)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            get_state_change_event,
        )

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_event_service.get_state_change_event",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_state_change_event(session, uuid.uuid4(), ACCOUNT_NAME)
            assert exc_info.value.status_code == 500


class TestListStateChangeEvents:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            list_state_change_events,
        )

        session = AsyncMock()
        expected = ListStateChangeEventsResponse(
            items=[],
            total=0,
            page=1,
            page_size=100,
        )

        with patch(
            f"{MODULE}.vision_event_service.list_state_change_events",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_list:
            result = await list_state_change_events(session, "test-account")

        assert result.total == 0
        mock_list.assert_awaited_once_with(
            session=session,
            account_name="test-account",
            project_id=None,
            entity_id=None,
            start=None,
            end=None,
            page=1,
            limit=100,
        )

    @pytest.mark.asyncio
    async def test_passes_page_and_limit(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            list_state_change_events,
        )

        session = AsyncMock()
        expected = ListStateChangeEventsResponse(
            items=[],
            total=0,
            page=3,
            page_size=25,
        )

        with patch(
            f"{MODULE}.vision_event_service.list_state_change_events",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_list:
            await list_state_change_events(
                session,
                "test-account",
                page=3,
                limit=25,
            )

        assert mock_list.await_args is not None
        assert mock_list.await_args.kwargs["page"] == 3
        assert mock_list.await_args.kwargs["limit"] == 25

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            list_state_change_events,
        )

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_event_service.list_state_change_events",
            new_callable=AsyncMock,
            side_effect=ValueError("Account not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_state_change_events(session, "bad-account")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            list_state_change_events,
        )

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_event_service.list_state_change_events",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_state_change_events(session, "test-account")
            assert exc_info.value.status_code == 500


class TestDeleteStateChangeEvent:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            delete_state_change_event,
        )

        session = AsyncMock()
        event_id = uuid.uuid4()

        with patch(
            f"{MODULE}.vision_event_service.delete_state_change_event",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await delete_state_change_event(session, event_id, ACCOUNT_NAME)

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            delete_state_change_event,
        )

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_event_service.delete_state_change_event",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_state_change_event(session, uuid.uuid4(), ACCOUNT_NAME)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            delete_state_change_event,
        )

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_event_service.delete_state_change_event",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_state_change_event(session, uuid.uuid4(), ACCOUNT_NAME)
            assert exc_info.value.status_code == 500


class TestUpdateStateChangeEvent:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            update_state_change_event,
        )

        session = AsyncMock()
        event_id = uuid.uuid4()
        expected = _make_response(
            id=event_id,
            event_metadata={"is_test": True, "test_group": "g1"},
            is_test=True,
            test_group="g1",
        )
        request = UpdateStateChangeEventRequest(is_test=True, test_group="g1")

        with patch(
            f"{MODULE}.vision_event_service.update_state_change_event",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await update_state_change_event(
                session, event_id, request, ACCOUNT_NAME
            )

        assert result.id == event_id
        assert result.is_test is True
        assert result.test_group == "g1"

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            update_state_change_event,
        )

        session = AsyncMock()
        request = UpdateStateChangeEventRequest(is_test=True)

        with patch(
            f"{MODULE}.vision_event_service.update_state_change_event",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_state_change_event(
                    session, uuid.uuid4(), request, ACCOUNT_NAME
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_state_change_events import (
            update_state_change_event,
        )

        session = AsyncMock()
        request = UpdateStateChangeEventRequest(is_test=True)

        with patch(
            f"{MODULE}.vision_event_service.update_state_change_event",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_state_change_event(
                    session, uuid.uuid4(), request, ACCOUNT_NAME
                )
            assert exc_info.value.status_code == 500
