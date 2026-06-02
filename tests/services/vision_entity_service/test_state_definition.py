"""Tests for vision_entity_service state definition CRUD operations."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas.operations.vision_entity import (
    CreateStateDefinitionRequest,
    UpdateStateDefinitionRequest,
)

MODULE = "services.vision_entity_service._implementation"


def _make_entity_type_mock(**overrides: object) -> MagicMock:
    et = MagicMock()
    et.id = overrides.get("id", uuid.uuid4())
    et.account_id = overrides.get("account_id", uuid.uuid4())
    et.name = overrides.get("name", "table")
    et.display_name = overrides.get("display_name", "Table")
    et.description = overrides.get("description", None)
    et.icon = overrides.get("icon", None)
    et.is_active = overrides.get("is_active", True)
    et.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    et.updated_at = overrides.get("updated_at", None)
    return et


def _make_state_def_mock(**overrides: object) -> MagicMock:
    sd = MagicMock()
    sd.id = overrides.get("id", uuid.uuid4())
    sd.entity_type_id = overrides.get("entity_type_id", uuid.uuid4())
    sd.name = overrides.get("name", "dirty")
    sd.display_name = overrides.get("display_name", "Dirty")
    sd.color = overrides.get("color", "#FF0000")
    sd.definition_type = overrides.get("definition_type", "cleanliness")
    sd.sort_order = overrides.get("sort_order", 0)
    sd.is_default = overrides.get("is_default", False)
    sd.is_active = overrides.get("is_active", True)
    sd.criteria = overrides.get("criteria", None)
    sd.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    return sd


class TestCreateStateDefinition:

    @pytest.mark.asyncio
    async def test_creates_state_definition(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        request = CreateStateDefinitionRequest(
            name="dirty", display_name="Dirty", color="#FF0000"
        )

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_entity_type_and_name.return_value = None
            sd_repo.create.return_value = None
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                create_state_definition,
            )

            result = await create_state_definition(
                session, account_id, entity_type_id, request
            )

            assert result.name == "dirty"
            sd_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "definition_type",
        ["touch", "glove_usage", "location", "presence"],
    )
    async def test_creates_supported_workflow_definition_types(
        self, definition_type: str
    ) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        request = CreateStateDefinitionRequest(
            name=f"{definition_type}_state",
            display_name="Workflow State",
            definition_type=definition_type,
        )

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_entity_type_and_name.return_value = None
            sd_repo.create.return_value = None
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                create_state_definition,
            )

            result = await create_state_definition(
                session, account_id, entity_type_id, request
            )

            created_record = sd_repo.create.call_args[0][0]
            assert result.definition_type == definition_type
            assert created_record.definition_type == definition_type

    @pytest.mark.asyncio
    async def test_duplicate_name_raises(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        request = CreateStateDefinitionRequest(name="dirty", display_name="Dirty")

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)
        existing = _make_state_def_mock(entity_type_id=entity_type_id, name="dirty")

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_entity_type_and_name.return_value = existing
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                create_state_definition,
            )

            with pytest.raises(ValueError, match="already exists"):
                await create_state_definition(
                    session, account_id, entity_type_id, request
                )

    @pytest.mark.asyncio
    async def test_creates_with_criteria(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        request = CreateStateDefinitionRequest(
            name="clean",
            display_name="Clean",
            criteria="No dishes or trash on the surface",
        )

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_entity_type_and_name.return_value = None
            sd_repo.create.return_value = None
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                create_state_definition,
            )

            result = await create_state_definition(
                session, account_id, entity_type_id, request
            )

            assert result.criteria == "No dishes or trash on the surface"
            created_record = sd_repo.create.call_args[0][0]
            assert created_record.criteria == "No dishes or trash on the surface"

    @pytest.mark.asyncio
    async def test_default_create_clears_same_definition_type(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        request = CreateStateDefinitionRequest(
            name="empty",
            display_name="Empty",
            definition_type="occupation",
            is_default=True,
        )

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_entity_type_and_name.return_value = None
            sd_repo.create.return_value = None
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                create_state_definition,
            )

            await create_state_definition(session, account_id, entity_type_id, request)

            sd_repo.clear_default_for_entity_type.assert_awaited_once_with(
                entity_type_id, "occupation"
            )

    @pytest.mark.asyncio
    async def test_entity_type_not_found_raises(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        request = CreateStateDefinitionRequest(name="dirty", display_name="Dirty")

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls:
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = None
            mock_et_cls.return_value = et_repo

            from services.vision_entity_service._implementation import (
                create_state_definition,
            )

            with pytest.raises(ValueError, match="not found"):
                await create_state_definition(
                    session, account_id, entity_type_id, request
                )


class TestListStateDefinitions:

    @pytest.mark.asyncio
    async def test_returns_all_for_entity_type(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)
        defs = [
            _make_state_def_mock(entity_type_id=entity_type_id, name="dirty"),
            _make_state_def_mock(entity_type_id=entity_type_id, name="clean"),
        ]

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.list_by_entity_type.return_value = defs
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                list_state_definitions,
            )

            result = await list_state_definitions(session, account_id, entity_type_id)

            assert result.total == 2
            assert len(result.items) == 2

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.list_by_entity_type.return_value = []
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                list_state_definitions,
            )

            result = await list_state_definitions(session, account_id, entity_type_id)

            assert result.total == 0
            assert result.items == []


class TestUpdateStateDefinition:

    @pytest.mark.asyncio
    async def test_updates_fields(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)
        state_def = _make_state_def_mock(id=state_def_id, entity_type_id=entity_type_id)
        updated = _make_state_def_mock(
            id=state_def_id,
            entity_type_id=entity_type_id,
            display_name="Very Dirty",
        )

        request = UpdateStateDefinitionRequest(display_name="Very Dirty")

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = state_def
            sd_repo.update.return_value = updated
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                update_state_definition,
            )

            result = await update_state_definition(
                session, account_id, entity_type_id, state_def_id, request
            )

            assert result.display_name == "Very Dirty"
            sd_repo.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rename_checks_uniqueness(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()
        other_id = uuid.uuid4()

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)
        state_def = _make_state_def_mock(
            id=state_def_id, entity_type_id=entity_type_id, name="dirty"
        )
        existing_other = _make_state_def_mock(
            id=other_id, entity_type_id=entity_type_id, name="clean"
        )

        request = UpdateStateDefinitionRequest(name="clean")

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = state_def
            sd_repo.get_by_entity_type_and_name.return_value = existing_other
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                update_state_definition,
            )

            with pytest.raises(ValueError, match="already exists"):
                await update_state_definition(
                    session, account_id, entity_type_id, state_def_id, request
                )

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)
        request = UpdateStateDefinitionRequest(display_name="X")

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = None
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                update_state_definition,
            )

            with pytest.raises(ValueError, match="not found"):
                await update_state_definition(
                    session, account_id, entity_type_id, state_def_id, request
                )

    @pytest.mark.asyncio
    async def test_updates_all_optional_fields(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)
        state_def = _make_state_def_mock(id=state_def_id, entity_type_id=entity_type_id)
        updated = _make_state_def_mock(
            id=state_def_id,
            entity_type_id=entity_type_id,
            name="new_name",
            color="#0000FF",
            sort_order=5,
            is_default=True,
        )

        request = UpdateStateDefinitionRequest(
            name="new_name", color="#0000FF", sort_order=5, is_default=True
        )

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = state_def
            sd_repo.get_by_entity_type_and_name.return_value = None
            sd_repo.update.return_value = updated
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                update_state_definition,
            )

            result = await update_state_definition(
                session, account_id, entity_type_id, state_def_id, request
            )

            assert result.name == "new_name"
            assert result.color == "#0000FF"
            assert result.sort_order == 5
            assert result.is_default is True
            sd_repo.clear_default_for_entity_type.assert_awaited_once_with(
                entity_type_id,
                "cleanliness",
                except_state_definition_id=state_def_id,
            )

    @pytest.mark.asyncio
    async def test_default_type_rename_clears_target_definition_type(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)
        state_def = _make_state_def_mock(
            id=state_def_id,
            entity_type_id=entity_type_id,
            definition_type="cleanliness",
            is_default=True,
        )
        updated = _make_state_def_mock(
            id=state_def_id,
            entity_type_id=entity_type_id,
            definition_type="hygiene",
            is_default=True,
        )

        request = UpdateStateDefinitionRequest(definition_type="hygiene")

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = state_def
            sd_repo.update.return_value = updated
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                update_state_definition,
            )

            result = await update_state_definition(
                session, account_id, entity_type_id, state_def_id, request
            )

            assert result.definition_type == "hygiene"
            sd_repo.clear_default_for_entity_type.assert_awaited_once_with(
                entity_type_id,
                "hygiene",
                except_state_definition_id=state_def_id,
            )

    @pytest.mark.asyncio
    async def test_update_returns_none_raises(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)
        state_def = _make_state_def_mock(id=state_def_id, entity_type_id=entity_type_id)

        request = UpdateStateDefinitionRequest(display_name="New")

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = state_def
            sd_repo.update.return_value = None
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                update_state_definition,
            )

            with pytest.raises(ValueError, match="not found"):
                await update_state_definition(
                    session, account_id, entity_type_id, state_def_id, request
                )

    @pytest.mark.asyncio
    async def test_updates_criteria(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)
        state_def = _make_state_def_mock(
            id=state_def_id, entity_type_id=entity_type_id, criteria="Old criteria"
        )
        updated = _make_state_def_mock(
            id=state_def_id,
            entity_type_id=entity_type_id,
            criteria="Surface is visibly soiled",
        )

        request = UpdateStateDefinitionRequest(criteria="Surface is visibly soiled")

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = state_def
            sd_repo.update.return_value = updated
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                update_state_definition,
            )

            result = await update_state_definition(
                session, account_id, entity_type_id, state_def_id, request
            )

            assert result.criteria == "Surface is visibly soiled"
            sd_repo.update.assert_awaited_once_with(
                state_def_id, criteria="Surface is visibly soiled"
            )

    @pytest.mark.asyncio
    async def test_clears_criteria_to_none(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)
        state_def = _make_state_def_mock(
            id=state_def_id,
            entity_type_id=entity_type_id,
            criteria="Some existing criteria",
        )
        updated = _make_state_def_mock(
            id=state_def_id, entity_type_id=entity_type_id, criteria=None
        )

        request = UpdateStateDefinitionRequest(criteria=None)

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = state_def
            sd_repo.update.return_value = updated
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                update_state_definition,
            )

            result = await update_state_definition(
                session, account_id, entity_type_id, state_def_id, request
            )

            assert result.criteria is None
            sd_repo.update.assert_awaited_once_with(state_def_id, criteria=None)

    @pytest.mark.asyncio
    async def test_no_changes_returns_existing(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)
        state_def = _make_state_def_mock(id=state_def_id, entity_type_id=entity_type_id)

        request = UpdateStateDefinitionRequest()

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = state_def
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                update_state_definition,
            )

            result = await update_state_definition(
                session, account_id, entity_type_id, state_def_id, request
            )

            assert result.id == state_def_id
            sd_repo.update.assert_not_awaited()


class TestDeleteStateDefinition:

    @pytest.mark.asyncio
    async def test_deletes_state_definition(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)
        state_def = _make_state_def_mock(id=state_def_id, entity_type_id=entity_type_id)

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = state_def
            sd_repo.delete_if_unused.return_value = True
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                delete_state_definition,
            )

            result = await delete_state_definition(
                session, account_id, entity_type_id, state_def_id
            )

            assert result is True
            sd_repo.delete_if_unused.assert_awaited_once_with(state_def_id)

    @pytest.mark.asyncio
    async def test_in_use_raises(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)
        state_def = _make_state_def_mock(id=state_def_id, entity_type_id=entity_type_id)

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = state_def
            sd_repo.delete_if_unused.return_value = False
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                delete_state_definition,
            )

            with pytest.raises(ValueError, match="Cannot delete"):
                await delete_state_definition(
                    session, account_id, entity_type_id, state_def_id
                )

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = None
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                delete_state_definition,
            )

            with pytest.raises(ValueError, match="not found"):
                await delete_state_definition(
                    session, account_id, entity_type_id, state_def_id
                )

    @pytest.mark.asyncio
    async def test_wrong_entity_type_raises(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        other_entity_type_id = uuid.uuid4()
        state_def_id = uuid.uuid4()

        et_mock = _make_entity_type_mock(id=entity_type_id, account_id=account_id)
        state_def = _make_state_def_mock(
            id=state_def_id, entity_type_id=other_entity_type_id
        )

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_et_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_sd_cls,
        ):
            et_repo = AsyncMock()
            et_repo.get_by_id.return_value = et_mock
            mock_et_cls.return_value = et_repo

            sd_repo = AsyncMock()
            sd_repo.get_by_id.return_value = state_def
            mock_sd_cls.return_value = sd_repo

            from services.vision_entity_service._implementation import (
                delete_state_definition,
            )

            with pytest.raises(ValueError, match="not found"):
                await delete_state_definition(
                    session, account_id, entity_type_id, state_def_id
                )
