import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.routes.admin._auth import authenticate_user
from api.routes.endpoints import endpoints
from api.schemas.catering.catering import (
    CateringRequest,
    CateringRequestListResponse,
    Contact,
    ContactListResponse,
    CreateCateringRequestRequest,
    CreateContactRequest,
    EventBridgeEvent,
    UpdateCateringRequestRequest,
)
from services.auth_types import UserContext

from . import _implementation

catering_router = APIRouter(prefix=endpoints.CATERING, tags=["Catering"])


@catering_router.post("/events", status_code=status.HTTP_200_OK)
async def handle_catering_event(
    event: EventBridgeEvent,
    session: AsyncSession = Depends(db.get_db_async),
):
    """
    Handle catering events from AWS EventBridge.
    This endpoint receives events with Default Behavior from EventBridge.
    """
    return await _implementation.handle_catering_event(event, session)


@catering_router.post(
    "/projects/{project_id}/requests", status_code=status.HTTP_201_CREATED
)
def create_project_catering_request(
    project_id: uuid.UUID,
    request: CreateCateringRequestRequest,
    context: UserContext = Depends(authenticate_user),
) -> CateringRequest:
    """
    Create a new catering request for a project.
    """
    return _implementation.create_project_catering_request(project_id, request, context)


@catering_router.get("/projects/{project_id}/requests")
def list_project_catering_requests(
    project_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
) -> CateringRequestListResponse:
    """
    List all catering requests for a project.
    """
    return _implementation.list_project_catering_requests(project_id, context)


@catering_router.patch(
    "/requests/{catering_request_id}", status_code=status.HTTP_200_OK
)
async def update_catering_request(
    catering_request_id: uuid.UUID,
    request: UpdateCateringRequestRequest,
    context: UserContext = Depends(authenticate_user),
    session: AsyncSession = Depends(db.get_db_async),
) -> CateringRequest:
    """
    Update an existing catering request.
    """
    return await _implementation.update_catering_request(
        catering_request_id, request, context, session
    )


@catering_router.post(
    "/projects/{project_id}/contacts", status_code=status.HTTP_201_CREATED
)
async def create_project_contact(
    project_id: uuid.UUID,
    request: CreateContactRequest,
    context: UserContext = Depends(authenticate_user),
    session: AsyncSession = Depends(db.get_db_async),
) -> Contact:
    """
    Create a new contact for a project.
    """
    return await _implementation.create_project_contact(
        project_id, request, context, session
    )


@catering_router.get("/projects/{project_id}/contacts")
async def list_project_contacts(
    project_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: AsyncSession = Depends(db.get_db_async),
) -> ContactListResponse:
    """
    List all contacts for a project.
    """
    return await _implementation.list_project_contacts(project_id, context, session)


@catering_router.delete("/projects/{project_id}/contacts/{contact_id}")
async def delete_project_contact(
    project_id: uuid.UUID,
    contact_id: uuid.UUID,
    context: UserContext = Depends(authenticate_user),
    session: AsyncSession = Depends(db.get_db_async),
):
    """
    Delete a contact from a project.
    """
    return await _implementation.delete_project_contact(
        project_id, contact_id, context, session
    )
