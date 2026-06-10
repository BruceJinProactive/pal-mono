import uuid
from typing import Dict

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.catering.catering import (
    CateringRequest,
    CateringRequestActivity,
    CateringRequestListResponse,
    Contact,
    ContactListResponse,
    CreateCateringRequestRequest,
    CreateContactRequest,
    EventBridgeEvent,
    PublicCateringRequest,
    UpdateCateringRequestRequest,
    UpdateContactRequest,
)
from db.tables.catering_request_activities import (
    CateringRequestActivityActorType,
    CateringRequestActivitySource,
)
from services.auth_types import UserContext
from services.catering_service._implementation import (
    create_catering_request_async,
    create_contact,
    delete_contact,
    get_public_catering_request_by_id,
    handle_catering_request_created_event,
    list_catering_requests_by_project_id,
    list_catering_requests_with_activities_by_project_id,
    list_contacts,
)
from services.catering_service._implementation import (
    update_catering_request as update_catering_request_impl,
)
from services.catering_service._implementation import update_contact
from utils.log import logger


def _get_actor_id(context: UserContext) -> uuid.UUID | None:
    try:
        return uuid.UUID(context.username)
    except (TypeError, ValueError):
        return None


def _get_actor_display_name(context: UserContext) -> str:
    for value in (context.display_name, context.email):
        if value and value.strip():
            return value.strip()
    return "Internal user"


async def handle_catering_event(
    event: EventBridgeEvent, session: AsyncSession
) -> Dict[str, str]:
    """
    Handle catering events from AWS EventBridge.
    Routes events based on detail-type to appropriate handlers.
    """
    detail_type = event.detail_type
    detail = event.detail

    logger.debug(
        f"[catering] Received catering event: {detail_type} from {event.source}"
    )

    if detail_type in ("CateringRequestCreated", "catering.RequestCreated"):
        return await handle_catering_request_created(detail, session)
    else:
        logger.warning(f"[catering] Unknown event type received: {detail_type}")
        return {"status": "ignored", "message": f"Unknown event type: {detail_type}"}


async def handle_catering_request_created(
    detail: Dict, session: AsyncSession
) -> Dict[str, str]:
    """
    Handle CateringRequestCreated events.
    Process the catering request creation event and send notifications to catering managers.
    """
    catering_request_id = detail.get("catering_request_id")
    idempotency_key = detail.get("idempotency_key")

    if not catering_request_id:
        logger.error("[catering] Missing catering_request_id in event detail")
        return {"status": "error", "message": "Missing catering_request_id"}

    if not idempotency_key:
        logger.error("[catering] Missing idempotency_key in event detail")
        return {"status": "error", "message": "Missing idempotency_key"}

    try:
        success = await handle_catering_request_created_event(
            catering_request_id, idempotency_key, session
        )

        if success:
            logger.debug(
                f"[catering] Successfully handled catering request created event for request {catering_request_id}"
            )
            status = "success"
        else:
            logger.warning(
                f"[catering] Some actions failed for catering request created event {catering_request_id}"
            )
            status = "failed"

    except Exception as e:
        logger.error(f"[catering] Error handling catering request created event: {e}")
        status = "failed"

    logger.debug(
        f"[catering] Processed catering request created event for request {catering_request_id}"
    )

    return {
        "status": status,
        "catering_request_id": catering_request_id,
        "idempotency_key": idempotency_key,
    }


async def create_project_catering_request(
    project_id: uuid.UUID,
    request: CreateCateringRequestRequest,
    context: UserContext,
    session: AsyncSession,
) -> CateringRequest:
    """
    Create a new catering request for a project.
    """
    catering_request = await create_catering_request_async(
        session=session,
        project_id=project_id,
        event_date=request.event_date,
        contact_name=request.contact_name,
        contact_phone_number=request.contact_phone_number,
        event_time=request.event_time,
        event_address=request.event_address,
        event_detail=request.event_detail,
        all_items=request.all_items,
        event_fulfillment=request.event_fulfillment,
        party_size=request.party_size,
        idempotency_key=request.idempotency_key,
        activity_actor_type=CateringRequestActivityActorType.INTERNAL_USER,
        activity_actor_id=_get_actor_id(context),
        activity_actor_display_name=_get_actor_display_name(context),
        activity_source=CateringRequestActivitySource.ADMIN_CONSOLE,
    )

    return CateringRequest.model_validate(catering_request)


