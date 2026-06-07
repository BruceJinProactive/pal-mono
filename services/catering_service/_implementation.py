import asyncio
import dataclasses
import enum
import os
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.chat.message import AuthorType, Broker, Extras
from api.schemas.chat.message import Message as RelayMessage
from api.schemas.chat.message import Metadata, TextObject, Type
from db.pal_repository.catering_request import (
    CateringRequestRepository as CateringRequestRepositoryNew,
)
from db.pal_repository.catering_request_activity import (
    CateringRequestActivityRepository,
)
from db.pal_repository.data_classes.catering_request import CateringRequestData
from db.pal_repository.data_classes.catering_request_activity import (
    CateringRequestActivityData,
)
from db.pal_repository.data_classes.contact import ContactData
from db.repositories.catering_request_repository import (
    CateringRequestRepository,
    CateringRequestRepositoryAsync,
)
from db.repositories.project_repository import ProjectRepository, ProjectRepositoryAsync
from db.session import SyncSessionLocal
from db.tables.catering_request_activities import (
    CateringRequestActivityActorType,
    CateringRequestActivitySource,
    CateringRequestActivityType,
)
from db.tables.catering_requests import CateringRequest, FulfillmentType, RequestStatus
from db.tables.types import Channel
from events import CateringRequestCreated, publish_event
from services import contact_service
from services.relay_service import send_message
from utils.log import logger

CATERING_MANAGER_ROLE = "catering"
CUSTOMER_STATUS_SMS_STATUSES: set[RequestStatus] = {
    RequestStatus.CONFIRMED,
    RequestStatus.IN_PREPARATION,
    RequestStatus.READY,
}
CATERING_REQUEST_CONFIRMATION_HOSTS: dict[str, str] = {
    "prd": "console.palona.ai",
    "lat": "lat-console.palona.ai",
    "stg": "stg-console.palona.ai",
}
CATERING_REQUEST_ACTIVITY_LIMIT_MAX = 100
CATERING_REQUEST_ACTIVITY_LIMIT_DEFAULT = 50
CATERING_REQUEST_ACTIVITY_SYSTEM_ACTOR = "System"


def _serialize_activity_value(value: object) -> object:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _snapshot_request_fields(
    catering_request: CateringRequest | CateringRequestData,
    fields: list[str],
) -> dict[str, object]:
    return {
        field: _serialize_activity_value(getattr(catering_request, field))
        for field in fields
    }


def _build_changed_fields_metadata(
    before: dict[str, object], after: dict[str, object]
) -> dict[str, dict[str, object]]:
    changed_fields: dict[str, dict[str, object]] = {}
    for field, old_value in before.items():
        new_value = after.get(field)
        if old_value != new_value:
            changed_fields[field] = {"old": old_value, "new": new_value}
    return changed_fields


async def record_catering_request_activity(
    session: AsyncSession,
    catering_request_id: uuid.UUID,
    project_id: uuid.UUID,
    activity_type: CateringRequestActivityType,
    actor_type: CateringRequestActivityActorType,
    actor_display_name: str,
    description: str,
    source: CateringRequestActivitySource,
    metadata: dict[str, Any] | None = None,
    actor_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
) -> CateringRequestActivityData:
    now = datetime.now(tz=timezone.utc)
    activity = CateringRequestActivityData(
        id=uuid.uuid4(),
        catering_request_id=catering_request_id,
        project_id=project_id,
        activity_type=activity_type,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_display_name=actor_display_name,
        description=description,
        metadata=metadata or {},
        schema_version=1,
        source=source,
        occurred_at=occurred_at or now,
        created_at=now,
    )
    return await CateringRequestActivityRepository(session).create(activity)


async def _record_catering_request_activity_safely(
    session: AsyncSession,
    catering_request_id: uuid.UUID,
    project_id: uuid.UUID,
    activity_type: CateringRequestActivityType,
    actor_type: CateringRequestActivityActorType,
    actor_display_name: str,
    description: str,
    source: CateringRequestActivitySource,
    metadata: dict[str, Any] | None = None,
    actor_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
) -> None:
    try:
        await record_catering_request_activity(
            session=session,
            catering_request_id=catering_request_id,
            project_id=project_id,
            activity_type=activity_type,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_display_name=actor_display_name,
            description=description,
            source=source,
            metadata=metadata,
            occurred_at=occurred_at,
        )
    except Exception:
        logger.warning(
            "[catering] Failed to record catering request activity.",
            extra={
                "request_id": str(catering_request_id),
                "project_id": str(project_id),
                "activity_type": activity_type.value,
            },
            exc_info=True,
        )


