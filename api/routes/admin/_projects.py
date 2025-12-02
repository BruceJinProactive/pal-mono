import uuid

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from api.schemas.admin.project import (
    BatchCreateProjectsRequest,
    BatchCreateProjectsResponse,
    BatchDeleteProjectsRequest,
    BatchDeleteProjectsResponse,
    BatchUpdateProjectsRequest,
    BatchUpdateProjectsResponse,
    CreateProjectRequest,
    Project,
    ProjectCreationResult,
    ProjectDeletionResult,
    ProjectUpdateResult,
    UpdateProjectRequest,
)
from db.repositories.voice_config_repository import VoiceConfigRepository
from services import (
    account_service,
    agent_service,
    project_service,
    subscription_service,
)
from services.admin_service import (
    deauthorize_instagram_access_token,
    get_instagram_connected,
    get_instagram_username,
    remove_instagram_access_token,
    set_instagram_access_token,
)
from utils.log import logger

from . import UserContext, _utils
from ._auth import authorize_admin
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
    return build_project(project)


async def create_project(
    create_request: CreateProjectRequest,
    context: UserContext,
    session: Session,
) -> Project:
    project_params = create_request.to_project_params()
    try:
        db_project = project_service.create_project(
            session,
            context,
            create_request.account_name,
            create_request.name,
            project_params,
        )

        # If subscription_id is provided, add the project to the subscription
        if create_request.subscription_id:
            try:
                subscription_service.create_project_subscription(
                    session, db_project, create_request.subscription_id
                )
            except ValueError as subscription_err:
                logger.warning(
                    f"Project created but failed to add to subscription: {subscription_err}",
                    extra={
                        "project_id": str(db_project.id),
                        "subscription_id": str(create_request.subscription_id),
                        "account_name": create_request.account_name,
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Project created successfully, but failed to add to subscription: {subscription_err}",
                    headers={"Content-Type": "application/json"},
                )
            except Exception as subscription_err:
                logger.error(
                    f"Project created but unexpected error adding to subscription: {subscription_err}",
                    extra={
                        "project_id": str(db_project.id),
                        "subscription_id": str(create_request.subscription_id),
                        "account_name": create_request.account_name,
                    },
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Project created successfully, but failed to add to subscription due to an internal error.",
                    headers={"Content-Type": "application/json"},
                )

        # Create default voice config if project has no voice configs
        voice_repo = VoiceConfigRepository(session, auto_commit=True)
        existing_voice_configs = voice_repo.get_voice_configs_by_project(db_project.id)

        if not existing_voice_configs:
            default_voice_id = "da69d796-4603-4419-8a95-293bfc5679eb"
            voice_repo.create_voice_config(
                project_id=db_project.id,
                language="english",
                voice_id=default_voice_id,
                first_message=f"Hello, this is {create_request.name} AI Agent, how can I help you today?!",
                transfer_message="",
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
    project_params = update_request.to_project_params()
    try:
        db_project = project_service.update_project(
            session,
            context,
            project_id,
            project_params,
            update_request.expected_version,
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
                session, project.id, curr_sub.external_id
            )

        # Delete all voice configs for this project
        voice_repo = VoiceConfigRepository(session, auto_commit=False)
        deleted_voice_configs = voice_repo.delete_voice_configs_by_project(project_id)
        logger.info(
            f"Deleted {deleted_voice_configs} voice configs for project {project.name}"
        )

        project_service.delete_project(session, context, project_id)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(
            f"Failed to remove project {project.name} to account subscription: {e}",
            extra={
                "project_id": str(project.id),
                "account_id": str(project.account_id),
            },
            exc_info=True,
        )
        raise


async def batch_create_projects(
    request: BatchCreateProjectsRequest, context: UserContext, session: Session
) -> BatchCreateProjectsResponse:
    """
    Create multiple projects for an account.
    """
    authorize_admin(context)

    account = account_service.get_account(session, request.account_name)
    if not account:
        raise not_found_error(f"Account '{request.account_name}' not found.")

    agent_obj = agent_service.get_agent(session, request.agent_id)
    if not agent_obj or agent_obj.account_id != account.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent {request.agent_id} not found or not associated with account {request.account_name}",
        )

    try:
        location_data = []
        for location in request.locations:
            params = location.to_project_params(request.agent_id)
            location_data.append(params)

        result = project_service.batch_create_projects(
            session=session,
            context=context,
            account_name=request.account_name,
            agent_id=request.agent_id,
            location_data=location_data,
            auto_commit=True,
        )

        creation_results = []
        for res in result["results"]:
            creation_results.append(
                ProjectCreationResult(
                    project_name=res["project_name"],
                    project_id=(
                        uuid.UUID(res["project_id"]) if res["project_id"] else None
                    ),
                    display_name=res.get("display_name"),
                    success=res["success"],
                    error_message=res.get("error_message"),
                )
            )

        return BatchCreateProjectsResponse(
            account_name=result["account_name"],
            total_requested=result["total_requested"],
            total_created=result["total_created"],
            total_failed=result["total_failed"],
            results=creation_results,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Batch project creation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during batch project creation",
        )


async def batch_update_projects(
    request: BatchUpdateProjectsRequest, context: UserContext, session: Session
) -> BatchUpdateProjectsResponse:
    """
    Update multiple projects for an account.
    """
    authorize_admin(context)

    account = account_service.get_account(session, request.account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{request.account_name}' not found.",
        )

    try:
        update_data = []
        for project_update in request.project_updates:
            update_dict = {
                "project_id": project_update.project_id,
                "project_params": project_update.to_project_params(),
                "expected_version": project_update.expected_version,
            }
            update_data.append(update_dict)

        result = project_service.batch_update_projects(
            session=session,
            context=context,
            account_name=request.account_name,
            project_updates=update_data,
            auto_commit=True,
        )

        update_results = []
        for res in result["results"]:
            update_results.append(
                ProjectUpdateResult(
                    project_id=(
                        uuid.UUID(res["project_id"]) if res["project_id"] else None
                    ),
                    project_name=res["project_name"],
                    display_name=res.get("display_name"),
                    success=res["success"],
                    error_message=res.get("error_message"),
                )
            )

        return BatchUpdateProjectsResponse(
            account_name=result["account_name"],
            total_requested=result["total_requested"],
            total_updated=result["total_updated"],
            total_failed=result["total_failed"],
            results=update_results,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Batch project update failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during batch project update",
        )


async def batch_delete_projects(
    request: BatchDeleteProjectsRequest, context: UserContext, session: Session
) -> BatchDeleteProjectsResponse:
    """
    Delete multiple projects for an account.
    """
    authorize_admin(context)

    account = account_service.get_account(session, request.account_name)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account '{request.account_name}' not found.",
        )

    try:
        result = project_service.batch_delete_projects(
            session=session,
            context=context,
            account_name=request.account_name,
            project_ids=request.project_ids,
            auto_commit=True,
        )

        deletion_results = []
        for res in result["results"]:
            deletion_results.append(
                ProjectDeletionResult(
                    project_id=uuid.UUID(res["project_id"]),
                    project_name=res["project_name"],
                    success=res["success"],
                    error_message=res.get("error_message"),
                )
            )

        return BatchDeleteProjectsResponse(
            account_name=result["account_name"],
            total_requested=result["total_requested"],
            total_deleted=result["total_deleted"],
            total_failed=result["total_failed"],
            results=deletion_results,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Batch project deletion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during batch project deletion",
        )
