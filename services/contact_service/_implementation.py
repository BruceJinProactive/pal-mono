"""Contact service implementation.

Coordinates ``ContactRepository`` and ``ProjectContactRepository`` so that
callers never need to manage both repos directly.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.contact import ContactRepository
from db.pal_repository.data_classes.contact import ContactData
from db.pal_repository.data_classes.project_contact import ProjectContactData
from db.pal_repository.data_classes.routine_execution import UNSET
from db.pal_repository.project_contact import ProjectContactRepository


async def get_by_id(session: AsyncSession, contact_id: uuid.UUID) -> ContactData | None:
    """Retrieve a single contact by ID."""
    repo = ContactRepository(session)
    return await repo.get_by_id(contact_id)


async def list_by_project(
    session: AsyncSession, project_id: uuid.UUID
) -> list[ContactData]:
    """List all contacts linked to a project.

    Joins ``project_contacts`` → ``contacts`` in two queries.
    """
    pc_repo = ProjectContactRepository(session)
    contact_ids = await pc_repo.list_contact_ids_by_project(project_id)
    if not contact_ids:
        return []

    contact_repo = ContactRepository(session)
    return await contact_repo.batch_get_by_ids(contact_ids)


async def create_for_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    name: str,
    phone_number: str,
    role: str,
    email: str | None = None,
) -> ContactData:
    """Create a contact and link it to a project in one operation."""
    contact_repo = ContactRepository(session)
    created = await contact_repo.create(
        name=name,
        phone_number=phone_number,
        role=role,
        email=email,
    )

    pc_repo = ProjectContactRepository(session)
    try:
        await pc_repo.create(
            ProjectContactData(
                id=uuid.uuid4(),
                project_id=project_id,
                contact_id=created.id,
            )
        )
    except Exception:
        await contact_repo.delete(created.id)
        raise
    return created


async def update_for_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    contact_id: uuid.UUID,
    name: str | None = None,
    phone_number: str | None = None,
    role: str | None = None,
    email: str | None = None,
) -> ContactData | None:
    """Update a contact, verifying it belongs to the project first."""
    pc_repo = ProjectContactRepository(session)
    contact_ids = await pc_repo.list_contact_ids_by_project(project_id)
    if contact_id not in contact_ids:
        return None

    contact_repo = ContactRepository(session)
    return await contact_repo.update(
        contact_id=contact_id,
        name=name if name is not None else UNSET,
        email=email,
        phone_number=phone_number if phone_number is not None else UNSET,
        role=role if role is not None else UNSET,
    )


async def delete_from_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    contact_id: uuid.UUID,
) -> ContactData | None:
    """Delete the project-contact link and the contact itself."""
    pc_repo = ProjectContactRepository(session)
    deleted_link = await pc_repo.delete_by_project_and_contact(project_id, contact_id)
    if deleted_link is None:
        return None

    contact_repo = ContactRepository(session)
    return await contact_repo.delete(contact_id)
