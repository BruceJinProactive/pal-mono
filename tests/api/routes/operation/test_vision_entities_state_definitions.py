"""Tests for api.routes.operation._vision_entities state definition handlers."""

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.schemas.operations.vision_entity import (
    CreateStateDefinitionRequest,
    ListStateDefinitionsResponse,
    StateDefinitionResponse,
    UpdateStateDefinitionRequest,
)

MODULE = "api.routes.operation._vision_entities"

ACCOUNT_NAME = "test-account"
ACCOUNT_ID = uuid.uuid4()


def _mock_resolve_account_id() -> Any:
    mock_account = MagicMock()
    mock_account.id = ACCOUNT_ID
    return patch(
        f"{MODULE}.account_service.get_account_async",
        new_callable=AsyncMock,
        return_value=mock_account,
    )


def _make_sd_response(**overrides: object) -> StateDefinitionResponse:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "entity_type_id": uuid.uuid4(),
        "name": "clean",
        "display_name": "Clean",
        "color": None,
        "sort_order": 0,
        "is_default": False,
        "criteria": None,
        "created_at": datetime(2026, 4, 29, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return StateDefinitionResponse(**defaults)  # type: ignore[arg-type]


class TestCreateStateDefinition:

    @pytest.mark.asyncio
    async def test_success_commits_and_returns(self) -> None:
        from api.routes.operation._vision_entities import create_state_definition

        session = AsyncMock()
        entity_type_id = uuid.uuid4()
        request = CreateStateDefinitionRequest(name="clean", display_name="Clean")
        expected = _make_sd_response(entity_type_id=entity_type_id)

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.create_state_definition",
                new_callable=AsyncMock,
                return_value=expected,
            ),
        ):
            result = await create_state_definition(
                session, ACCOUNT_NAME, entity_type_id, request
            )

        assert result.name == "clean"

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_entities import create_state_definition

        session = AsyncMock()
        request = CreateStateDefinitionRequest(name="x", display_name="X")

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.create_state_definition",
                new_callable=AsyncMock,
                side_effect=ValueError("not found"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_state_definition(
                    session, ACCOUNT_NAME, uuid.uuid4(), request
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_duplicate_returns_400(self) -> None:
        from api.routes.operation._vision_entities import create_state_definition

        session = AsyncMock()
        request = CreateStateDefinitionRequest(name="dup", display_name="Dup")

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.create_state_definition",
                new_callable=AsyncMock,
                side_effect=ValueError("already exists"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_state_definition(
                    session, ACCOUNT_NAME, uuid.uuid4(), request
                )
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_entities import create_state_definition

        session = AsyncMock()
        request = CreateStateDefinitionRequest(name="x", display_name="X")

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.create_state_definition",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_state_definition(
                    session, ACCOUNT_NAME, uuid.uuid4(), request
                )
            assert exc_info.value.status_code == 500


class TestListStateDefinitions:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_entities import list_state_definitions

        session = AsyncMock()
        expected = ListStateDefinitionsResponse(items=[], total=0)

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.list_state_definitions",
                new_callable=AsyncMock,
                return_value=expected,
            ),
        ):
            result = await list_state_definitions(session, ACCOUNT_NAME, uuid.uuid4())

        assert result.total == 0

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_entities import list_state_definitions

        session = AsyncMock()

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.list_state_definitions",
                new_callable=AsyncMock,
                side_effect=ValueError("not found"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_state_definitions(session, ACCOUNT_NAME, uuid.uuid4())
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_entities import list_state_definitions

        session = AsyncMock()

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.list_state_definitions",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_state_definitions(session, ACCOUNT_NAME, uuid.uuid4())
            assert exc_info.value.status_code == 500


class TestUpdateStateDefinition:

    @pytest.mark.asyncio
    async def test_success_commits(self) -> None:
        from api.routes.operation._vision_entities import update_state_definition

        session = AsyncMock()
        sd_id = uuid.uuid4()
        request = UpdateStateDefinitionRequest(display_name="Dirty")
        expected = _make_sd_response(id=sd_id, display_name="Dirty")

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.update_state_definition",
                new_callable=AsyncMock,
                return_value=expected,
            ),
        ):
            result = await update_state_definition(
                session, ACCOUNT_NAME, uuid.uuid4(), sd_id, request
            )

        assert result.display_name == "Dirty"

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_entities import update_state_definition

        session = AsyncMock()
        request = UpdateStateDefinitionRequest(display_name="X")

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.update_state_definition",
                new_callable=AsyncMock,
                side_effect=ValueError("not found"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_state_definition(
                    session, ACCOUNT_NAME, uuid.uuid4(), uuid.uuid4(), request
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_duplicate_name_returns_400(self) -> None:
        from api.routes.operation._vision_entities import update_state_definition

        session = AsyncMock()
        request = UpdateStateDefinitionRequest(name="taken")

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.update_state_definition",
                new_callable=AsyncMock,
                side_effect=ValueError("already exists"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_state_definition(
                    session, ACCOUNT_NAME, uuid.uuid4(), uuid.uuid4(), request
                )
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_entities import update_state_definition

        session = AsyncMock()
        request = UpdateStateDefinitionRequest(display_name="X")

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.update_state_definition",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_state_definition(
                    session, ACCOUNT_NAME, uuid.uuid4(), uuid.uuid4(), request
                )
            assert exc_info.value.status_code == 500


class TestDeleteStateDefinition:

    @pytest.mark.asyncio
    async def test_success_commits(self) -> None:
        from api.routes.operation._vision_entities import delete_state_definition

        session = AsyncMock()

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.delete_state_definition",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            await delete_state_definition(
                session, ACCOUNT_NAME, uuid.uuid4(), uuid.uuid4()
            )

    @pytest.mark.asyncio
    async def test_cannot_delete_returns_400(self) -> None:
        from api.routes.operation._vision_entities import delete_state_definition

        session = AsyncMock()

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.delete_state_definition",
                new_callable=AsyncMock,
                side_effect=ValueError("Cannot delete state definition: 3 entities"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_state_definition(
                    session, ACCOUNT_NAME, uuid.uuid4(), uuid.uuid4()
                )
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_entities import delete_state_definition

        session = AsyncMock()

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.delete_state_definition",
                new_callable=AsyncMock,
                side_effect=ValueError("not found"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_state_definition(
                    session, ACCOUNT_NAME, uuid.uuid4(), uuid.uuid4()
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_entities import delete_state_definition

        session = AsyncMock()

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.delete_state_definition",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_state_definition(
                    session, ACCOUNT_NAME, uuid.uuid4(), uuid.uuid4()
                )
            assert exc_info.value.status_code == 500
