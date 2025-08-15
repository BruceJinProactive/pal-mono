import uuid

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from api.schemas.admin.project import (
    CreateProjectRequest,
    Project,
    UpdateProjectRequest,
)
from services import account_service, project_service, subscription_service
from services.admin_service import (
    deauthorize_instagram_access_token,
    get_instagram_connected,
    get_instagram_username,
    remove_instagram_access_token,
    set_instagram_access_token,
)
from utils.log import logger

from . import UserContext, _auth, _utils
from ._auth import authorize_admin, authorize_user_account
from ._builder import build_project
from ._utils import not_found_error


async def connect_instagram(
    project_id: str,
    request: Request,
    session: Session,
):
    ig_access_token = request.headers.get("Access-Token", "")
    ig_user_id = request.headers.get("User-Id", "")
    ig_username = request.headers.get("Username", "")

    if not all([ig_access_token, ig_user_id, ig_username]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required header(s): Access-Token, Username and/or User-Id",
            headers={"Content-Type": "application/json"},
        )

    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid project UUID",
            headers={"Content-Type": "application/json"},
        )

    try:
        set_instagram_access_token(
            session, project_uuid, ig_access_token, ig_user_id, ig_username
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    return {"message": "Instagram account connected"}


async def disconnect_instagram(
    project_id: uuid.UUID,
    session: Session,
):
    try:
        remove_instagram_access_token(session, project_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    return {"message": "Instagram account disconnected"}


async def get_project_instagram_connected(
    project_id: uuid.UUID,
    session: Session,
):
    try:
        connected = get_instagram_connected(session, project_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    return {"connected": connected}


async def get_project_instagram_username(
    project_id: uuid.UUID,
    session: Session,
):
    # Verify the project is connected to instagram
    try:
        connected = get_instagram_connected(session, project_id)
        if not connected:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not connected to Instagram",
                headers={"Content-Type": "application/json"},
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    try:
        username = get_instagram_username(session, project_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not connected to Instagram",
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    return {"username": username}


async def handle_instagram_deauthorization(
    ig_user_id: str, request: Request, session: Session
):
    encoded_signature = request.headers.get("Encoded-Signature", "")
    encoded_payload = request.headers.get("Encoded-Payload", "")

    # Check for missing headers
    if not all([encoded_signature, encoded_payload]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required headers: Encoded-Signature and/or Encoded-Payload",
            headers={"Content-Type": "application/json"},
        )

    # Verify the incoming request
    try:
        _utils.verify_instagram_deauthorize_signature(
            encoded_payload, encoded_signature
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    try:
        deauthorize_instagram_access_token(session, ig_user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error, please try again later.",
            headers={"Content-Type": "application/json"},
        )

    return {"message": "Instagram account deauthorized"}


async def list_account_projects(
    account_name: str,
    context: UserContext,
    session: Session,
) -> list[Project]:
    authorize_user_account(context, account_name)

    account = account_service.get_account(session, account_name)
    if not account:
        raise not_found_error(f"Account {account_name} not found")

    projects = project_service.get_projects_by_account_id(session, account.id)
    return [build_project(project) for project in projects]


def get_project(
    project_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> Project:
    project = project_service.get_project(session, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    _auth.authorize_user_account(context, project.account.name)
    return build_project(project)


async def create_project(
    create_request: CreateProjectRequest,
    context: UserContext,
    session: Session,
) -> Project:
    authorize_user_account(context, create_request.account_name)
    project_params = create_request.to_project_params()
    try:
        db_project = project_service.create_project(
            session,
            context,
            create_request.account_name,
            create_request.name,
            project_params,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
    return build_project(db_project)


async def update_project(
    project_id: uuid.UUID,
    update_request: UpdateProjectRequest,
    context: UserContext,
    session: Session,
) -> Project:
    project = project_service.get_project(session, project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
            headers={"Content-Type": "application/json"},
        )
    authorize_user_account(context, project.account.name)
    project_params = update_request.to_project_params()
    try:
        db_project = project_service.update_project(
            session, context, project_id, project_params
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
            headers={"Content-Type": "application/json"},
        )
    return build_project(db_project)


async def delete_project(
    project_id: uuid.UUID,
    context: UserContext,
    session: Session,
):
    authorize_admin(context)

    project = project_service.get_project(session, project_id)
    if not project:
        return

    try:
        curr_sub, _ = subscription_service.get_account_subscriptions(
            session, project.account_id
        )
        if curr_sub:
            subscription_service.remove_project_subscription(
                session, project, curr_sub.external_id
            )
        project_service.delete_project(session, context, project_id)
    except Exception as e:
        logger.error(
            f"Failed to remove project {project.name} to account subscription: {e}",
            extra={
                "project_id": str(project.id),
                "account_id": str(project.account_id),
            },
            exc_info=True,
        )
        raise
