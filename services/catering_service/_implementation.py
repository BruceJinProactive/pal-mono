import re
import uuid
from datetime import date, time
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.catering.catering import Contact as ContactSchema
from api.schemas.chat.message import AuthorType, Broker, Extras
from api.schemas.chat.message import Message as RelayMessage
from api.schemas.chat.message import Metadata, TextObject, Type
from db.repositories.catering_request_repository import (
    CateringRequestRepository,
    CateringRequestRepositoryAsync,
)
from db.repositories.contact_repository import ContactRepositoryAsync
from db.repositories.project_contact_repository import ProjectContactRepositoryAsync
from db.session import SyncSessionLocal
from db.tables.catering_requests import CateringRequest, FulfillmentType, RequestStatus
from db.tables.contacts import Contact
from db.tables.types import Channel
from services.catering_service._eventbridge import publish_catering_event
from services.relay_service import send_message
from utils.log import logger


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
    idempotency_key: Optional[str] = None,
) -> CateringRequest:
    """
    Create or update a catering request with idempotency support.

    Args:
        project_id: ID of the project this request belongs to
        event_date: Date of the catering event
        contact_name: Name of the contact person
        contact_phone_number: Phone number of the contact person
        event_time: Time of the event (optional)
        event_address: Address where the event will take place (optional)
        event_detail: Additional details about the event (optional)
        event_fulfillment: How the catering will be fulfilled (optional)
        party_size: Number of people expected (optional)
        idempotency_key: Key to prevent duplicate requests (optional, will generate if not provided)

    Returns:
        CateringRequest: The created or updated catering request
    """
    session = SyncSessionLocal()
    try:
        catering_request_repo = CateringRequestRepository(session)

        # Generate idempotency key if not provided
        if idempotency_key is None:
            idempotency_key = str(uuid.uuid4())

        # Check if request already exists with this idempotency key
        existing_request = (
            catering_request_repo.get_catering_request_by_idempotency_key(
                idempotency_key
            )
        )

        if existing_request:
            # If request exists, check if there are any changes and update if needed
            updates_needed = False
            update_fields = {}

            # Compare fields and track changes
            field_mappings = {
                "event_date": event_date,
                "event_time": event_time,
                "event_address": event_address,
                "event_detail": event_detail,
                "event_fulfillment": event_fulfillment,
                "contact_name": contact_name,
                "contact_phone_number": contact_phone_number,
                "party_size": party_size,
            }

            for field, new_value in field_mappings.items():
                if (
                    new_value is not None
                    and getattr(existing_request, field) != new_value
                ):
                    update_fields[field] = new_value
                    updates_needed = True

            if updates_needed:
                # Create update object with only changed fields
                updated_catering_request = CateringRequest()
                for field, value in update_fields.items():
                    setattr(updated_catering_request, field, value)

                return catering_request_repo.update_catering_request(
                    existing_request.id, updated_catering_request
                )
            else:
                # No changes needed, return existing request
                return existing_request
        else:
            # Create new request
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
                idempotency_key=idempotency_key,
            )

            created_request = catering_request_repo.create_catering_request(
                catering_request
            )

            # Publish event for new catering request creation to EventBridge
            event_published = publish_catering_event(
                catering_request_id=str(created_request.id),
                event_type="catering_request_created",
                idempotency_key=idempotency_key,
            )
            if not event_published:
                logger.warning(
                    f"Failed to publish catering_request_created event for request {created_request.id}"
                )

            return created_request
    finally:
        session.close()


def list_catering_requests_by_project_id(
    project_id: uuid.UUID,
) -> List[CateringRequest]:
    """
    List all catering requests for a specific project.

    Args:
        project_id: ID of the project to list catering requests for

    Returns:
        List[CateringRequest]: List of catering requests for the project
    """
    session = SyncSessionLocal()
    try:
        catering_request_repo = CateringRequestRepository(session)
        return catering_request_repo.list_catering_requests_by_project_id(project_id)
    finally:
        session.close()


