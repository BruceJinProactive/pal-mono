import uuid
from datetime import date, time
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.catering_request_repository import (
    CateringRequestRepository,
    CateringRequestRepositoryAsync,
)
from db.repositories.contact_repository import ContactRepositoryAsync
from db.repositories.project_contact_repository import ProjectContactRepositoryAsync
from db.session import SyncSessionLocal
from db.tables.catering_requests import CateringRequest, FulfillmentType, RequestStatus
from db.tables.contacts import Contact


def create_catering_request(
    project_id: uuid.UUID,
    event_date: date,
    contact_name: str,
    contact_phone_number: str,
    event_time: Optional[time] = None,
    event_address: Optional[str] = None,
    event_detail: Optional[str] = None,
    event_fulfillment: Optional[FulfillmentType] = None,
    party_size: Optional[int] = None,
) -> CateringRequest:
    """
    Create a new catering request.

    Args:
        session: Database session
        project_id: ID of the project this request belongs to
        event_date: Date of the catering event
        contact_name: Name of the contact person
        contact_phone_number: Phone number of the contact person
        event_time: Time of the event (optional)
        event_address: Address where the event will take place (optional)
        event_detail: Additional details about the event (optional)
        event_fulfillment: How the catering will be fulfilled (optional)
        party_size: Number of people expected (optional)

    Returns:
        CateringRequest: The created catering request
    """
    session = SyncSessionLocal()
    try:
        catering_request = CateringRequest(
            project_id=project_id,
            event_date=event_date,
            event_time=event_time,
            event_address=event_address,
            event_detail=event_detail,
            event_fulfillment=event_fulfillment,
            contact_name=contact_name,
            contact_phone_number=contact_phone_number,
            party_size=party_size,
            contact_id=None,
            status=RequestStatus.PENDING,
        )

        catering_request_repo = CateringRequestRepository(session)
        return catering_request_repo.create_catering_request(catering_request)
    finally:
        session.close()


async def create_contact(
    session: AsyncSession,
    project_id: uuid.UUID,
    name: str,
    phone_number: str,
    role: str,
    email: Optional[str] = None,
) -> Contact:
    """
    Create a new contact and associate it with a project asynchronously.

    Args:
        session: Async database session
        project_id: ID of the project to associate the contact with
        name: Contact's name
        phone_number: Contact's phone number
        role: Contact's role
        email: Contact's email address (optional)

    Returns:
        Contact: The created contact
    """
    contact = Contact(
        name=name,
        phone_number=phone_number,
        role=role,
        email=email,
    )

    contact_repo = ContactRepositoryAsync(session)
    created_contact = await contact_repo.create_contact(contact)

    # Create the project-contact relation
    project_contact_repo = ProjectContactRepositoryAsync(session)
    await project_contact_repo.create_project_contact_relation(
        project_id, created_contact.id
    )

    return created_contact


async def list_contacts(
    session: AsyncSession,
    project_id: uuid.UUID,
) -> List[Contact]:
    """
    List all contacts for a specific project asynchronously.

    Args:
        session: Async database session
        project_id: ID of the project to list contacts for

    Returns:
        List[Contact]: List of contacts associated with the project
    """
    # Get contact IDs for the project
    project_contact_repo = ProjectContactRepositoryAsync(session)
    contact_ids = await project_contact_repo.list_contacts_by_project(project_id)

    if not contact_ids:
        return []

    # Get the actual contact objects
    contact_repo = ContactRepositoryAsync(session)
    contacts = await contact_repo.batch_list_contacts(contact_ids)

    return contacts


async def delete_contact(
    session: AsyncSession,
    project_id: uuid.UUID,
    contact_id: uuid.UUID,
) -> Contact | None:
    """
    Delete a contact and its project relation asynchronously.

    Args:
        session: Async database session
        project_id: ID of the project
        contact_id: ID of the contact to delete

    Returns:
        Contact: The deleted contact, or None if not found
    """
    # First delete the project-contact relation
    project_contact_repo = ProjectContactRepositoryAsync(session)
    await project_contact_repo.delete_project_contact_relation(project_id, contact_id)

    # Then delete the contact itself
    contact_repo = ContactRepositoryAsync(session)
    deleted_contact = await contact_repo.delete_contact(contact_id)

    return deleted_contact


async def update_catering_request(
    session: AsyncSession,
    catering_request_id: uuid.UUID,
    event_date: Optional[date] = None,
    contact_name: Optional[str] = None,
    contact_phone_number: Optional[str] = None,
    event_time: Optional[time] = None,
    event_address: Optional[str] = None,
    event_detail: Optional[str] = None,
    event_fulfillment: Optional[FulfillmentType] = None,
    party_size: Optional[int] = None,
    status: Optional[RequestStatus] = None,
) -> CateringRequest:
    """
    Update an existing catering request asynchronously.

    Args:
        session: Async database session
        catering_request_id: ID of the catering request to update
        event_date: New event date (optional)
        contact_name: New contact name (optional)
        contact_phone_number: New contact phone number (optional)
        event_time: New event time (optional)
        event_address: New event address (optional)
        event_detail: New event details (optional)
        event_fulfillment: New fulfillment type (optional)
        party_size: New party size (optional)
        status: New status (optional)

    Returns:
        CateringRequest: The updated catering request
    """
    # Create an updated catering request object with only the provided fields
    updated_catering_request = CateringRequest()

    # Map of parameter names to values, excluding None values
    updates = {
        "event_date": event_date,
        "contact_name": contact_name,
        "contact_phone_number": contact_phone_number,
        "event_time": event_time,
        "event_address": event_address,
        "event_detail": event_detail,
        "event_fulfillment": event_fulfillment,
        "party_size": party_size,
        "status": status,
    }

    # Set only non-None values
    for field, value in updates.items():
        if value is not None:
            setattr(updated_catering_request, field, value)

    catering_request_repo = CateringRequestRepositoryAsync(session)
    return await catering_request_repo.update_catering_request(
        catering_request_id, updated_catering_request
    )
