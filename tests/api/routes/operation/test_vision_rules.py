"""Tests for api.routes.operation._vision_rules API handlers."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.schemas.operations.vision_rule import (
    CreateVisionRuleRequest,
    ListVisionRulesResponse,
    UpdateVisionRuleRequest,
    VisionRuleResponse,
)

MODULE = "api.routes.operation._vision_rules"

ACCOUNT_NAME = "test-account"
PROJECT_ID = uuid.uuid4()


def _make_response(**overrides: object) -> VisionRuleResponse:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "project_id": PROJECT_ID,
        "name": "Table must be clean",
        "description": None,
        "type": "table_cleanness",
        "severity": "high",
        "is_active": True,
        "rule_metadata": {},
        "label": [],
        "created_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "updated_at": None,
    }
    defaults.update(overrides)
    return VisionRuleResponse(**defaults)  # type: ignore[arg-type]


class TestCreateVisionRule:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_rules import create_vision_rule

        session = AsyncMock()
        request = CreateVisionRuleRequest(
            project_id=PROJECT_ID,
            name="Table must be clean",
            type="table_cleanness",
            severity="high",
        )
        expected = _make_response()

        with patch(
            f"{MODULE}.vision_rule_service.create_vision_rule",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await create_vision_rule(session, request, ACCOUNT_NAME)

        assert result.name == "Table must be clean"

    @pytest.mark.asyncio
    async def test_value_error_returns_400(self) -> None:
        from api.routes.operation._vision_rules import create_vision_rule

        session = AsyncMock()
        request = CreateVisionRuleRequest(
            project_id=PROJECT_ID,
            name="Test",
            type="table_cleanness",
            severity="high",
        )

        with patch(
            f"{MODULE}.vision_rule_service.create_vision_rule",
            new_callable=AsyncMock,
            side_effect=ValueError("project not owned"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_vision_rule(session, request, ACCOUNT_NAME)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_rules import create_vision_rule

        session = AsyncMock()
        request = CreateVisionRuleRequest(
            project_id=PROJECT_ID,
            name="Test",
            type="table_cleanness",
            severity="high",
        )

        with patch(
            f"{MODULE}.vision_rule_service.create_vision_rule",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_vision_rule(session, request, ACCOUNT_NAME)
            assert exc_info.value.status_code == 500


class TestGetVisionRule:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_rules import get_vision_rule

        session = AsyncMock()
        rule_id = uuid.uuid4()
        expected = _make_response(id=rule_id, label=["cleanliness"])

        with patch(
            f"{MODULE}.vision_rule_service.get_vision_rule",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await get_vision_rule(session, rule_id, ACCOUNT_NAME)

        assert result.id == rule_id
        assert result.label == ["cleanliness"]

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_rules import get_vision_rule

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_rule_service.get_vision_rule",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_vision_rule(session, uuid.uuid4(), ACCOUNT_NAME)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_rules import get_vision_rule

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_rule_service.get_vision_rule",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_vision_rule(session, uuid.uuid4(), ACCOUNT_NAME)
            assert exc_info.value.status_code == 500


class TestListVisionRules:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_rules import list_vision_rules

        session = AsyncMock()
        expected = ListVisionRulesResponse(items=[], total=0, items_by_label={})

        with patch(
            f"{MODULE}.vision_rule_service.list_vision_rules",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await list_vision_rules(session, ACCOUNT_NAME)

        assert result.total == 0
        assert result.items_by_label == {}

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_rules import list_vision_rules

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_rule_service.list_vision_rules",
            new_callable=AsyncMock,
            side_effect=ValueError("Account not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_vision_rules(session, "bad-account")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_rules import list_vision_rules

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_rule_service.list_vision_rules",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_vision_rules(session, ACCOUNT_NAME)
            assert exc_info.value.status_code == 500


class TestUpdateVisionRule:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_rules import update_vision_rule

        session = AsyncMock()
        rule_id = uuid.uuid4()
        expected = _make_response(id=rule_id, name="Updated", label=["priority"])
        request = UpdateVisionRuleRequest(name="Updated", label=["priority"])

        with patch(
            f"{MODULE}.vision_rule_service.update_vision_rule",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await update_vision_rule(session, rule_id, request, ACCOUNT_NAME)

        assert result.id == rule_id
        assert result.label == ["priority"]

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_rules import update_vision_rule

        session = AsyncMock()
        request = UpdateVisionRuleRequest(name="Updated")

        with patch(
            f"{MODULE}.vision_rule_service.update_vision_rule",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_vision_rule(session, uuid.uuid4(), request, ACCOUNT_NAME)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_rules import update_vision_rule

        session = AsyncMock()
        request = UpdateVisionRuleRequest(name="Updated")

        with patch(
            f"{MODULE}.vision_rule_service.update_vision_rule",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_vision_rule(session, uuid.uuid4(), request, ACCOUNT_NAME)
            assert exc_info.value.status_code == 500


class TestDeleteVisionRule:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_rules import delete_vision_rule

        session = AsyncMock()
        rule_id = uuid.uuid4()

        with patch(
            f"{MODULE}.vision_rule_service.delete_vision_rule",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await delete_vision_rule(session, rule_id, ACCOUNT_NAME)

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_rules import delete_vision_rule

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_rule_service.delete_vision_rule",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_vision_rule(session, uuid.uuid4(), ACCOUNT_NAME)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_rules import delete_vision_rule

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_rule_service.delete_vision_rule",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_vision_rule(session, uuid.uuid4(), ACCOUNT_NAME)
            assert exc_info.value.status_code == 500
