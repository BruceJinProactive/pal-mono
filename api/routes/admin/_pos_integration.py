import uuid

from fastapi import Response, status
from sqlalchemy.orm import Session

from api.routes.admin._utils import UserContext, not_found_error
from api.schemas.admin.pos_integration import CreatePOSIntegrationRequest
from services import project_service
from services.integration_service import pos_integration

from ._auth import authorize_user_account


async def set_project_pos_integration(
    context: UserContext,
    session: Session,
    project_id: uuid.UUID,
    request: CreatePOSIntegrationRequest,
):
    project = project_service.get_project(session, project_id)
    if not project:
        raise not_found_error(f"Project {project_id} not found")
    authorize_user_account(context, project.account.name)

    pos_integration.setup_project_pos_integration(
        session=session,
        context=context,
        project=project,
        store_identifier=request.store_identifier,
        provider=request.provider,
        state=request.state,
    )
    return Response(status_code=status.HTTP_200_OK)
