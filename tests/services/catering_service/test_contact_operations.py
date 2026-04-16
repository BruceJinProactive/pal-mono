"""Tests for catering_service contact CRUD operations.

Validates that service functions correctly delegate to contact_service.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# TestListContacts
# ---------------------------------------------------------------------------


class TestListContacts:
    """list_contacts delegates to contact_service.list_by_project."""

    @pytest.mark.asyncio
    async def test_returns_contacts(self) -> None:
        from services.catering_service._implementation import list_contacts

        session = AsyncMock()
        project_id = uuid.uuid4()
        mock_contact = MagicMock()

        with patch(
            "services.catering_service._implementation.contact_service.list_by_project",
            new_callable=AsyncMock,
            return_value=[mock_contact],
        ) as mock_list:
            result = await list_contacts(session, project_id)

        assert result == [mock_contact]
        mock_list.assert_awaited_once_with(session, project_id)

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_contacts(self) -> None:
        from services.catering_service._implementation import list_contacts

        session = AsyncMock()

        with patch(
            "services.catering_service._implementation.contact_service.list_by_project",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await list_contacts(session, uuid.uuid4())

        assert result == []


# ---------------------------------------------------------------------------
# TestDeleteContact
# ---------------------------------------------------------------------------


class TestDeleteContact:
    """delete_contact delegates to contact_service.delete_from_project."""

    @pytest.mark.asyncio
    async def test_delegates_to_contact_service(self) -> None:
        from services.catering_service._implementation import delete_contact

        session = AsyncMock()
        project_id = uuid.uuid4()
        contact_id = uuid.uuid4()
        mock_deleted = MagicMock()

        with patch(
            "services.catering_service._implementation.contact_service.delete_from_project",
            new_callable=AsyncMock,
            return_value=mock_deleted,
        ) as mock_delete:
            result = await delete_contact(session, project_id, contact_id)

        assert result == mock_deleted
        mock_delete.assert_awaited_once_with(session, project_id, contact_id)


# ---------------------------------------------------------------------------
# TestUpdateContact
# ---------------------------------------------------------------------------


class TestUpdateContact:
    """update_contact delegates to contact_service.update_for_project."""

    @pytest.mark.asyncio
    async def test_returns_none_when_contact_not_linked(self) -> None:
        from services.catering_service._implementation import update_contact

        session = AsyncMock()
        project_id = uuid.uuid4()
        contact_id = uuid.uuid4()

        with patch(
            "services.catering_service._implementation.contact_service.update_for_project",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await update_contact(
                session, project_id, contact_id, name="New Name"
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_updated_contact(self) -> None:
        from services.catering_service._implementation import update_contact

        session = AsyncMock()
        project_id = uuid.uuid4()
        contact_id = uuid.uuid4()
        mock_updated = MagicMock()

        with patch(
            "services.catering_service._implementation.contact_service.update_for_project",
            new_callable=AsyncMock,
            return_value=mock_updated,
        ) as mock_update:
            result = await update_contact(
                session, project_id, contact_id, name="New Name"
            )

        assert result == mock_updated
        mock_update.assert_awaited_once_with(
            session,
            project_id=project_id,
            contact_id=contact_id,
            name="New Name",
            phone_number=None,
            role=None,
            email=None,
        )


# ---------------------------------------------------------------------------
# TestCreateContact
# ---------------------------------------------------------------------------


class TestCreateContact:
    """create_contact delegates to contact_service.create_for_project."""

    @pytest.mark.asyncio
    async def test_delegates_to_contact_service(self) -> None:
        from services.catering_service._implementation import create_contact

        session = AsyncMock()
        project_id = uuid.uuid4()
        mock_created = MagicMock()

        with patch(
            "services.catering_service._implementation.contact_service.create_for_project",
            new_callable=AsyncMock,
            return_value=mock_created,
        ) as mock_create:
            result = await create_contact(
                session, project_id, "John", "+1234567890", "manager"
            )

        assert result == mock_created
        mock_create.assert_awaited_once_with(
            session,
            project_id=project_id,
            name="John",
            phone_number="+1234567890",
            role="manager",
            email=None,
        )
