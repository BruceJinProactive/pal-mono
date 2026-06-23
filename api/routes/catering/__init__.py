import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.routes.admin._auth import authenticate_user
from api.routes.endpoints import endpoints
from api.schemas.catering.catering import (
    CateringMenuItem,
    CateringMenuItemListResponse,
    CateringRequest,
    CateringRequestListResponse,
    Contact,
    ContactListResponse,
    CreateCateringRequestRequest,
    CreateContactRequest,
    EventBridgeEvent,
    PublicCateringRequest,
    UpdateCateringMenuItemRequest,
    UpdateCateringRequestRequest,
    UpdateContactRequest,
)
from api.schemas.error.error import ErrorResponse
from services.auth_service.dependencies import require_project_permission
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
async def create_project_catering_request(
    project_id: uuid.UUID,
    request: CreateCateringRequestRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> CateringRequest:
    """
    Create a new catering request for a project.
    """
    return await _implementation.create_project_catering_request(
        project_id, request, context, session
    )


@catering_router.get("/projects/{project_id}/requests")
async def list_project_catering_requests(
    project_id: uuid.UUID,
    include_activities: bool = False,
    activity_limit: int = Query(default=50, ge=1, le=100),
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> CateringRequestListResponse:
    """
    List all catering requests for a project.
    """
    return await _implementation.list_project_catering_requests(
        project_id, include_activities, activity_limit, context, session
    )


@catering_router.get(
    endpoints.CATERING_PROJECT_MENU_ITEMS,
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_project_catering_menu_items(
    project_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> CateringMenuItemListResponse:
    """
    List catering menu items for a project.
    """
    return await _implementation.list_project_catering_menu_items(
        project_id, context, session
    )


@catering_router.get("/requests/{catering_request_id}/public")
async def get_public_catering_request(
    catering_request_id: uuid.UUID,
    session: AsyncSession = Depends(db.get_db_async),
) -> PublicCateringRequest:
    """
    Get public-safe details for a catering request.
    """
    return await _implementation.get_public_catering_request(
        catering_request_id, session
    )


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


@catering_router.patch(
    endpoints.CATERING_PROJECT_MENU_ITEM,
    status_code=status.HTTP_200_OK,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_catering_menu_item(
    project_id: uuid.UUID,
    menu_item_id: uuid.UUID,
    request: UpdateCateringMenuItemRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> CateringMenuItem:
    """
    Update an existing catering menu item.
    """
    return await _implementation.update_catering_menu_item(
        project_id, menu_item_id, request, context, session
    )


@catering_router.delete(
    "/projects/{project_id}/requests/{catering_request_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_catering_request(
    project_id: uuid.UUID,
    catering_request_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
):
    """
    Delete an existing catering request.
    """
    return await _implementation.delete_catering_request(
        project_id, catering_request_id, context, session
    )


@catering_router.post(
    "/projects/{project_id}/contacts", status_code=status.HTTP_201_CREATED
)
async def create_project_contact(
    project_id: uuid.UUID,
    request: CreateContactRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
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
    context: UserContext = Depends(
        require_project_permission("project.read", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> ContactListResponse:
    """
    List all contacts for a project.
    """
    return await _implementation.list_project_contacts(project_id, context, session)


@catering_router.patch("/projects/{project_id}/contacts/{contact_id}")
async def update_project_contact(
    project_id: uuid.UUID,
    contact_id: uuid.UUID,
    request: UpdateContactRequest,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> Contact:
    """
    Update a contact for a project.
    """
    return await _implementation.update_project_contact(
        project_id, contact_id, request, session
    )


@catering_router.delete("/projects/{project_id}/contacts/{contact_id}")
async def delete_project_contact(
    project_id: uuid.UUID,
    contact_id: uuid.UUID,
    context: UserContext = Depends(
        require_project_permission("project.write", authenticate_user)
    ),
    session: AsyncSession = Depends(db.get_db_async),
):
    """
    Delete a contact from a project.
    """
    return await _implementation.delete_project_contact(
        project_id, contact_id, context, session
    )
