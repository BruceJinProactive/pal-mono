"""Tests for catering_service contact CRUD operations.

Validates that service functions correctly delegate to the new-style
ProjectContactRepository (from db.pal_repository).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# TestListContacts
# ---------------------------------------------------------------------------


class TestListContacts:
    """list_contacts delegates to ProjectContactRepository + ContactRepositoryAsync."""

    @pytest.mark.asyncio
    async def test_returns_contacts(self) -> None:
        from services.catering_service._implementation import list_contacts

        session = AsyncMock()
        project_id = uuid.uuid4()
        contact_id = uuid.uuid4()
        mock_contact = MagicMock(id=contact_id)

        with (
            patch(
                "services.catering_service._implementation.ProjectContactRepository"
            ) as MockPCRepo,
            patch(
                "services.catering_service._implementation.ContactRepositoryAsync"
            ) as MockCRepo,
        ):
            MockPCRepo.return_value.list_contact_ids_by_project = AsyncMock(
                return_value=[contact_id]
            )
            MockCRepo.return_value.batch_list_contacts = AsyncMock(
                return_value=[mock_contact]
            )

            result = await list_contacts(session, project_id)

        assert result == [mock_contact]
        MockPCRepo.return_value.list_contact_ids_by_project.assert_awaited_once_with(
            project_id
        )

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_contacts(self) -> None:
        from services.catering_service._implementation import list_contacts

        session = AsyncMock()

        with patch(
            "services.catering_service._implementation.ProjectContactRepository"
        ) as MockPCRepo:
            MockPCRepo.return_value.list_contact_ids_by_project = AsyncMock(
                return_value=[]
            )

            result = await list_contacts(session, uuid.uuid4())

        assert result == []


# ---------------------------------------------------------------------------
# TestDeleteContact
# ---------------------------------------------------------------------------


class TestDeleteContact:
    """delete_contact delegates to ProjectContactRepository + ContactRepositoryAsync."""

    @pytest.mark.asyncio
    async def test_deletes_relation_then_contact(self) -> None:
        from services.catering_service._implementation import delete_contact

        session = AsyncMock()
        project_id = uuid.uuid4()
        contact_id = uuid.uuid4()
        mock_deleted = MagicMock()
        call_order: list[str] = []

        with (
            patch(
                "services.catering_service._implementation.ProjectContactRepository"
            ) as MockPCRepo,
            patch(
                "services.catering_service._implementation.ContactRepositoryAsync"
            ) as MockCRepo,
        ):

            async def _delete_relation(*a: object, **kw: object) -> None:
                call_order.append("delete_relation")

            async def _delete_contact(*a: object, **kw: object) -> MagicMock:
                call_order.append("delete_contact")
                return mock_deleted

            MockPCRepo.return_value.delete_by_project_and_contact = AsyncMock(
                side_effect=_delete_relation
            )
            MockCRepo.return_value.delete_contact = AsyncMock(
                side_effect=_delete_contact
            )

            result = await delete_contact(session, project_id, contact_id)

        assert result == mock_deleted
        MockPCRepo.return_value.delete_by_project_and_contact.assert_awaited_once_with(
            project_id, contact_id
        )
        MockCRepo.return_value.delete_contact.assert_awaited_once_with(contact_id)
        assert call_order == ["delete_relation", "delete_contact"]


# ---------------------------------------------------------------------------
# TestUpdateContact
# ---------------------------------------------------------------------------


class TestUpdateContact:
    """update_contact verifies membership via ProjectContactRepository."""

    @pytest.mark.asyncio
    async def test_returns_none_when_contact_not_linked(self) -> None:
        from services.catering_service._implementation import update_contact

        session = AsyncMock()
        project_id = uuid.uuid4()
        contact_id = uuid.uuid4()

        with patch(
            "services.catering_service._implementation.ProjectContactRepository"
        ) as MockPCRepo:
            MockPCRepo.return_value.list_contact_ids_by_project = AsyncMock(
                return_value=[]
            )

            result = await update_contact(
                session, project_id, contact_id, name="New Name"
            )

        assert result is None
