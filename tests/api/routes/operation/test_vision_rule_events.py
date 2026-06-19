"""Tests for api.routes.operation._vision_rule_events API handlers."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.schemas.operations.vision_rule_event import (
    ListVisionRuleEventsResponse,
    UpdateVisionRuleEventRequest,
    VisionRuleEventResponse,
)

MODULE = "api.routes.operation._vision_rule_events"

ACCOUNT_NAME = "test-account"
RULE_ID = uuid.uuid4()
ENTITY_ID = uuid.uuid4()


def _make_response(**overrides: object) -> VisionRuleEventResponse:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "rule_id": RULE_ID,
        "entity_id": ENTITY_ID,
        "state_change_event_id": uuid.uuid4(),
        "severity": "high",
        "duration": Decimal("3.7500"),
        "triggered_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "event_metadata": {},
    }
    defaults.update(overrides)
    return VisionRuleEventResponse(**defaults)  # type: ignore[arg-type]


class TestGetRuleEvent:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_rule_events import get_rule_event

        session = AsyncMock()
        event_id = uuid.uuid4()
        expected = _make_response(id=event_id)

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


class TestListRuleEvents:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_rule_events import list_rule_events

        session = AsyncMock()
        expected = ListVisionRuleEventsResponse(items=[], total=0)

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
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_rule_events import update_rule_event

        session = AsyncMock()
        event_id = uuid.uuid4()
        request = UpdateVisionRuleEventRequest(
            triggered_at=datetime(2026, 5, 1, 12, 30, tzinfo=timezone.utc),
            duration=Decimal("2.5000"),
        )
        expected = _make_response(
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
            request=request,
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
