"""Tests for api.routes.operation._vision_entities API handlers."""

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.schemas.operations.vision_entity import (
    CreateEntityTypeRequest,
    EntityTypeResponse,
    ListEntityTypesResponse,
    UpdateEntityTypeRequest,
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


def _make_response(**overrides: object) -> EntityTypeResponse:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "account_id": ACCOUNT_ID,
        "name": "table",
        "display_name": "Table",
        "description": None,
        "icon": None,
        "is_active": True,
        "created_at": datetime(2026, 4, 29, tzinfo=timezone.utc),
        "updated_at": None,
    }
    defaults.update(overrides)
    return EntityTypeResponse(**defaults)  # type: ignore[arg-type]


class TestCreateEntityType:

    @pytest.mark.asyncio
    async def test_success_commits_and_returns(self) -> None:
        from api.routes.operation._vision_entities import create_entity_type

        session = AsyncMock()
        request = CreateEntityTypeRequest(name="table", display_name="Table")
        expected = _make_response()

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.create_entity_type",
                new_callable=AsyncMock,
                return_value=expected,
            ),
        ):
            result = await create_entity_type(session, ACCOUNT_NAME, request)

        assert result.name == "table"

    @pytest.mark.asyncio
    async def test_value_error_returns_400(self) -> None:
        from api.routes.operation._vision_entities import create_entity_type

        session = AsyncMock()
        request = CreateEntityTypeRequest(name="dup", display_name="Dup")

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.create_entity_type",
                new_callable=AsyncMock,
                side_effect=ValueError("already exists"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_entity_type(session, ACCOUNT_NAME, request)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_entities import create_entity_type

        session = AsyncMock()
        request = CreateEntityTypeRequest(name="x", display_name="X")

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.create_entity_type",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_entity_type(session, ACCOUNT_NAME, request)
            assert exc_info.value.status_code == 500


class TestGetEntityType:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_entities import get_entity_type

        session = AsyncMock()
        entity_type_id = uuid.uuid4()
        expected = _make_response(id=entity_type_id)

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.get_entity_type",
                new_callable=AsyncMock,
                return_value=expected,
            ),
        ):
            result = await get_entity_type(session, ACCOUNT_NAME, entity_type_id)

        assert result.id == entity_type_id

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_entities import get_entity_type

        session = AsyncMock()

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.get_entity_type",
                new_callable=AsyncMock,
                side_effect=ValueError("not found"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_entity_type(session, ACCOUNT_NAME, uuid.uuid4())
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_entities import get_entity_type

        session = AsyncMock()

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.get_entity_type",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_entity_type(session, ACCOUNT_NAME, uuid.uuid4())
            assert exc_info.value.status_code == 500


class TestListEntityTypes:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_entities import list_entity_types

        session = AsyncMock()
        expected = ListEntityTypesResponse(items=[], total=0)

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.list_entity_types",
                new_callable=AsyncMock,
                return_value=expected,
            ),
        ):
            result = await list_entity_types(session, ACCOUNT_NAME)

        assert result.total == 0

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_entities import list_entity_types

        session = AsyncMock()

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.list_entity_types",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_entity_types(session, ACCOUNT_NAME)
            assert exc_info.value.status_code == 500


class TestUpdateEntityType:

    @pytest.mark.asyncio
    async def test_success_commits(self) -> None:
        from api.routes.operation._vision_entities import update_entity_type

        session = AsyncMock()
        entity_type_id = uuid.uuid4()
        request = UpdateEntityTypeRequest(display_name="New Name")
        expected = _make_response(id=entity_type_id, display_name="New Name")

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.update_entity_type",
                new_callable=AsyncMock,
                return_value=expected,
            ),
        ):
            result = await update_entity_type(
                session, ACCOUNT_NAME, entity_type_id, request
            )

        assert result.display_name == "New Name"

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_entities import update_entity_type

        session = AsyncMock()
        request = UpdateEntityTypeRequest(display_name="X")

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.update_entity_type",
                new_callable=AsyncMock,
                side_effect=ValueError("not found"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_entity_type(session, ACCOUNT_NAME, uuid.uuid4(), request)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_duplicate_name_returns_400(self) -> None:
        from api.routes.operation._vision_entities import update_entity_type

        session = AsyncMock()
        request = UpdateEntityTypeRequest(name="taken")

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.update_entity_type",
                new_callable=AsyncMock,
                side_effect=ValueError("already exists"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_entity_type(session, ACCOUNT_NAME, uuid.uuid4(), request)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_entities import update_entity_type

        session = AsyncMock()
        request = UpdateEntityTypeRequest(display_name="X")

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.update_entity_type",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_entity_type(session, ACCOUNT_NAME, uuid.uuid4(), request)
            assert exc_info.value.status_code == 500


class TestDeleteEntityType:

    @pytest.mark.asyncio
    async def test_success_commits(self) -> None:
        from api.routes.operation._vision_entities import delete_entity_type

        session = AsyncMock()
        entity_type_id = uuid.uuid4()

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.delete_entity_type",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            await delete_entity_type(session, ACCOUNT_NAME, entity_type_id)

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_entities import delete_entity_type

        session = AsyncMock()

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.delete_entity_type",
                new_callable=AsyncMock,
                side_effect=ValueError("not found"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_entity_type(session, ACCOUNT_NAME, uuid.uuid4())
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_entities import delete_entity_type

        session = AsyncMock()

        with (
            _mock_resolve_account_id(),
            patch(
                f"{MODULE}.vision_entity_service.delete_entity_type",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_entity_type(session, ACCOUNT_NAME, uuid.uuid4())
            assert exc_info.value.status_code == 500