async def list_catering_request_activities(
    session: AsyncSession,
    project_id: uuid.UUID,
    catering_request_id: uuid.UUID,
    limit: int = CATERING_REQUEST_ACTIVITY_LIMIT_DEFAULT,
    before: datetime | None = None,
) -> list[CateringRequestActivityData] | None:
    request_repo = CateringRequestRepositoryNew(session)
    catering_request = await request_repo.get_by_id(catering_request_id)
    if catering_request is None or catering_request.project_id != project_id:
        return None

    bounded_limit = min(max(limit, 1), CATERING_REQUEST_ACTIVITY_LIMIT_MAX)
    activity_repo = CateringRequestActivityRepository(session)
    return await activity_repo.list_by_request(
        project_id=project_id,
        catering_request_id=catering_request_id,
        limit=bounded_limit,
        before=before,
    )


async def list_catering_requests_with_activities_by_project_id(
    session: AsyncSession,
    project_id: uuid.UUID,
    activity_limit: int = CATERING_REQUEST_ACTIVITY_LIMIT_DEFAULT,
) -> list[tuple[CateringRequestData, list[CateringRequestActivityData]]]:
    bounded_limit = min(max(activity_limit, 1), CATERING_REQUEST_ACTIVITY_LIMIT_MAX)
    request_repo = CateringRequestRepositoryNew(session)
    activity_repo = CateringRequestActivityRepository(session)
    catering_requests = await request_repo.get_by_project_id(project_id)

    requests_with_activities: list[
        tuple[CateringRequestData, list[CateringRequestActivityData]]
    ] = []
    for catering_request in catering_requests:
        activities = await activity_repo.list_by_request(
            project_id=project_id,
            catering_request_id=catering_request.id,
            limit=bounded_limit,
        )
        requests_with_activities.append((catering_request, activities))

    return requests_with_activities


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
                status=RequestStatus.LEAD,
                idempotency_key=idempotency_key,
            )

            created_request = catering_request_repo.create_catering_request(
                catering_request
            )

            # Get project to retrieve account_id for the event
            project_repo = ProjectRepository(session)
            project = project_repo.get_project(project_id)
            if not project:
                logger.warning(
                    f"Project {project_id} not found, skipping event publishing"
                )
                return created_request

            # Publish event for new catering request creation to EventBridge
            event = CateringRequestCreated(
                catering_request_id=created_request.id,
                account_id=project.account_id,
                event_date=datetime.combine(created_request.event_date, time.min),
                guest_count=created_request.party_size or 0,
                idempotency_key=idempotency_key,
                created_at=created_request.created_at or datetime.utcnow(),
            )
            event_published = asyncio.run(publish_event(event))
            if not event_published:
                logger.warning(
                    f"Failed to publish catering_request_created event for request {created_request.id}"
                )

            return created_request
    finally:
        session.close()


