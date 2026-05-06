"""Tests for vision_entity_service entity type CRUD operations."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas.operations.vision_entity import (
    CreateEntityTypeRequest,
    UpdateEntityTypeRequest,
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


class TestCreateEntityType:

    @pytest.mark.asyncio
    async def test_creates_entity_type(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        request = CreateEntityTypeRequest(
            name="table",
            display_name="Table",
            description="Dining tables",
            icon="🍽️",
        )

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_account_and_name.return_value = None
            repo.create.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import (
                create_entity_type,
            )

            result = await create_entity_type(session, account_id, request)

            assert result.name == "table"
            assert result.display_name == "Table"
            repo.get_by_account_and_name.assert_awaited_once_with(account_id, "table")
            repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_name_raises(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        request = CreateEntityTypeRequest(name="table", display_name="Table")

        existing = _make_entity_type_mock(account_id=account_id, name="table")

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_account_and_name.return_value = existing
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import (
                create_entity_type,
            )

            with pytest.raises(ValueError, match="already exists"):
                await create_entity_type(session, account_id, request)


class TestGetEntityType:

    @pytest.mark.asyncio
    async def test_returns_entity_type(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        entity_type = _make_entity_type_mock(
            id=entity_type_id, account_id=account_id, name="table"
        )

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity_type
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import get_entity_type

            result = await get_entity_type(session, account_id, entity_type_id)

            assert result.id == entity_type_id
            assert result.name == "table"
            repo.get_by_id.assert_awaited_once_with(entity_type_id)

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import get_entity_type

            with pytest.raises(ValueError, match="not found"):
                await get_entity_type(session, account_id, entity_type_id)

    @pytest.mark.asyncio
    async def test_wrong_account_raises(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        other_account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        entity_type = _make_entity_type_mock(
            id=entity_type_id, account_id=other_account_id
        )

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity_type
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import get_entity_type

            with pytest.raises(ValueError, match="not found"):
                await get_entity_type(session, account_id, entity_type_id)


class TestListEntityTypes:

    @pytest.mark.asyncio
    async def test_returns_all_for_account(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        types = [
            _make_entity_type_mock(account_id=account_id, name="table"),
            _make_entity_type_mock(account_id=account_id, name="employee"),
        ]

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_account.return_value = types
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import list_entity_types

            result = await list_entity_types(session, account_id)

            assert result.total == 2
            assert len(result.items) == 2
            repo.get_by_account.assert_awaited_once_with(account_id, is_active=None)

    @pytest.mark.asyncio
    async def test_filters_by_is_active(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_account.return_value = []
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import list_entity_types

            await list_entity_types(session, account_id, is_active=True)

            repo.get_by_account.assert_awaited_once_with(account_id, is_active=True)

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_account.return_value = []
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import list_entity_types

            result = await list_entity_types(session, account_id)

            assert result.total == 0
            assert result.items == []


class TestUpdateEntityType:

    @pytest.mark.asyncio
    async def test_updates_fields(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        entity_type = _make_entity_type_mock(
            id=entity_type_id, account_id=account_id, name="table"
        )
        updated = _make_entity_type_mock(
            id=entity_type_id,
            account_id=account_id,
            name="table",
            display_name="Dining Table",
        )

        request = UpdateEntityTypeRequest(display_name="Dining Table")

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity_type
            repo.update.return_value = updated
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import (
                update_entity_type,
            )

            result = await update_entity_type(
                session, account_id, entity_type_id, request
            )

            assert result.display_name == "Dining Table"
            repo.update.assert_awaited_once_with(
                entity_type_id, display_name="Dining Table"
            )

    @pytest.mark.asyncio
    async def test_rename_checks_uniqueness(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        other_id = uuid.uuid4()
        entity_type = _make_entity_type_mock(
            id=entity_type_id, account_id=account_id, name="table"
        )
        existing_other = _make_entity_type_mock(
            id=other_id, account_id=account_id, name="employee"
        )

        request = UpdateEntityTypeRequest(name="employee")

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity_type
            repo.get_by_account_and_name.return_value = existing_other
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import (
                update_entity_type,
            )

            with pytest.raises(ValueError, match="already exists"):
                await update_entity_type(session, account_id, entity_type_id, request)

    @pytest.mark.asyncio
    async def test_rename_to_same_name_allowed(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        entity_type = _make_entity_type_mock(
            id=entity_type_id, account_id=account_id, name="table"
        )

        request = UpdateEntityTypeRequest(name="table")

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity_type
            repo.get_by_account_and_name.return_value = entity_type
            repo.update.return_value = entity_type
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import (
                update_entity_type,
            )

            result = await update_entity_type(
                session, account_id, entity_type_id, request
            )

            assert result.name == "table"
            repo.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        request = UpdateEntityTypeRequest(display_name="New Name")

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import (
                update_entity_type,
            )

            with pytest.raises(ValueError, match="not found"):
                await update_entity_type(session, account_id, entity_type_id, request)

    @pytest.mark.asyncio
    async def test_updates_all_optional_fields(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        entity_type = _make_entity_type_mock(id=entity_type_id, account_id=account_id)
        updated = _make_entity_type_mock(
            id=entity_type_id,
            account_id=account_id,
            description="desc",
            icon="🍽️",
            is_active=False,
        )

        request = UpdateEntityTypeRequest(description="desc", icon="🍽️", is_active=False)

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity_type
            repo.update.return_value = updated
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import (
                update_entity_type,
            )

            result = await update_entity_type(
                session, account_id, entity_type_id, request
            )

            assert result.description == "desc"
            assert result.icon == "🍽️"
            assert result.is_active is False
            repo.update.assert_awaited_once_with(
                entity_type_id,
                description="desc",
                icon="🍽️",
                is_active=False,
            )

    @pytest.mark.asyncio
    async def test_update_returns_none_raises(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        entity_type = _make_entity_type_mock(id=entity_type_id, account_id=account_id)

        request = UpdateEntityTypeRequest(display_name="New")

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity_type
            repo.update.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import (
                update_entity_type,
            )

            with pytest.raises(ValueError, match="not found"):
                await update_entity_type(session, account_id, entity_type_id, request)

    @pytest.mark.asyncio
    async def test_no_changes_returns_existing(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        entity_type = _make_entity_type_mock(id=entity_type_id, account_id=account_id)

        request = UpdateEntityTypeRequest()

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity_type
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import (
                update_entity_type,
            )

            result = await update_entity_type(
                session, account_id, entity_type_id, request
            )

            assert result.id == entity_type_id
            repo.update.assert_not_awaited()


class TestDeleteEntityType:

    @pytest.mark.asyncio
    async def test_deletes_entity_type(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        entity_type = _make_entity_type_mock(id=entity_type_id, account_id=account_id)

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls,
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_state_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id.return_value = entity_type
            repo.delete.return_value = True
            mock_repo_cls.return_value = repo

            entity_repo = AsyncMock()
            entity_repo.list_by_entity_type.return_value = []
            mock_entity_cls.return_value = entity_repo

            mapping_repo = AsyncMock()
            mock_mapping_cls.return_value = mapping_repo

            state_repo = AsyncMock()
            state_repo.delete_by_entity_type.return_value = 0
            mock_state_cls.return_value = state_repo

            from services.vision_entity_service._implementation import (
                delete_entity_type,
            )

            result = await delete_entity_type(session, account_id, entity_type_id)

            assert result is True
            repo.delete.assert_awaited_once_with(entity_type_id)
            entity_repo.list_by_entity_type.assert_called_once_with(entity_type_id)
            state_repo.delete_by_entity_type.assert_called_once_with(entity_type_id)

    @pytest.mark.asyncio
    async def test_deletes_entity_type_with_existing_entities_and_states(
        self,
    ) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        entity_id = uuid.uuid4()
        entity_type = _make_entity_type_mock(id=entity_type_id, account_id=account_id)

        entity_mock = MagicMock()
        entity_mock.id = entity_id

        with (
            patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls,
            patch(f"{MODULE}.VisionEntityRepository") as mock_entity_cls,
            patch(f"{MODULE}.VisionCameraEntityRepository") as mock_mapping_cls,
            patch(f"{MODULE}.VisionEntityStateDefinitionRepository") as mock_state_cls,
        ):
            repo = AsyncMock()
            repo.get_by_id.return_value = entity_type
            repo.delete.return_value = True
            mock_repo_cls.return_value = repo

            entity_repo = AsyncMock()
            entity_repo.list_by_entity_type.return_value = [entity_mock]
            entity_repo.delete.return_value = True
            mock_entity_cls.return_value = entity_repo

            mapping_repo = AsyncMock()
            mapping_repo.delete_by_entity.return_value = 1
            mock_mapping_cls.return_value = mapping_repo

            state_repo = AsyncMock()
            state_repo.delete_by_entity_type.return_value = 2
            mock_state_cls.return_value = state_repo

            from services.vision_entity_service._implementation import (
                delete_entity_type,
            )

            result = await delete_entity_type(session, account_id, entity_type_id)

            assert result is True
            mapping_repo.delete_by_entity.assert_called_once_with(entity_id)
            entity_repo.delete.assert_called_once_with(entity_id)
            state_repo.delete_by_entity_type.assert_called_once_with(entity_type_id)

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = None
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import (
                delete_entity_type,
            )

            with pytest.raises(ValueError, match="not found"):
                await delete_entity_type(session, account_id, entity_type_id)

    @pytest.mark.asyncio
    async def test_wrong_account_raises(self) -> None:
        session = AsyncMock()
        account_id = uuid.uuid4()
        other_account_id = uuid.uuid4()
        entity_type_id = uuid.uuid4()
        entity_type = _make_entity_type_mock(
            id=entity_type_id, account_id=other_account_id
        )

        with patch(f"{MODULE}.VisionEntityTypeRepository") as mock_repo_cls:
            repo = AsyncMock()
            repo.get_by_id.return_value = entity_type
            mock_repo_cls.return_value = repo

            from services.vision_entity_service._implementation import (
                delete_entity_type,
            )

            with pytest.raises(ValueError, match="not found"):
                await delete_entity_type(session, account_id, entity_type_id)
