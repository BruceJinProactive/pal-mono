"""Tests for api.routes.operation._vision_entities entity handlers."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.schemas.operations.vision_entity import (
    CreateEntityRequest,
    EntityResponse,
    ListEntitiesResponse,
    UpdateEntityRequest,
    UpdateEntityStateRequest,
)

MODULE = "api.routes.operation._vision_entities"


def _make_entity_response(**overrides: object) -> EntityResponse:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "entity_type_id": uuid.uuid4(),
        "name": "Table 1",
        "current_state_id": None,
        "current_state_since": None,
        "entity_metadata": {},
        "is_active": True,
        "created_at": datetime(2026, 4, 29, tzinfo=timezone.utc),
        "updated_at": None,
    }
    defaults.update(overrides)
    return EntityResponse(**defaults)  # type: ignore[arg-type]


class TestCreateEntity:

    @pytest.mark.asyncio
    async def test_success_commits_and_returns(self) -> None:
        from api.routes.operation._vision_entities import create_entity

        session = AsyncMock()
        project_id = uuid.uuid4()
        request = CreateEntityRequest(entity_type_id=uuid.uuid4(), name="Table 1")
        expected = _make_entity_response(project_id=project_id)

        with patch(
            f"{MODULE}.vision_entity_service.create_entity",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await create_entity(session, project_id, request)

        assert result.name == "Table 1"

    @pytest.mark.asyncio
    async def test_value_error_returns_400(self) -> None:
        from api.routes.operation._vision_entities import create_entity

        session = AsyncMock()
        request = CreateEntityRequest(entity_type_id=uuid.uuid4(), name="dup")

        with patch(
            f"{MODULE}.vision_entity_service.create_entity",
            new_callable=AsyncMock,
            side_effect=ValueError("already exists"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_entity(session, uuid.uuid4(), request)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_entities import create_entity

        session = AsyncMock()
        request = CreateEntityRequest(entity_type_id=uuid.uuid4(), name="x")

        with patch(
            f"{MODULE}.vision_entity_service.create_entity",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await create_entity(session, uuid.uuid4(), request)
            assert exc_info.value.status_code == 500


class TestGetEntity:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_entities import get_entity

        session = AsyncMock()
        entity_id = uuid.uuid4()
        expected = _make_entity_response(id=entity_id)

        with patch(
            f"{MODULE}.vision_entity_service.get_entity",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await get_entity(session, uuid.uuid4(), entity_id)

        assert result.id == entity_id

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_entities import get_entity

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_entity_service.get_entity",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_entity(session, uuid.uuid4(), uuid.uuid4())
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_entities import get_entity

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_entity_service.get_entity",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_entity(session, uuid.uuid4(), uuid.uuid4())
            assert exc_info.value.status_code == 500


class TestListEntities:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from api.routes.operation._vision_entities import list_entities

        session = AsyncMock()
        expected = ListEntitiesResponse(items=[], total=0)

        with patch(
            f"{MODULE}.vision_entity_service.list_entities",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await list_entities(session, uuid.uuid4())

        assert result.total == 0

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_entities import list_entities

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_entity_service.list_entities",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_entities(session, uuid.uuid4())
            assert exc_info.value.status_code == 500


class TestUpdateEntity:

    @pytest.mark.asyncio
    async def test_success_commits(self) -> None:
        from api.routes.operation._vision_entities import update_entity

        session = AsyncMock()
        entity_id = uuid.uuid4()
        request = UpdateEntityRequest(name="New Name")
        expected = _make_entity_response(id=entity_id, name="New Name")

        with patch(
            f"{MODULE}.vision_entity_service.update_entity",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await update_entity(session, uuid.uuid4(), entity_id, request)

        assert result.name == "New Name"

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_entities import update_entity

        session = AsyncMock()
        request = UpdateEntityRequest(name="X")

        with patch(
            f"{MODULE}.vision_entity_service.update_entity",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_entity(session, uuid.uuid4(), uuid.uuid4(), request)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_duplicate_name_returns_400(self) -> None:
        from api.routes.operation._vision_entities import update_entity

        session = AsyncMock()
        request = UpdateEntityRequest(name="taken")

        with patch(
            f"{MODULE}.vision_entity_service.update_entity",
            new_callable=AsyncMock,
            side_effect=ValueError("already exists"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_entity(session, uuid.uuid4(), uuid.uuid4(), request)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_entities import update_entity

        session = AsyncMock()
        request = UpdateEntityRequest(name="X")

        with patch(
            f"{MODULE}.vision_entity_service.update_entity",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_entity(session, uuid.uuid4(), uuid.uuid4(), request)
            assert exc_info.value.status_code == 500


class TestUpdateEntityState:

    @pytest.mark.asyncio
    async def test_success_commits(self) -> None:
        from api.routes.operation._vision_entities import update_entity_state

        session = AsyncMock()
        entity_id = uuid.uuid4()
        state_id = uuid.uuid4()
        request = UpdateEntityStateRequest(state_definition_id=state_id)
        expected = _make_entity_response(id=entity_id, current_state_id=state_id)

        with patch(
            f"{MODULE}.vision_entity_service.update_entity_state",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            result = await update_entity_state(
                session, uuid.uuid4(), entity_id, request
            )

        assert result.current_state_id == state_id

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_entities import update_entity_state

        session = AsyncMock()
        request = UpdateEntityStateRequest(state_definition_id=uuid.uuid4())

        with patch(
            f"{MODULE}.vision_entity_service.update_entity_state",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_entity_state(session, uuid.uuid4(), uuid.uuid4(), request)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_wrong_type_returns_400(self) -> None:
        from api.routes.operation._vision_entities import update_entity_state

        session = AsyncMock()
        request = UpdateEntityStateRequest(state_definition_id=uuid.uuid4())

        with patch(
            f"{MODULE}.vision_entity_service.update_entity_state",
            new_callable=AsyncMock,
            side_effect=ValueError("does not belong"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_entity_state(session, uuid.uuid4(), uuid.uuid4(), request)
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_entities import update_entity_state

        session = AsyncMock()
        request = UpdateEntityStateRequest(state_definition_id=uuid.uuid4())

        with patch(
            f"{MODULE}.vision_entity_service.update_entity_state",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_entity_state(session, uuid.uuid4(), uuid.uuid4(), request)
            assert exc_info.value.status_code == 500


class TestDeleteEntity:

    @pytest.mark.asyncio
    async def test_success_commits(self) -> None:
        from api.routes.operation._vision_entities import delete_entity

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_entity_service.delete_entity",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await delete_entity(session, uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self) -> None:
        from api.routes.operation._vision_entities import delete_entity

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_entity_service.delete_entity",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_entity(session, uuid.uuid4(), uuid.uuid4())
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self) -> None:
        from api.routes.operation._vision_entities import delete_entity

        session = AsyncMock()

        with patch(
            f"{MODULE}.vision_entity_service.delete_entity",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await delete_entity(session, uuid.uuid4(), uuid.uuid4())
            assert exc_info.value.status_code == 500