async def create_catering_request_async(
    session: AsyncSession,
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
    activity_actor_type: CateringRequestActivityActorType = (
        CateringRequestActivityActorType.CUSTOMER
    ),
    activity_actor_id: uuid.UUID | None = None,
    activity_actor_display_name: str | None = None,
    activity_source: CateringRequestActivitySource = CateringRequestActivitySource.AI_AGENT,
) -> CateringRequestData:
    """Create or update a catering request asynchronously with idempotency support."""
    repo = CateringRequestRepositoryNew(session)

    if idempotency_key is None:
        idempotency_key = str(uuid.uuid4())

    existing_request = await repo.get_by_idempotency_key(idempotency_key)

    if existing_request:
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

        update_kwargs: dict = {}
        for field, new_value in field_mappings.items():
            if new_value is not None and getattr(existing_request, field) != new_value:
                update_kwargs[field] = new_value

        if update_kwargs:
            fields = list(update_kwargs.keys())
            before_values = _snapshot_request_fields(existing_request, fields)
            updated = await repo.update(
                idempotency_key=idempotency_key, **update_kwargs
            )
            if updated is not None:
                after_values = _snapshot_request_fields(updated, fields)
                changed_fields = _build_changed_fields_metadata(
                    before_values, after_values
                )
                if changed_fields:
                    await _record_catering_request_activity_safely(
                        session=session,
                        catering_request_id=updated.id,
                        project_id=updated.project_id,
                        activity_type=CateringRequestActivityType.REQUEST_UPDATED,
                        actor_type=activity_actor_type,
                        actor_id=activity_actor_id,
                        actor_display_name=activity_actor_display_name
                        or updated.contact_name,
                        description="Catering request updated.",
                        source=activity_source,
                        metadata={"changed_fields": changed_fields},
                    )
            return updated or existing_request
        return existing_request

    data = CateringRequestData(
        id=uuid.uuid4(),
        project_id=project_id,
        event_date=event_date,
        contact_name=contact_name,
        contact_phone_number=contact_phone_number,
        status=RequestStatus.LEAD.value,
        idempotency_key=idempotency_key,
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
        event_time=event_time,
        event_address=event_address,
        event_detail=event_detail,
        event_fulfillment=event_fulfillment.value if event_fulfillment else None,
        party_size=party_size,
    )

    created_request_id = await repo.create(data)
    data = dataclasses.replace(data, id=created_request_id)

    await _record_catering_request_activity_safely(
        session=session,
        catering_request_id=data.id,
        project_id=data.project_id,
        activity_type=CateringRequestActivityType.REQUEST_CREATED,
        actor_type=activity_actor_type,
        actor_id=activity_actor_id,
        actor_display_name=activity_actor_display_name or data.contact_name,
        description="Catering request created.",
        source=activity_source,
        metadata={
            "initial_fields": _snapshot_request_fields(
                data,
                [
                    "event_date",
                    "event_time",
                    "event_address",
                    "event_detail",
                    "event_fulfillment",
                    "contact_name",
                    "contact_phone_number",
                    "party_size",
                    "status",
                ],
            )
        },
    )

    project_repo = ProjectRepositoryAsync(session)
    project = await project_repo.get_project(project_id)
    if not project:
        logger.warning(f"Project {project_id} not found, skipping event publishing")
        return data

    event = CateringRequestCreated(
        catering_request_id=data.id,
        account_id=project.account_id,
        event_date=datetime.combine(data.event_date, time.min),
        guest_count=data.party_size or 0,
        idempotency_key=idempotency_key,
        created_at=data.created_at or datetime.now(tz=timezone.utc),
    )
    event_published = await publish_event(event)
    if not event_published:
        logger.warning(
            f"Failed to publish catering_request_created event for request {data.id}"
        )

    return data