async def list_project_catering_requests(
    project_id: uuid.UUID,
    include_activities: bool,
    activity_limit: int,
    context: UserContext,
    session: AsyncSession,
) -> CateringRequestListResponse:
    """
    List all catering requests for a project.
    """
    del context

    if not include_activities:
        catering_requests = list_catering_requests_by_project_id(project_id)

        return CateringRequestListResponse(
            catering_requests=[
                CateringRequest.model_validate(request) for request in catering_requests
            ]
        )

    catering_requests_with_activities = (
        await list_catering_requests_with_activities_by_project_id(
            session=session,
            project_id=project_id,
            activity_limit=activity_limit,
        )
    )

    response_requests: list[CateringRequest] = []
    for catering_request, activities in catering_requests_with_activities:
        response_request = CateringRequest.model_validate(catering_request)
        response_request.activities = [
            CateringRequestActivity.model_validate(activity) for activity in activities
        ]
        response_requests.append(response_request)

    return CateringRequestListResponse(catering_requests=response_requests)


async def get_public_catering_request(
    catering_request_id: uuid.UUID,
    session: AsyncSession,
) -> PublicCateringRequest:
    """
    Get public-safe catering request details by ID.
    """
    catering_request = await get_public_catering_request_by_id(
        session=session,
        catering_request_id=catering_request_id,
    )

    if catering_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Catering request {catering_request_id} not found",
            headers={"Content-Type": "application/json"},
        )

    return PublicCateringRequest.model_validate(catering_request)


async def update_catering_request(
    catering_request_id: uuid.UUID,
    request: UpdateCateringRequestRequest,
    context: UserContext,
    session: AsyncSession,
) -> CateringRequest:
    """
    Update an existing catering request.
    """
    updated_request = await update_catering_request_impl(
        session=session,
        catering_request_id=catering_request_id,
        event_date=request.event_date,
        contact_name=request.contact_name,
        contact_phone_number=request.contact_phone_number,
        event_time=request.event_time,
        event_address=request.event_address,
        event_detail=request.event_detail,
        all_items=request.all_items,
        event_fulfillment=request.event_fulfillment,
        party_size=request.party_size,
        status=request.status,
        actor_id=_get_actor_id(context),
        actor_display_name=_get_actor_display_name(context),
    )

    return CateringRequest.model_validate(updated_request)


async def create_project_contact(
    project_id: uuid.UUID,
    request: CreateContactRequest,
    context: UserContext,
    session: AsyncSession,
) -> Contact:
    """
    Create a new contact for a project.
    """
    contact = await create_contact(
        session=session,
        project_id=project_id,
        name=request.name,
        phone_number=request.phone_number,
        role=request.role,
        email=request.email,
    )

    return Contact.model_validate(contact)


async def list_project_contacts(
    project_id: uuid.UUID,
    context: UserContext,
    session: AsyncSession,
) -> ContactListResponse:
    """
    List all contacts for a project.
    """
    contacts = await list_contacts(session, project_id)

    return ContactListResponse(
        contacts=[Contact.model_validate(contact) for contact in contacts]
    )


async def update_project_contact(
    project_id: uuid.UUID,
    contact_id: uuid.UUID,
    request: UpdateContactRequest,
    session: AsyncSession,
) -> Contact:
    """
    Update a contact for a project.
    """
    updated_contact = await update_contact(
        session=session,
        project_id=project_id,
        contact_id=contact_id,
        name=request.name,
        phone_number=request.phone_number,
        role=request.role,
        email=request.email,
    )

    if not updated_contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Contact {contact_id} not found for project {project_id}",
            headers={"Content-Type": "application/json"},
        )

    logger.debug(f"Successfully updated contact {contact_id} for project {project_id}")
    return Contact.model_validate(updated_contact)


async def delete_project_contact(
    project_id: uuid.UUID,
    contact_id: uuid.UUID,
    context: UserContext,
    session: AsyncSession,
) -> Dict[str, str]:
    """
    Delete a contact from a project.
    """
    deleted_contact = await delete_contact(session, project_id, contact_id)

    if deleted_contact:
        logger.debug(
            f"Successfully deleted contact {contact_id} from project {project_id}"
        )
        return {"status": "deleted"}
    else:
        logger.warning(f"Contact {contact_id} not found for project {project_id}")
        return {"status": "not_found"}
