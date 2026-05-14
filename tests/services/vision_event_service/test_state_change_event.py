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
)
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
        event_data = _make_event_data(id=event_id)

        with (
            patch(
                f"{MODULE}.account_service.get_account_async",
                new_callable=AsyncMock,
                return_value=_mock_account(),
            ),
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_repo_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id_for_account.return_value = event_data
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                get_state_change_event,
            )

            result = await get_state_change_event(session, event_id, ACCOUNT_NAME)

            assert result.id == event_id

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
            repo.list_by_account.return_value = [event_data]
            mock_repo_cls.return_value = repo

            from services.vision_event_service._implementation import (
                list_state_change_events,
            )

            result = await list_state_change_events(session, ACCOUNT_NAME)

            assert result.total == 1
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
            repo.list_by_account.return_value = []
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
                limit=50,
            )

            assert result.total == 0
            repo.list_by_account.assert_awaited_once_with(
                account_id=ACCOUNT_ID,
                project_id=project_id,
                entity_id=entity_id,
                start=start,
                end=end,
                limit=50,
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