async def get_public_catering_request_by_id(
    session: AsyncSession,
    catering_request_id: uuid.UUID,
) -> CateringRequestData | None:
    """Fetch a catering request for a public detail page."""
    repo = CateringRequestRepositoryNew(session)
    return await repo.get_by_id(catering_request_id)


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
) -> ContactData:
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
        ContactData: The created contact
    """
    return await contact_service.create_for_project(
        session,
        project_id=project_id,
        name=name,
        phone_number=phone_number,
        role=role,
        email=email,
    )


async def list_contacts(
    session: AsyncSession,
    project_id: uuid.UUID,
) -> List[ContactData]:
    """
    List all contacts for a specific project asynchronously.

    Args:
        session: Async database session
        project_id: ID of the project to list contacts for

    Returns:
        List[ContactData]: List of contacts associated with the project
    """
    return await contact_service.list_by_project(session, project_id)


async def delete_contact(
    session: AsyncSession,
    project_id: uuid.UUID,
    contact_id: uuid.UUID,
) -> ContactData | None:
    """
    Delete a contact and its project relation asynchronously.

    Args:
        session: Async database session
        project_id: ID of the project
        contact_id: ID of the contact to delete

    Returns:
        ContactData | None: The deleted contact, or None if not found
    """
    return await contact_service.delete_from_project(session, project_id, contact_id)


async def update_contact(
    session: AsyncSession,
    project_id: uuid.UUID,
    contact_id: uuid.UUID,
    name: Optional[str] = None,
    phone_number: Optional[str] = None,
    role: Optional[str] = None,
    email: Optional[str] = None,
) -> ContactData | None:
    """
    Update an existing contact for a project asynchronously.

    Args:
        session: Async database session
        project_id: ID of the project the contact belongs to
        contact_id: ID of the contact to update
        name: New contact name (optional)
        phone_number: New phone number (optional)
        role: New role (optional)
        email: New email address (optional)

    Returns:
        ContactData | None: The updated contact, or None if not found
    """
    return await contact_service.update_for_project(
        session,
        project_id=project_id,
        contact_id=contact_id,
        name=name,
        phone_number=phone_number,
        role=role,
        email=email,
    )


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
    actor_id: uuid.UUID | None = None,
    actor_display_name: str | None = None,
    actor_type: CateringRequestActivityActorType = (
        CateringRequestActivityActorType.INTERNAL_USER
    ),
    activity_source: CateringRequestActivitySource = (
        CateringRequestActivitySource.ADMIN_CONSOLE
    ),
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
    catering_request_repo = CateringRequestRepositoryAsync(session)
    existing_request = await catering_request_repo.get_catering_request_by_id(
        catering_request_id
    )
    if existing_request is None:
        raise ValueError(f"Catering request {catering_request_id} not found")

    tracked_fields = [
        "event_date",
        "contact_name",
        "contact_phone_number",
        "event_time",
        "event_address",
        "event_detail",
        "event_fulfillment",
        "party_size",
        "status",
    ]
    before_values = _snapshot_request_fields(existing_request, tracked_fields)

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

    updated_request = await catering_request_repo.update_catering_request(
        catering_request_id, updated_catering_request
    )
    after_values = _snapshot_request_fields(updated_request, tracked_fields)
    changed_fields = _build_changed_fields_metadata(before_values, after_values)

    if changed_fields:
        activity_type = CateringRequestActivityType.REQUEST_UPDATED
        description = "Catering request updated."
        metadata: dict[str, Any] = {"changed_fields": changed_fields}

        if "status" in changed_fields:
            activity_type = CateringRequestActivityType.STATUS_CHANGED
            from_status = changed_fields["status"]["old"]
            to_status = changed_fields["status"]["new"]
            description = f"Moved request from {from_status} to {to_status}."
            metadata = {
                "from_status": from_status,
                "to_status": to_status,
                "changed_fields": changed_fields,
            }

        await _record_catering_request_activity_safely(
            session=session,
            catering_request_id=updated_request.id,
            project_id=updated_request.project_id,
            activity_type=activity_type,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_display_name=actor_display_name
            or CATERING_REQUEST_ACTIVITY_SYSTEM_ACTOR,
            description=description,
            source=activity_source,
            metadata=metadata,
        )
        await session.refresh(updated_request)

    previous_status_value = before_values["status"]
    requested_status_value = (
        status.value if isinstance(status, RequestStatus) else status
    )
    updated_status_value = (
        updated_request.status.value
        if isinstance(updated_request.status, RequestStatus)
        else updated_request.status
    )
    sms_skip_reason = _get_customer_status_sms_skip_reason(status)

    logger.info(
        "[catering] Processed catering request update.",
        extra={
            "request_id": str(updated_request.id),
            "previous_status": previous_status_value,
            "requested_status": requested_status_value,
            "updated_status": updated_status_value,
            "customer_status_sms_decision": sms_skip_reason,
        },
    )

    if sms_skip_reason == "eligible":
        logger.info(
            "[catering] Customer status SMS eligible; attempting send.",
            extra={
                "request_id": str(updated_request.id),
                "previous_status": previous_status_value,
                "requested_status": requested_status_value,
                "updated_status": updated_status_value,
            },
        )
        try:
            business_name = await _get_catering_business_name(
                session, updated_request.project_id
            )
            try:
                store_phone_number = await _get_catering_store_phone_number(
                    session, updated_request.project_id
                )
            except Exception as exc:
                store_phone_number = None
                logger.warning(
                    "[catering] Failed to resolve store phone number for customer status SMS.",
                    extra={
                        "request_id": str(updated_request.id),
                        "project_id": str(updated_request.project_id),
                        "error": str(exc),
                    },
                )
            sms_sent = await asyncio.to_thread(
                send_sms_notification,
                updated_request.contact_phone_number,
                _build_customer_status_sms_message(
                    updated_request, business_name, store_phone_number
                ),
            )
            if not sms_sent:
                logger.warning(
                    "[catering] Updated request status but failed to send customer status SMS.",
                    extra={
                        "request_id": str(updated_request.id),
                        "old_status": previous_status_value,
                        "new_status": updated_status_value,
                    },
                )
        except Exception as exc:
            logger.warning(
                "[catering] Updated request status but customer status SMS notification failed unexpectedly.",
                extra={
                    "request_id": str(updated_request.id),
                    "old_status": previous_status_value,
                    "new_status": updated_status_value,
                    "error": str(exc),
                },
            )
    else:
        logger.info(
            "[catering] Customer status SMS skipped.",
            extra={
                "request_id": str(updated_request.id),
                "previous_status": previous_status_value,
                "requested_status": requested_status_value,
                "updated_status": updated_status_value,
                "skip_reason": sms_skip_reason,
            },
        )

    return updated_request


def _should_send_customer_status_sms(
    previous_status: RequestStatus | None, next_status: RequestStatus | None
) -> bool:
    del previous_status
    if next_status is None:
        return False

    return next_status in CUSTOMER_STATUS_SMS_STATUSES


def _get_customer_status_sms_skip_reason(next_status: RequestStatus | None) -> str:
    if next_status is None:
        return "no_status_requested"
    if next_status not in CUSTOMER_STATUS_SMS_STATUSES:
        return "status_not_supported"
    return "eligible"


async def _get_catering_business_name(
    session: AsyncSession, project_id: uuid.UUID
) -> str:
    project = await ProjectRepositoryAsync(session).get_project(project_id)
    if project:
        account = getattr(project, "account", None)
        for candidate in (
            getattr(account, "display_name", None),
            getattr(account, "name", None),
            project.display_name,
            project.name,
        ):
            if candidate and candidate.strip():
                return candidate.strip()
    return "the business"


async def _get_catering_store_phone_number(
    session: AsyncSession, project_id: uuid.UUID
) -> str | None:
    contacts = await contact_service.list_by_project(session, project_id)
    contacts_with_phone = [
        contact for contact in contacts if contact.phone_number.strip()
    ]
    if len(contacts_with_phone) == 1:
        return contacts_with_phone[0].phone_number.strip()

    for preferred_role in (CATERING_MANAGER_ROLE, "general"):
        for contact in contacts_with_phone:
            if contact.role.strip().lower() == preferred_role:
                return contact.phone_number.strip()
    return None


def _build_customer_status_sms_message(
    catering_request: CateringRequest,
    business_name: str,
    store_phone_number: str | None = None,
) -> str:
    raw_contact_name = getattr(catering_request, "contact_name", None)
    raw_event_fulfillment = getattr(catering_request, "event_fulfillment", None)
    contact_name = raw_contact_name if isinstance(raw_contact_name, str) else None
    event_fulfillment: FulfillmentType | str | None
    if isinstance(raw_event_fulfillment, (FulfillmentType, str)):
        event_fulfillment = raw_event_fulfillment
    else:
        event_fulfillment = None

    greeting = _build_customer_sms_greeting(contact_name)
    event_phrase = _build_customer_sms_event_phrase(catering_request.event_date)
    confirmation_link_sentence = _build_customer_sms_confirmation_link_sentence(
        catering_request.id
    )
    contact_sentence = _build_customer_sms_contact_sentence(store_phone_number)
    preparation_followup_sentence = _build_preparation_followup_sentence(
        event_fulfillment,
        bool(event_phrase),
    )
    ready_fulfillment_phrase = _build_ready_fulfillment_phrase(event_fulfillment)

    if catering_request.status == RequestStatus.CONFIRMED:
        return (
            f"{greeting} your catering request with {business_name}{event_phrase} "
            f"is confirmed. We'll reach out if we need any final details."
            f"{confirmation_link_sentence}"
            f"{contact_sentence}"
        )

    if catering_request.status == RequestStatus.IN_PREPARATION:
        return (
            f"{greeting} {business_name} has started preparing your catering order"
            f"{event_phrase}.{preparation_followup_sentence}"
            f"{confirmation_link_sentence}"
            f"{contact_sentence}"
        )

    if catering_request.status == RequestStatus.READY:
        return (
            f"{greeting} your catering order from {business_name}{event_phrase} "
            f"is ready{ready_fulfillment_phrase}."
            f"{confirmation_link_sentence}"
            f"{contact_sentence}"
        )

    raise ValueError(
        f"Unsupported catering status for customer SMS: {catering_request.status}"
    )


def _build_customer_sms_greeting(contact_name: str | None) -> str:
    if contact_name and contact_name.strip():
        return f"Hi {contact_name.strip()},"
    return "Hi,"


def _build_customer_sms_event_phrase(event_date: date | None) -> str:
    if event_date is None:
        return ""
    return f" for {event_date.strftime('%B %d, %Y')}"


def _build_customer_sms_contact_sentence(store_phone_number: str | None) -> str:
    if store_phone_number and store_phone_number.strip():
        return f" Questions? Call {store_phone_number.strip()}."
    return ""


def _build_customer_sms_confirmation_link_sentence(
    catering_request_id: uuid.UUID,
) -> str:
    url = _get_catering_request_confirmation_url(catering_request_id)
    return f" View details: {url}"


def _get_catering_request_confirmation_url(catering_request_id: uuid.UUID) -> str:
    runtime_env = os.getenv("RUNTIME_ENV", "prd").strip().lower()
    host = CATERING_REQUEST_CONFIRMATION_HOSTS.get(
        runtime_env,
        CATERING_REQUEST_CONFIRMATION_HOSTS["prd"],
    )
    return f"https://{host}/catering-request/{catering_request_id}"


def _get_customer_sms_fulfillment_label(
    event_fulfillment: FulfillmentType | str | None,
) -> str | None:
    fulfillment_value = (
        event_fulfillment.value
        if isinstance(event_fulfillment, FulfillmentType)
        else event_fulfillment
    )
    if fulfillment_value == FulfillmentType.DELIVERY.value:
        return "delivery"
    if fulfillment_value == FulfillmentType.PICKUP.value:
        return "pickup"
    return None


def _build_preparation_followup_sentence(
    event_fulfillment: FulfillmentType | str | None,
    has_event_date: bool,
) -> str:
    fulfillment_label = _get_customer_sms_fulfillment_label(event_fulfillment)
    if fulfillment_label:
        return f" We'll keep you posted as it gets closer to {fulfillment_label}."
    if has_event_date:
        return " We'll keep you posted as your event gets closer."
    return " We'll keep you posted."


def _build_ready_fulfillment_phrase(
    event_fulfillment: FulfillmentType | str | None,
) -> str:
    fulfillment_label = _get_customer_sms_fulfillment_label(event_fulfillment)
    if fulfillment_label:
        return f" for {fulfillment_label}"
    return ""


def _is_catering_manager_role(role: str | None) -> bool:
    return bool(role) and role.strip().lower() == CATERING_MANAGER_ROLE


async def _find_and_assign_catering_manager(
    session: AsyncSession,
    catering_request,
    catering_request_id: str,
) -> ContactData | None:
    """
    Find a catering manager for the request and assign it if needed.

    Args:
        session: Database session
        catering_request: The catering request object
        catering_request_id: ID of the catering request (for logging)

    Returns:
        ContactData | None: The catering manager contact if found, None otherwise
    """
    contacts = await contact_service.list_by_project(
        session, catering_request.project_id
    )

    # Try to get the direct contact first, but only if it is still linked
    if catering_request.contact_id:
        catering_manager = next(
            (c for c in contacts if c.id == catering_request.contact_id),
            None,
        )
        if catering_manager:
            logger.debug(
                f"[catering] Using existing contact {catering_manager.name} (ID: {catering_manager.id})"
            )
            return catering_manager

    if not contacts:
        logger.warning(
            f"[catering] No contacts found for project {catering_request.project_id}"
        )
        return None

    # Find the first catering manager
    catering_manager = next(
        (contact for contact in contacts if _is_catering_manager_role(contact.role)),
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

        notification_success = await asyncio.to_thread(
            send_sms_notification, catering_manager.phone_number, message
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


def send_sms_notification(phone_number: str, message: str) -> bool:
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
        sender_number = os.getenv("CATERING_SMS_SENDER_NUMBER", "+19803725662")
        logger.debug(
            f"[catering] Sending SMS from ****{sender_number[-4:]} to ****{formatted_phone_number[-4:]}"
        )
        relay_message = RelayMessage(
            author_type=AuthorType.SYSTEM,
            sender_identifier=sender_number,
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


@dataclasses.dataclass
class CateringReminderResult:
    """Result summary from processing catering inquiry reminders."""

    projects_checked: int = 0
    reminders_sent: int = 0
    apologies_sent: int = 0
    errors: list[str] = dataclasses.field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


async def _find_catering_manager_for_project(
    session: AsyncSession,
    project_id: uuid.UUID,
) -> ContactData | None:
    """
    Find the catering manager contact for a project (without assignment side effects).

    Args:
        session: Database session.
        project_id: The project to look up contacts for.

    Returns:
        The catering manager contact if found, None otherwise.
    """
    contacts = await contact_service.list_by_project(session, project_id)
    if not contacts:
        return None

    return next(
        (c for c in contacts if _is_catering_manager_role(c.role)),
        None,
    )


def format_catering_reminder_message(
    requests: list[CateringRequest],
) -> str:
    """
    Format a reminder message for stale catering inquiry requests.

    Args:
        requests: The qualifying catering requests (all for the same project).

    Returns:
        Formatted SMS message string.
    """
    if len(requests) == 1:
        req = requests[0]
        parts = [
            "A catering request from 2 days ago is still at lead status.",
            f"Date: {req.event_date.strftime('%B %d, %Y')}",
            f"Contact: {req.contact_name} ({req.contact_phone_number})",
        ]
        if req.party_size:
            parts.append(f"Party Size: {req.party_size}")
        parts.append("Please review and update this request.")
        return "\n".join(parts)

    parts = [
        f"There are {len(requests)} catering requests from 2 days ago that are still at lead status.",
        "",
    ]
    for i, req in enumerate(requests, 1):
        line = f"{i}. {req.event_date.strftime('%b %d')} - {req.contact_name} ({req.contact_phone_number})"
        if req.party_size:
            line += f", Party of {req.party_size}"
        parts.append(line)
    parts.append("")
    parts.append("You may want to review or update these requests.")
    return "\n".join(parts)


async def send_catering_inquiry_reminders(
    session: AsyncSession,
) -> CateringReminderResult:
    """
    Send reminder SMS for catering inquiries that are exactly 2 calendar days old.

    For each project with qualifying requests, sends ONE reminder SMS to the
    catering manager. A request qualifies if:
    - Status is LEAD or legacy INQUIRY
    - created_at date (in the project's timezone) is exactly 2 days ago
    - The event date/time has not yet passed

    Args:
        session: Async database session.

    Returns:
        CateringReminderResult with summary of actions taken.
    """
    result = CateringReminderResult()
    now_utc = datetime.now(timezone.utc)

    # Wide UTC window to ensure no request is missed by the prefilter.
    # A request created late on "2 days ago" in an eastern timezone (e.g. 11 PM ET)
    # may be only ~36h old at job time (19:00 UTC). A request created early on
    # "2 days ago" in a western timezone may be ~63h old. We use 72h-24h to be safe;
    # the per-project timezone filter in Python handles exact calendar-day matching.
    created_after = now_utc - timedelta(hours=72)
    created_before = now_utc - timedelta(hours=24)

    catering_repo = CateringRequestRepositoryAsync(session)
    candidate_requests = await catering_repo.list_inquiry_requests_in_date_range(
        created_after=created_after,
        created_before=created_before,
    )

    if not candidate_requests:
        logger.debug("[catering-reminder] No candidate inquiry requests found")
        return result

    # Group by project
    requests_by_project: dict[uuid.UUID, list[CateringRequest]] = {}
    for req in candidate_requests:
        requests_by_project.setdefault(req.project_id, []).append(req)

    # Fetch all projects for timezone info
    project_repo = ProjectRepositoryAsync(session)
    projects = await project_repo.list_projects_by_ids(list(requests_by_project.keys()))
    projects_by_id = {p.id: p for p in projects}

    for project_id, project_requests in requests_by_project.items():
        project = projects_by_id.get(project_id)
        if not project:
            logger.warning(
                f"[catering-reminder] Project {project_id} not found, skipping"
            )
            continue

        result.projects_checked += 1
        try:
            tz = ZoneInfo(project.timezone or "America/Los_Angeles")
        except (KeyError, Exception):
            logger.warning(
                f"[catering-reminder] Invalid timezone '{project.timezone}' for project {project_id}, skipping"
            )
            continue
        now_local = now_utc.astimezone(tz)
        today_local = now_local.date()
        two_days_ago = today_local - timedelta(days=2)

        # Filter: created exactly 2 calendar days ago in project timezone
        qualifying: list[CateringRequest] = []
        for req in project_requests:
            created_local = req.created_at.astimezone(tz).date()
            if created_local != two_days_ago:
                continue

            # Filter: event hasn't passed
            if req.event_date < today_local:
                continue
            if (
                req.event_date == today_local
                and req.event_time is not None
                and req.event_time < now_local.time()
            ):
                continue

            qualifying.append(req)

        if not qualifying:
            continue

        # Find catering manager
        catering_manager = await _find_catering_manager_for_project(session, project_id)
        if not catering_manager:
            logger.warning(
                f"[catering-reminder] No catering manager for project {project_id}, skipping"
            )
            continue

        # Send one reminder SMS. Not idempotent, but retries only happen if
        # pal-mono is fully down (5xx/timeout), so duplicates are near-impossible.
        message = format_catering_reminder_message(qualifying)
        try:
            sms_success = await asyncio.to_thread(
                send_sms_notification, catering_manager.phone_number, message
            )
            if sms_success:
                result.reminders_sent += 1
                logger.info(
                    f"[catering-reminder] Sent reminder to {catering_manager.name} "
                    f"for project {project_id} ({len(qualifying)} request(s))"
                )
            else:
                error_msg = f"SMS failed for project {project_id}"
                result.errors.append(error_msg)
                logger.error(f"[catering-reminder] {error_msg}")
        except Exception as e:
            error_msg = f"Error sending reminder for project {project_id}: {e}"
            result.errors.append(error_msg)
            logger.error(f"[catering-reminder] {error_msg}")

    return result


def format_catering_apology_message(
    request: CateringRequest,
    project_name: str,
) -> str:
    """
    Format an apology message for a requester whose catering event has passed
    while still at lead status.

    Args:
        request: The catering request.
        project_name: Display name of the project/restaurant.

    Returns:
        Formatted SMS message string.
    """
    parts = [
        f"Hi {request.contact_name}, we're sorry if we weren't able to respond "
        f"to your catering request for {request.event_date.strftime('%B %d, %Y')} in time.",
        "We apologize for the inconvenience and hope to assist you with future catering needs.",
        f"- {project_name}",
    ]
    return "\n".join(parts)


async def send_catering_inquiry_apologies(
    session: AsyncSession,
) -> CateringReminderResult:
    """
    Send apology SMS to requesters whose catering event has passed while still
    at lead status.

    A request qualifies if:
    - Status is LEAD or legacy INQUIRY
    - event_date (calendar date) was yesterday in the project's timezone

    Sends one apology SMS per qualifying request to the requester's phone number.

    Args:
        session: Async database session.

    Returns:
        CateringReminderResult with apologies_sent populated.
    """
    result = CateringReminderResult()
    now_utc = datetime.now(timezone.utc)

    # event_date is a plain Date column. "Yesterday" can vary across timezones
    # by up to ~1 day, so we query a 3-day window and filter per-project timezone.
    event_date_start = (now_utc - timedelta(days=3)).date()
    event_date_end = (now_utc - timedelta(days=0)).date()

    catering_repo = CateringRequestRepositoryAsync(session)
    candidate_requests = await catering_repo.list_inquiry_requests_by_event_date_range(
        event_date_start=event_date_start,
        event_date_end=event_date_end,
    )

    if not candidate_requests:
        logger.debug("[catering-apology] No candidate inquiry requests found")
        return result

    # Group by project
    requests_by_project: dict[uuid.UUID, list[CateringRequest]] = {}
    for req in candidate_requests:
        requests_by_project.setdefault(req.project_id, []).append(req)

    # Fetch all projects for timezone info and display name
    project_repo = ProjectRepositoryAsync(session)
    projects = await project_repo.list_projects_by_ids(list(requests_by_project.keys()))
    projects_by_id = {p.id: p for p in projects}

    for project_id, project_requests in requests_by_project.items():
        project = projects_by_id.get(project_id)
        if not project:
            logger.warning(
                f"[catering-apology] Project {project_id} not found, skipping"
            )
            continue

        result.projects_checked += 1
        try:
            tz = ZoneInfo(project.timezone or "America/Los_Angeles")
        except (KeyError, Exception):
            logger.warning(
                f"[catering-apology] Invalid timezone '{project.timezone}' for project {project_id}, skipping"
            )
            continue
        now_local = now_utc.astimezone(tz)
        yesterday_local = now_local.date() - timedelta(days=1)

        # Filter: event_date was exactly yesterday in the project timezone
        qualifying = [
            req for req in project_requests if req.event_date == yesterday_local
        ]

        if not qualifying:
            continue

        project_name = getattr(project, "display_name", None) or getattr(
            project, "name", "Our Restaurant"
        )

        for req in qualifying:
            message = format_catering_apology_message(req, project_name)
            try:
                sms_success = await asyncio.to_thread(
                    send_sms_notification, req.contact_phone_number, message
                )
                if sms_success:
                    result.apologies_sent += 1
                    logger.info(
                        f"[catering-apology] Sent apology to {req.contact_name} "
                        f"for request {req.id} in project {project_id}"
                    )
                else:
                    error_msg = f"Apology SMS failed for request {req.id} in project {project_id}"
                    result.errors.append(error_msg)
                    logger.error(f"[catering-apology] {error_msg}")
            except Exception as e:
                error_msg = f"Error sending apology for request {req.id} in project {project_id}: {e}"
                result.errors.append(error_msg)
                logger.error(f"[catering-apology] {error_msg}")

    return result
