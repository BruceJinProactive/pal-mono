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
    sd.definition_type = overrides.get("definition_type", "cleanliness")
    sd.sort_order = overrides.get("sort_order", 0)
    sd.is_default = overrides.get("is_default", False)
    sd.is_active = overrides.get("is_active", True)
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
            assert result.current_state_since is not None
            assert result.current_states["cleanliness"].state_definition_id == (
                default_state_id
            )
            assert result.current_states["cleanliness"].state == "clean"
            assert (
                result.current_states["cleanliness"].current_state_since
                == result.current_state_since
            )
            entity_repo.create.assert_awaited_once()
            created_record = entity_repo.create.await_args.args[0]
            assert created_record.entity_metadata["current_states"]["cleanliness"] == {
                "state_definition_id": str(default_state_id),
                "state": "clean",
                "current_state_since": result.current_state_since.isoformat(),
                "observed_at": result.current_state_since.isoformat(),
            }

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
    async def test_creates_entity_with_all_default_state_types(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        clean_state_id = uuid.uuid4()
        empty_state_id = uuid.uuid4()
        dirty_state_id = uuid.uuid4()

        request = CreateEntityRequest(entity_type_id=entity_type_id, name="Table 1")

        clean_state = _make_state_def_mock(
            id=clean_state_id,
            entity_type_id=entity_type_id,
            name="clean",
            definition_type="cleanliness",
            is_default=True,
        )
        empty_state = _make_state_def_mock(
            id=empty_state_id,
            entity_type_id=entity_type_id,
            name="empty",
            definition_type="occupation",
            is_default=True,
        )
        dirty_state = _make_state_def_mock(
            id=dirty_state_id,
            entity_type_id=entity_type_id,
            name="dirty",
            definition_type="cleanliness",
            is_default=False,
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
            sd_repo.list_by_entity_type.return_value = [
                dirty_state,
                clean_state,
                empty_state,
            ]
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import create_entity

            result = await create_entity(session, project_id, request)

            assert result.current_state_id == clean_state_id
            assert set(result.current_states) == {"cleanliness", "occupation"}
            assert result.current_states["cleanliness"].state_definition_id == (
                clean_state_id
            )
            assert result.current_states["occupation"].state_definition_id == (
                empty_state_id
            )
            assert result.current_states["cleanliness"].state_definition_id != (
                dirty_state_id
            )

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
    async def test_returns_current_states_from_metadata(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        state_id = uuid.uuid4()
        observed_at = datetime.now(timezone.utc)
        entity = _make_entity_mock(
            id=entity_id,
            project_id=project_id,
            entity_metadata={
                "current_states": {
                    "occupation": {
                        "state_definition_id": str(state_id),
                        "state": "occupied",
                        "current_state_since": observed_at.isoformat(),
                        "observed_at": observed_at.isoformat(),
                    }
                }
            },
        )

        with patch(f"{MODULE}.VisionEntityRepository") as mock_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity
            mock_cls.return_value = repo

            from services.vision_entity_service._implementation import get_entity

            result = await get_entity(session, project_id, entity_id)

            assert result.current_states["occupation"].state_definition_id == state_id
            assert result.current_states["occupation"].state == "occupied"
            assert (
                result.current_states["occupation"].current_state_since == observed_at
            )
            assert result.current_states["occupation"].observed_at == observed_at

    def test_current_state_response_ignores_invalid_metadata(self) -> None:
        from services.vision_entity_service._implementation import (
            _build_current_state_response,
        )

        state_id = uuid.uuid4()
        observed_at = datetime.now(timezone.utc)

        response = _build_current_state_response(
            {
                "state_definition_id": state_id,
                "state": 123,
                "current_state_since": observed_at,
                "observed_at": "not-a-date",
            }
        )

        assert response is not None
        assert response.state_definition_id == state_id
        assert response.state is None
        assert response.current_state_since == observed_at
        assert response.observed_at is None
        assert _build_current_state_response("not metadata") is None
        assert (
            _build_current_state_response({"state_definition_id": "not-a-uuid"}) is None
        )
        assert _build_current_state_response({"state_definition_id": 123}) is None

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
        request = UpdateEntityStateRequest(state_definition_id=state_def_id)

        with (
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_event_cls,
        ):
            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = entity

            async def update_entity(
                entity_id_arg: uuid.UUID, **kwargs: object
            ) -> MagicMock:
                assert entity_id_arg == entity_id
                for key, value in kwargs.items():
                    setattr(entity, key, value)
                return entity

            entity_repo.update = AsyncMock(side_effect=update_entity)
            mock_entity_cls.return_value = entity_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = state_def
            mock_sd_cls.return_value = sd_repo

            event_repo = AsyncMock()
            event_repo.create.return_value = None
            mock_event_cls.return_value = event_repo

            from services.vision_entity_service._implementation import (
                update_entity_state,
            )

            result = await update_entity_state(session, project_id, entity_id, request)

            assert result.current_state_id == state_def_id
            assert result.current_states["cleanliness"].state_definition_id == (
                state_def_id
            )
            update_kwargs = entity_repo.update.await_args.kwargs
            assert update_kwargs["entity_metadata"]["current_states"][
                "cleanliness"
            ] == {
                "state_definition_id": str(state_def_id),
                "state": "clean",
                "current_state_since": update_kwargs["current_state_since"].isoformat(),
                "observed_at": update_kwargs["current_state_since"].isoformat(),
            }
            event_repo.create.assert_awaited_once()
            state_change_event = event_repo.create.await_args.args[0]
            assert state_change_event.event_metadata == {
                "definition_type": "cleanliness"
            }

    @pytest.mark.asyncio
    async def test_transitions_from_previous_metadata_state(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        previous_state_id = uuid.uuid4()
        state_def_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        entity = _make_entity_mock(
            id=entity_id,
            project_id=project_id,
            entity_type_id=entity_type_id,
            entity_metadata={
                "current_states": {
                    "cleanliness": {
                        "state_definition_id": str(previous_state_id),
                        "state": "dirty",
                        "current_state_since": now.isoformat(),
                        "observed_at": now.isoformat(),
                    }
                }
            },
        )
        state_def = _make_state_def_mock(id=state_def_id, entity_type_id=entity_type_id)
        previous_state_def = _make_state_def_mock(
            id=previous_state_id,
            entity_type_id=entity_type_id,
            name="dirty",
            definition_type="cleanliness",
        )

        request = UpdateEntityStateRequest(state_definition_id=state_def_id)

        with (
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_event_cls,
        ):
            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = entity
            entity_repo.update.return_value = entity
            mock_entity_cls.return_value = entity_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.side_effect = [state_def, previous_state_def]
            mock_sd_cls.return_value = sd_repo

            event_repo = AsyncMock()
            event_repo.create.return_value = None
            mock_event_cls.return_value = event_repo

            from services.vision_entity_service._implementation import (
                update_entity_state,
            )

            await update_entity_state(session, project_id, entity_id, request)

            state_change_event = event_repo.create.await_args.args[0]
            assert state_change_event.previous_state_id == previous_state_id

    @pytest.mark.asyncio
    async def test_transitions_from_matching_legacy_current_state(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        previous_state_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        entity = _make_entity_mock(
            id=entity_id,
            project_id=project_id,
            entity_type_id=entity_type_id,
            current_state_id=previous_state_id,
        )
        state_def = _make_state_def_mock(id=state_def_id, entity_type_id=entity_type_id)
        previous_state_def = _make_state_def_mock(
            id=previous_state_id,
            entity_type_id=entity_type_id,
            name="dirty",
            definition_type="cleanliness",
        )

        request = UpdateEntityStateRequest(state_definition_id=state_def_id)

        with (
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
            patch(f"{MODULE}.VisionStateChangeEventRepository") as mock_event_cls,
        ):
            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = entity
            entity_repo.update.return_value = entity
            mock_entity_cls.return_value = entity_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.side_effect = [state_def, previous_state_def]
            mock_sd_cls.return_value = sd_repo

            event_repo = AsyncMock()
            event_repo.create.return_value = None
            mock_event_cls.return_value = event_repo

            from services.vision_entity_service._implementation import (
                update_entity_state,
            )

            await update_entity_state(session, project_id, entity_id, request)

            state_change_event = event_repo.create.await_args.args[0]
            assert state_change_event.previous_state_id == previous_state_id

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


class TestDeleteEntityState:

    @pytest.mark.asyncio
    async def test_removes_state_type_and_keeps_remaining_state(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        removed_state_id = uuid.uuid4()
        remaining_state_id = uuid.uuid4()
        removed_since = datetime(2026, 6, 3, 12, tzinfo=timezone.utc)
        remaining_since = datetime(2026, 6, 3, 11, tzinfo=timezone.utc)

        entity = _make_entity_mock(
            id=entity_id,
            project_id=project_id,
            entity_type_id=entity_type_id,
            current_state_id=removed_state_id,
            current_state_since=removed_since,
            entity_metadata={
                "current_states": {
                    "glove_usage": {
                        "state_definition_id": str(removed_state_id),
                        "state": "gloves_off",
                        "current_state_since": removed_since.isoformat(),
                        "observed_at": removed_since.isoformat(),
                    },
                    "location": {
                        "state_definition_id": str(remaining_state_id),
                        "state": "food_container_on_floor",
                        "current_state_since": remaining_since.isoformat(),
                        "observed_at": remaining_since.isoformat(),
                    },
                }
            },
        )

        with (
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = entity

            async def update_entity(
                entity_id_arg: uuid.UUID, **kwargs: object
            ) -> MagicMock:
                assert entity_id_arg == entity_id
                for key, value in kwargs.items():
                    setattr(entity, key, value)
                return entity

            entity_repo.update = AsyncMock(side_effect=update_entity)
            mock_entity_cls.return_value = entity_repo
            mock_sd_cls.return_value = AsyncMock()

            from services.vision_entity_service._implementation import (
                delete_entity_state,
            )

            result = await delete_entity_state(
                session, project_id, entity_id, "glove_usage"
            )

        assert "glove_usage" not in result.current_states
        assert result.current_states["location"].state_definition_id == (
            remaining_state_id
        )
        assert result.current_state_id == remaining_state_id
        assert result.current_state_since == remaining_since
        update_kwargs = entity_repo.update.await_args.kwargs
        assert "glove_usage" not in update_kwargs["entity_metadata"]["current_states"]
        assert update_kwargs["current_state_id"] == remaining_state_id

    @pytest.mark.asyncio
    async def test_missing_state_type_is_noop(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity = _make_entity_mock(id=entity_id, project_id=project_id)

        with (
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = entity
            mock_entity_cls.return_value = entity_repo
            mock_sd_cls.return_value = AsyncMock()

            from services.vision_entity_service._implementation import (
                delete_entity_state,
            )

            result = await delete_entity_state(
                session, project_id, entity_id, "glove_usage"
            )

        assert result.id == entity_id
        entity_repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_removes_state_type_with_invalid_metadata_state_id(self) -> None:
        session = AsyncMock()
        project_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity = _make_entity_mock(
            id=entity_id,
            project_id=project_id,
            entity_metadata={
                "label": "Area 1",
                "current_states": {
                    "glove_usage": {
                        "state_definition_id": "not-a-uuid",
                        "state": "gloves_off",
                    }
                },
            },
        )

        with (
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = entity

            async def update_entity(
                entity_id_arg: uuid.UUID, **kwargs: object
            ) -> MagicMock:
                assert entity_id_arg == entity_id
                for key, value in kwargs.items():
                    setattr(entity, key, value)
                return entity

            entity_repo.update = AsyncMock(side_effect=update_entity)
            mock_entity_cls.return_value = entity_repo
            mock_sd_cls.return_value = AsyncMock()

            from services.vision_entity_service._implementation import (
                delete_entity_state,
            )

            result = await delete_entity_state(
                session, project_id, entity_id, "glove_usage"
            )

        assert result.current_states == {}
        update_kwargs = entity_repo.update.await_args.kwargs
        assert update_kwargs["entity_metadata"] == {"label": "Area 1"}
        assert update_kwargs["current_state_id"] is None

    @pytest.mark.asyncio
    async def test_entity_not_found_raises(self) -> None:
        session = AsyncMock()

        with patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls:
            entity_repo = AsyncMock()
            entity_repo.get_by_id.return_value = None
            mock_entity_cls.return_value = entity_repo

            from services.vision_entity_service._implementation import (
                delete_entity_state,
            )

            with pytest.raises(ValueError, match="not found"):
                await delete_entity_state(
                    session, uuid.uuid4(), uuid.uuid4(), "glove_usage"
                )


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
