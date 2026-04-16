"""Tests for services.contact_service._implementation."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.pal_repository.data_classes.contact import ContactData

IMPL = "services.contact_service._implementation"


class TestGetById:
    @pytest.mark.asyncio
    async def test_delegates_to_repo(self) -> None:
        from services.contact_service._implementation import get_by_id

        session = AsyncMock()
        cid = uuid.uuid4()
        mock_data = MagicMock(spec=ContactData)

        with patch(f"{IMPL}.ContactRepository") as MockRepo:
            MockRepo.return_value.get_by_id = AsyncMock(return_value=mock_data)
            result = await get_by_id(session, cid)

        assert result is mock_data
        MockRepo.return_value.get_by_id.assert_awaited_once_with(cid)


class TestListByProject:
    @pytest.mark.asyncio
    async def test_returns_contacts(self) -> None:
        from services.contact_service._implementation import list_by_project

        session = AsyncMock()
        pid = uuid.uuid4()
        cid = uuid.uuid4()
        mock_contact = MagicMock(spec=ContactData)

        with (
            patch(f"{IMPL}.ProjectContactRepository") as MockPCRepo,
            patch(f"{IMPL}.ContactRepository") as MockCRepo,
        ):
            MockPCRepo.return_value.list_contact_ids_by_project = AsyncMock(
                return_value=[cid]
            )
            MockCRepo.return_value.batch_get_by_ids = AsyncMock(
                return_value=[mock_contact]
            )
            result = await list_by_project(session, pid)

        assert result == [mock_contact]

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_links(self) -> None:
        from services.contact_service._implementation import list_by_project

        session = AsyncMock()

        with patch(f"{IMPL}.ProjectContactRepository") as MockPCRepo:
            MockPCRepo.return_value.list_contact_ids_by_project = AsyncMock(
                return_value=[]
            )
            result = await list_by_project(session, uuid.uuid4())

        assert result == []


class TestCreateForProject:
    @pytest.mark.asyncio
    async def test_creates_contact_and_link(self) -> None:
        from services.contact_service._implementation import create_for_project

        session = AsyncMock()
        pid = uuid.uuid4()
        mock_created = MagicMock(spec=ContactData, id=uuid.uuid4())

        with (
            patch(f"{IMPL}.ContactRepository") as MockCRepo,
            patch(f"{IMPL}.ProjectContactRepository") as MockPCRepo,
        ):
            MockCRepo.return_value.create = AsyncMock(return_value=mock_created)
            MockPCRepo.return_value.create = AsyncMock()

            result = await create_for_project(
                session, pid, "John", "+1234567890", "manager"
            )

        assert result is mock_created
        MockCRepo.return_value.create.assert_awaited_once()
        MockPCRepo.return_value.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleans_up_on_link_failure(self) -> None:
        from services.contact_service._implementation import create_for_project

        session = AsyncMock()
        pid = uuid.uuid4()
        mock_created = MagicMock(spec=ContactData, id=uuid.uuid4())

        with (
            patch(f"{IMPL}.ContactRepository") as MockCRepo,
            patch(f"{IMPL}.ProjectContactRepository") as MockPCRepo,
        ):
            MockCRepo.return_value.create = AsyncMock(return_value=mock_created)
            MockCRepo.return_value.delete = AsyncMock()
            MockPCRepo.return_value.create = AsyncMock(
                side_effect=RuntimeError("link failed")
            )

            with pytest.raises(RuntimeError, match="link failed"):
                await create_for_project(session, pid, "John", "+1234567890", "manager")

        MockCRepo.return_value.delete.assert_awaited_once_with(mock_created.id)


class TestUpdateForProject:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_linked(self) -> None:
        from services.contact_service._implementation import update_for_project

        session = AsyncMock()

        with patch(f"{IMPL}.ProjectContactRepository") as MockPCRepo:
            MockPCRepo.return_value.list_contact_ids_by_project = AsyncMock(
                return_value=[]
            )
            result = await update_for_project(
                session, uuid.uuid4(), uuid.uuid4(), name="X"
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_updates_when_linked(self) -> None:
        from services.contact_service._implementation import update_for_project

        session = AsyncMock()
        pid = uuid.uuid4()
        cid = uuid.uuid4()
        mock_updated = MagicMock(spec=ContactData)

        with (
            patch(f"{IMPL}.ProjectContactRepository") as MockPCRepo,
            patch(f"{IMPL}.ContactRepository") as MockCRepo,
        ):
            MockPCRepo.return_value.list_contact_ids_by_project = AsyncMock(
                return_value=[cid]
            )
            MockCRepo.return_value.update = AsyncMock(return_value=mock_updated)

            result = await update_for_project(session, pid, cid, name="New")

        assert result is mock_updated


class TestDeleteFromProject:
    @pytest.mark.asyncio
    async def test_returns_none_when_link_not_found(self) -> None:
        from services.contact_service._implementation import delete_from_project

        session = AsyncMock()

        with patch(f"{IMPL}.ProjectContactRepository") as MockPCRepo:
            MockPCRepo.return_value.delete_by_project_and_contact = AsyncMock(
                return_value=None
            )
            result = await delete_from_project(session, uuid.uuid4(), uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_deletes_link_then_contact(self) -> None:
        from services.contact_service._implementation import delete_from_project

        session = AsyncMock()
        pid = uuid.uuid4()
        cid = uuid.uuid4()
        mock_deleted = MagicMock(spec=ContactData)

        order: list[str] = []

        async def _delete_link(*args: object, **kwargs: object) -> MagicMock:
            order.append("delete_link")
            return MagicMock()

        async def _delete_contact(*args: object, **kwargs: object) -> MagicMock:
            order.append("delete_contact")
            return mock_deleted

        with (
            patch(f"{IMPL}.ProjectContactRepository") as MockPCRepo,
            patch(f"{IMPL}.ContactRepository") as MockCRepo,
        ):
            MockPCRepo.return_value.delete_by_project_and_contact = _delete_link
            MockCRepo.return_value.delete = _delete_contact

            result = await delete_from_project(session, pid, cid)

        assert result is mock_deleted
        assert order == ["delete_link", "delete_contact"]
