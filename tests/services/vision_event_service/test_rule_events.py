"""Tests for vision_event_service rule event operations."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas.operations.vision_rule_event import UpdateVisionRuleEventRequest
from db.pal_repository.data_classes.vision_rule_event import VisionRuleEventData

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
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "rule_id": RULE_ID,
        "entity_id": ENTITY_ID,
        "state_change_event_id": uuid.uuid4(),
        "severity": "high",
        "duration": Decimal("4.2500"),
        "manually_adjusted": False,
        "triggered_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "event_metadata": {},
    }
    defaults.update(overrides)
    return VisionRuleEventData(**defaults)  # type: ignore[arg-type]


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

            assert result.total == 1
            assert result.items[0].rule_id == RULE_ID
            assert result.items[0].duration == Decimal("4.2500")
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

            assert result.total == 1
            assert result.items[0].manually_adjusted is True
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
        request = UpdateVisionRuleEventRequest(
            triggered_at=triggered_at,
            duration=Decimal("2.5000"),
        )
        event_data = _make_event_data(
            id=event_id,
            triggered_at=triggered_at,
            duration=Decimal("2.5000"),
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
                request=request,
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
        request = UpdateVisionRuleEventRequest(
            triggered_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            duration=Decimal("1.0000"),
        )

        with patch(
            f"{MODULE}.account_service.get_account_async",
            new_callable=AsyncMock,
            return_value=None,
        ):
            from services.vision_event_service._rule_events import update_rule_event

            with pytest.raises(ValueError, match="not found"):
                await update_rule_event(session, uuid.uuid4(), request, "bad-account")

    @pytest.mark.asyncio
    async def test_raises_when_event_not_found(self) -> None:
        session = AsyncMock()
        request = UpdateVisionRuleEventRequest(
            triggered_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            duration=Decimal("1.0000"),
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
            repo.update_for_account.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_event_service._rule_events import update_rule_event

            with pytest.raises(ValueError, match="not found"):
                await update_rule_event(session, uuid.uuid4(), request, ACCOUNT_NAME)