async def create_contact(
    session: AsyncSession,
    project_id: uuid.UUID,
    name: str,
    phone_number: str,
    role: str,
    email: Optional[str] = None,
) -> ContactSchema:
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
        ContactSchema: The created contact as a Pydantic model
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
) -> List[ContactSchema]:
    """
    List all contacts for a specific project asynchronously.

    Args:
        session: Async database session
        project_id: ID of the project to list contacts for

    Returns:
        List[ContactSchema]: List of contact Pydantic models associated with the project
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


async def _find_and_assign_catering_manager(
    session: AsyncSession,
    catering_request,
    catering_request_id: str,
) -> ContactSchema | None:
    """
    Find a catering manager for the request and assign it if needed.

    Args:
        session: Database session
        catering_request: The catering request object
        catering_request_id: ID of the catering request (for logging)

    Returns:
        ContactSchema | None: The catering manager contact if found, None otherwise
    """
    contact_repo = ContactRepositoryAsync(session)

    # Try to get the direct contact first
    if catering_request.contact_id:
        catering_manager = await contact_repo.get_contact_by_id(
            catering_request.contact_id
        )
        if catering_manager:
            logger.debug(
                f"[catering] Using existing contact {catering_manager.name} (ID: {catering_manager.id})"
            )
            return catering_manager

    project_contact_repo = ProjectContactRepositoryAsync(session)

    contact_ids = await project_contact_repo.list_contacts_by_project(
        catering_request.project_id
    )

    if not contact_ids:
        logger.warning(
            f"[catering] No contacts found for project {catering_request.project_id}"
        )
        return None

    contacts = await contact_repo.batch_list_contacts(contact_ids)

    if not contacts:
        logger.warning(
            f"[catering] No valid contacts found for project {catering_request.project_id}"
        )
        return None

    # Find the first catering manager
    catering_manager = next(
        (contact for contact in contacts if contact.role.lower() == "catering_manager"),
        None,
    )

    if not catering_manager:
        logger.warning(
            f"[catering] No catering manager found for project {catering_request.project_id}"
        )
        return None

    logger.debug(f"[catering] Found catering manager: {catering_manager.name}")

    # If the catering request doesn't have a contact_id, assign this manager
    if not catering_request.contact_id:
        try:
            catering_request.contact_id = catering_manager.id
            catering_request_repo = CateringRequestRepositoryAsync(session)
            await catering_request_repo.update_catering_request(
                uuid.UUID(catering_request_id), catering_request
            )
            logger.debug(
                f"[catering] Assigned catering manager {catering_manager.name} (ID: {catering_manager.id}) to catering request {catering_request_id}"
            )
        except Exception as e:
            logger.warning(
                f"[catering] Failed to assign catering manager to request {catering_request_id}: {e}"
            )
            # Don't fail the entire process if we can't update the assignment

    return catering_manager


async def handle_catering_request_created_event(
    catering_request_id: str,
    idempotency_key: str,
    session: AsyncSession,
) -> bool:
    """
    Handle all business logic when a catering request is created.
    This includes notifications, integrations, analytics, etc.

    Args:
        catering_request_id: ID of the catering request
        idempotency_key: Idempotency key for the catering request
        session: Async database session

    Returns:
        bool: True if all actions completed successfully, False otherwise
    """

    try:
        catering_request_repo = CateringRequestRepositoryAsync(session)

        # Get the catering request details
        catering_request = await catering_request_repo.get_catering_request_by_id(
            uuid.UUID(catering_request_id)
        )

        if not catering_request:
            logger.error(f"[catering] Catering request {catering_request_id} not found")
            return False

        # Validate idempotency key matches
        if catering_request.idempotency_key != idempotency_key:
            logger.error(
                f"[catering] Idempotency key mismatch for catering request {catering_request_id}. "
                f"Expected: {catering_request.idempotency_key}, Got: {idempotency_key}"
            )
            return False

        catering_manager = await _find_and_assign_catering_manager(
            session, catering_request, catering_request_id
        )

        if not catering_manager:
            logger.error(
                f"[catering] No catering manager found for project {catering_request.project_id}"
            )
            return False

        # Format the notification message
        message = format_catering_request_message(catering_request)

        notification_success = await send_sms_notification(
            catering_manager.phone_number, message
        )
        if notification_success:
            logger.debug(
                f"[catering] Successfully sent catering request notification to {catering_manager.name}"
            )
            return True
        else:
            logger.error(
                f"[catering] Failed to send SMS to manager {catering_manager.name} at ****{catering_manager.phone_number[-4:]}"
            )
            return False

    except Exception as e:
        logger.error(f"[catering] Error in handle_catering_request_created_event: {e}")
        return False


def format_catering_request_message(catering_request) -> str:
    """
    Format catering request details into a text message.

    Args:
        catering_request: CateringRequest object

    Returns:
        str: Formatted message
    """
    message_parts = [
        "New Catering Request",
        f"Date: {catering_request.event_date.strftime('%B %d, %Y')}",
        f"Contact: {catering_request.contact_name}",
        f"Phone: {catering_request.contact_phone_number}",
    ]

    if catering_request.event_time:
        message_parts.append(
            f"Time: {catering_request.event_time.strftime('%I:%M %p')}"
        )

    if catering_request.party_size:
        message_parts.append(f"Party Size: {catering_request.party_size}")

    if catering_request.event_address:
        message_parts.append(f"Address: {catering_request.event_address}")

    if catering_request.event_detail:
        message_parts.append(f"Details: {catering_request.event_detail}")

    return "\n".join(message_parts)


def _validate_and_format_phone_number(phone_number: str) -> str:
    """
    Validate and format phone number to +1xxxxxxxxxx format.

    Args:
        phone_number: Raw phone number input

    Returns:
        str: Formatted phone number in +1xxxxxxxxxx format

    Raises:
        ValueError: If phone number is invalid or cannot be formatted
    """
    if not phone_number:
        raise ValueError("Phone number cannot be empty")

    # Remove all non-digit characters
    digits_only = re.sub(r"\D", "", phone_number)

    # Handle different input formats
    if len(digits_only) == 10:
        # Assume US number without country code: 1234567890 -> +11234567890
        formatted = f"+1{digits_only}"
    elif len(digits_only) == 11 and digits_only.startswith("1"):
        # US number with country code: 11234567890 -> +11234567890
        formatted = f"+{digits_only}"
    else:
        raise ValueError(f"Invalid phone number format: {phone_number}")

    # Validate the final format
    if not re.match(r"^\+1\d{10}$", formatted):
        raise ValueError(
            f"Phone number must be in +1xxxxxxxxxx format, got: {formatted}"
        )

    return formatted


async def send_sms_notification(phone_number: str, message: str) -> bool:
    """
    Send SMS notification using configured SMS service.

    Args:
        phone_number: Phone number to send to (will be validated and formatted)
        message: Message content

    Returns:
        bool: True if sent successfully, False otherwise
    """
    try:
        formatted_phone_number = _validate_and_format_phone_number(phone_number)
        logger.debug(f"[catering] Send message to {formatted_phone_number}")

        PALONA_NUMBER = "+18338725662"
        relay_message = RelayMessage(
            author_type=AuthorType.SYSTEM,
            sender_identifier=PALONA_NUMBER,
            recipient_identifier=formatted_phone_number,
            channel=Channel.SMS,
            broker=Broker.TWILIO,
            type=Type.TEXT,
            text=TextObject(body=message),
            metadata=Metadata(testing=False),
            extras=Extras(),
        )

        # Send the message through the relay service
        response = send_message(relay_message)

        if response.get("status") == "scheduled":
            logger.debug(
                f"[catering] SMS sent successfully to ****{formatted_phone_number[-4:]}"
            )
            return True
        else:
            logger.error(
                f"[catering] Failed to send SMS to ****{formatted_phone_number[-4:]}: {response.get('error_message', 'Unknown error')}"
            )
            return False

    except ValueError as e:
        logger.error(f"[catering] Invalid phone number format: {e}")
        return False
    except Exception as e:
        logger.error(f"[catering] Failed to send SMS to {phone_number}: {e}")
        return False
