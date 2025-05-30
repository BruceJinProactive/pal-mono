import uuid

from fastapi import Response, status
from sqlalchemy.orm import Session

from api.routes.admin._utils import UserContext, not_found_error
from api.schemas.admin.order_integration import CreateOrderIntegrationRequest
from services import admin_service, project_service

from ._auth import authorize_user_account


async def set_project_order_integration(
    context: UserContext,
    session: Session,
    project_id: uuid.UUID,
    request: CreateOrderIntegrationRequest,
):
    project = project_service.get_project(session, project_id)
    if not project:
        raise not_found_error(f"Project {project_id} not found")
    authorize_user_account(context, project.account.name)

    admin_service.setup_project_order_integration(
        session=session,
        context=context,
        project=project,
        protocol=request.order_protocol,
        destination=request.destination,
        vendor=request.vendor,
    )
    return Response(status_code=status.HTTP_200_OK)
