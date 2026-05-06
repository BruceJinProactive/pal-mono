"""Tests for vision_entity_service entity CRUD operations."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas.operations.vision_entity import (
    CreateEntityRequest,
    UpdateEntityRequest,
    UpdateEntityStateRequest,
)

MODULE = "services.vision_entity_service._implementation"


def _make_entity_mock(**overrides: object) -> MagicMock:
    e = MagicMock()
    e.id = overrides.get("id", uuid.uuid4())
    e.project_id = overrides.get("project_id", uuid.uuid4())
    e.entity_type_id = overrides.get("entity_type_id", uuid.uuid4())
    e.name = overrides.get("name", "Table 1")
    e.current_state_id = overrides.get("current_state_id", None)
    e.current_state_since = overrides.get("current_state_since", None)
    e.entity_metadata = overrides.get("entity_metadata", {})
    e.is_active = overrides.get("is_active", True)
    e.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    e.updated_at = overrides.get("updated_at", None)
    return e


def _make_state_def_mock(**overrides: object) -> MagicMock:
    sd = MagicMock()
    sd.id = overrides.get("id", uuid.uuid4())
    sd.entity_type_id = overrides.get("entity_type_id", uuid.uuid4())
    sd.name = overrides.get("name", "clean")
    sd.display_name = overrides.get("display_name", "Clean")
    sd.color = overrides.get("color", None)
    sd.sort_order = overrides.get("sort_order", 0)
    sd.is_default = overrides.get("is_default", False)
    sd.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    return sd


class TestCreateEntity:

    @pytest.mark.asyncio
    async def test_creates_entity_with_default_state(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        default_state_id = uuid.uuid4()

        request = CreateEntityRequest(entity_type_id=entity_type_id, name="Table 1")

        default_state = _make_state_def_mock(
            id=default_state_id, entity_type_id=entity_type_id, is_default=True
        )

        with (
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            entity_repo = AsyncMock()
            entity_repo.get_by_project_type_and_name.return_value = None
            entity_repo.create.return_value = None
            mock_entity_cls.return_value = entity_repo

            sd_repo = AsyncMock()
            sd_repo.list_by_entity_type.return_value = [default_state]
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import create_entity

            result = await create_entity(session, project_id, request)

            assert result.current_state_id == default_state_id
            entity_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_entity_without_default_state(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        request = CreateEntityRequest(entity_type_id=entity_type_id, name="Table 1")

        with (
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            entity_repo = AsyncMock()
            entity_repo.get_by_project_type_and_name.return_value = None
            entity_repo.create.return_value = None
            mock_entity_cls.return_value = entity_repo

            sd_repo = AsyncMock()
            sd_repo.list_by_entity_type.return_value = []
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import create_entity

            result = await create_entity(session, project_id, request)

            assert result.current_state_id is None

    @pytest.mark.asyncio
    async def test_duplicate_name_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        request = CreateEntityRequest(entity_type_id=entity_type_id, name="Table 1")
        existing = _make_entity_mock(
            project_id=project_id, entity_type_id=entity_type_id
        )

        with patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls:
            entity_repo = AsyncMock()
            entity_repo.get_by_project_type_and_name.return_value = existing
            mock_entity_cls.return_value = entity_repo

            from services.vision_entity_service._implementation import create_entity

            with pytest.raises(ValueError, match="already exists"):
                await create_entity(session, project_id, request)


class TestGetEntity:

    @pytest.mark.asyncio
    async def test_returns_entity(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity = _make_entity_mock(id=entity_id, project_id=project_id)

        with patch(f"{MODULE}.VisionEntityRepository") as mock_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity
            mock_cls.return_value = repo

            from services.vision_entity_service._implementation import get_entity

            result = await get_entity(session, project_id, entity_id)

            assert result.id == entity_id

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()

        with patch(f"{MODULE}.VisionEntityRepository") as mock_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = None
            mock_cls.return_value = repo

            from services.vision_entity_service._implementation import get_entity

            with pytest.raises(ValueError, match="not found"):
                await get_entity(session, uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_wrong_project_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        other_project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity = _make_entity_mock(id=entity_id, project_id=other_project_id)

        with patch(f"{MODULE}.VisionEntityRepository") as mock_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity
            mock_cls.return_value = repo

            from services.vision_entity_service._implementation import get_entity

            with pytest.raises(ValueError, match="not found"):
                await get_entity(session, project_id, entity_id)


class TestListEntities:

    @pytest.mark.asyncio
    async def test_returns_all(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entities = [
            _make_entity_mock(project_id=project_id, name="Table 1"),
            _make_entity_mock(project_id=project_id, name="Table 2"),
        ]

        with patch(f"{MODULE}.VisionEntityRepository") as mock_cls:
            repo = AsyncMock()
            repo.list_by_project.return_value = entities
            mock_cls.return_value = repo

            from services.vision_entity_service._implementation import list_entities

            result = await list_entities(session, project_id)

            assert result.total == 2

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        session = AsyncMock()

        with patch(f"{MODULE}.VisionEntityRepository") as mock_cls:
            repo = AsyncMock()
            repo.list_by_project.return_value = []
            mock_cls.return_value = repo

            from services.vision_entity_service._implementation import list_entities

            result = await list_entities(session, uuid.uuid4())

            assert result.total == 0


class TestUpdateEntity:

    @pytest.mark.asyncio
    async def test_updates_fields(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity = _make_entity_mock(id=entity_id, project_id=project_id)
        updated = _make_entity_mock(
            id=entity_id, project_id=project_id, name="New Name"
        )

        request = UpdateEntityRequest(name="New Name")

        with patch(f"{MODULE}.VisionEntityRepository") as mock_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity
            repo.get_by_project_type_and_name.return_value = None
            repo.update.return_value = updated
            mock_cls.return_value = repo

            from services.vision_entity_service._implementation import update_entity

            result = await update_entity(session, project_id, entity_id, request)

            assert result.name == "New Name"

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()
        request = UpdateEntityRequest(name="X")

        with patch(f"{MODULE}.VisionEntityRepository") as mock_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = None
            mock_cls.return_value = repo

            from services.vision_entity_service._implementation import update_entity

            with pytest.raises(ValueError, match="not found"):
                await update_entity(session, uuid.uuid4(), uuid.uuid4(), request)

    @pytest.mark.asyncio
    async def test_duplicate_name_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        other_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        entity = _make_entity_mock(
            id=entity_id,
            project_id=project_id,
            entity_type_id=entity_type_id,
        )
        existing_other = _make_entity_mock(
            id=other_id,
            project_id=project_id,
            entity_type_id=entity_type_id,
            name="Taken",
        )

        request = UpdateEntityRequest(name="Taken")

        with patch(f"{MODULE}.VisionEntityRepository") as mock_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity
            repo.get_by_project_type_and_name.return_value = existing_other
            mock_cls.return_value = repo

            from services.vision_entity_service._implementation import update_entity

            with pytest.raises(ValueError, match="already exists"):
                await update_entity(session, project_id, entity_id, request)

    @pytest.mark.asyncio
    async def test_updates_metadata_and_is_active(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity = _make_entity_mock(id=entity_id, project_id=project_id)
        updated = _make_entity_mock(
            id=entity_id,
            project_id=project_id,
            entity_metadata={"seats": 6},
            is_active=False,
        )

        request = UpdateEntityRequest(entity_metadata={"seats": 6}, is_active=False)

        with patch(f"{MODULE}.VisionEntityRepository") as mock_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity
            repo.update.return_value = updated
            mock_cls.return_value = repo

            from services.vision_entity_service._implementation import update_entity

            result = await update_entity(session, project_id, entity_id, request)

            assert result.entity_metadata == {"seats": 6}
            assert result.is_active is False

    @pytest.mark.asyncio
    async def test_update_returns_none_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity = _make_entity_mock(id=entity_id, project_id=project_id)

        request = UpdateEntityRequest(name="New")

        with patch(f"{MODULE}.VisionEntityRepository") as mock_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity
            repo.get_by_project_type_and_name.return_value = None
            repo.update.return_value = None
            mock_cls.return_value = repo

            from services.vision_entity_service._implementation import update_entity

            with pytest.raises(ValueError, match="not found"):
                await update_entity(session, project_id, entity_id, request)

    @pytest.mark.asyncio
    async def test_no_changes_returns_existing(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity = _make_entity_mock(id=entity_id, project_id=project_id)

        request = UpdateEntityRequest()

        with patch(f"{MODULE}.VisionEntityRepository") as mock_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity
            mock_cls.return_value = repo

            from services.vision_entity_service._implementation import update_entity

            result = await update_entity(session, project_id, entity_id, request)

            assert result.id == entity_id
            repo.update.assert_not_awaited()


class TestUpdateEntityState:

    @pytest.mark.asyncio
    async def test_transitions_state(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        entity = _make_entity_mock(
            id=entity_id,
            project_id=project_id,
            entity_type_id=entity_type_id,
        )
        state_def = _make_state_def_mock(id=state_def_id, entity_type_id=entity_type_id)
        updated = _make_entity_mock(
            id=entity_id,
            project_id=project_id,
            current_state_id=state_def_id,
        )

        request = UpdateEntityStateRequest(state_definition_id=state_def_id)

        with (
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = entity
            entity_repo.update.return_value = updated
            mock_entity_cls.return_value = entity_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = state_def
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                update_entity_state,
            )

            result = await update_entity_state(session, project_id, entity_id, request)

            assert result.current_state_id == state_def_id

    @pytest.mark.asyncio
    async def test_wrong_entity_type_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        other_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        entity = _make_entity_mock(
            id=entity_id,
            project_id=project_id,
            entity_type_id=entity_type_id,
        )
        state_def = _make_state_def_mock(id=state_def_id, entity_type_id=other_type_id)

        request = UpdateEntityStateRequest(state_definition_id=state_def_id)

        with (
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = entity
            mock_entity_cls.return_value = entity_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = state_def
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                update_entity_state,
            )

            with pytest.raises(ValueError, match="not found"):
                await update_entity_state(session, project_id, entity_id, request)

    @pytest.mark.asyncio
    async def test_update_returns_none_raises(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        entity = _make_entity_mock(
            id=entity_id,
            project_id=project_id,
            entity_type_id=entity_type_id,
        )
        state_def = _make_state_def_mock(id=state_def_id, entity_type_id=entity_type_id)

        request = UpdateEntityStateRequest(state_definition_id=state_def_id)

        with (
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = entity
            entity_repo.update.return_value = None
            mock_entity_cls.return_value = entity_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = state_def
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                update_entity_state,
            )

            with pytest.raises(ValueError, match="not found"):
                await update_entity_state(session, project_id, entity_id, request)

    @pytest.mark.asyncio
    async def test_entity_not_found_raises(self) -> None:
        session = AsyncMock()
        request = UpdateEntityStateRequest(state_definition_id=uuid.uuid4())

        with patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls:
            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = None
            mock_entity_cls.return_value = entity_repo

            from services.vision_entity_service._implementation import (
                update_entity_state,
            )

            with pytest.raises(ValueError, match="not found"):
                await update_entity_state(session, uuid.uuid4(), uuid.uuid4(), request)


class TestDeleteEntity:

    @pytest.mark.asyncio
    async def test_deletes_entity(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity = _make_entity_mock(id=entity_id, project_id=project_id)

        with (
            patch(f"{MODULE}.VisionEntityRepository") as mock_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id.return_value = entity
            repo.delete.return_value = True
            mock_cls.return_value = repo

            mapping_repo = AsyncMock()
            mapping_repo.delete_by_entity.return_value = 0
            mock_mapping_cls.return_value = mapping_repo

            from services.vision_entity_service._implementation import delete_entity

            result = await delete_entity(session, project_id, entity_id)

            assert result is True
            mapping_repo.delete_by_entity.assert_called_once_with(entity_id)

    @pytest.mark.asyncio
    async def test_deletes_entity_with_existing_mappings(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity = _make_entity_mock(id=entity_id, project_id=project_id)

        with (
            patch(f"{MODULE}.VisionEntityRepository") as mock_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id.return_value = entity
            repo.delete.return_value = True
            mock_cls.return_value = repo

            mapping_repo = AsyncMock()
            mapping_repo.delete_by_entity.return_value = 2
            mock_mapping_cls.return_value = mapping_repo

            from services.vision_entity_service._implementation import delete_entity

            result = await delete_entity(session, project_id, entity_id)

            assert result is True
            mapping_repo.delete_by_entity.assert_called_once_with(entity_id)

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()

        with patch(f"{MODULE}.VisionEntityRepository") as mock_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = None
            mock_cls.return_value = repo

            from services.vision_entity_service._implementation import delete_entity

            with pytest.raises(ValueError, match="not found"):
                await delete_entity(session, uuid.uuid4(), uuid.uuid4())
