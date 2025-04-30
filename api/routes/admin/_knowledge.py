import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import db
from api.schemas.admin.knowledge import ListKnowledgeFileResponse, ResourceType
from services import admin_service, agent_service, project_service
from utils.log import logger

from . import UserContext, _auth
from ._utils import not_found_error


async def get_project_knowledge_files(
    resource: ResourceType,
    resource_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> ListKnowledgeFileResponse:
    """
    Retrieve a list of knowledge file names for a specific project.
    This endpoint gets the knowledge settings from the project's raw_config
    and uses them to query the Pinecone index for all files.
    """
    target = get_and_authorize(resource, resource_id, context, session)

    try:
        file_names = admin_service.list_knowledge_files(session, target)
        return ListKnowledgeFileResponse(
            files=file_names,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except RuntimeError as e:
        logger.error(f"Error retrieving knowledge files: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving knowledge files: {str(e)}",
        )


async def upload_knowledge_file(
    resource: ResourceType,
    resource_id: uuid.UUID,
    file_name: str,
    content: bytes,
    context: UserContext,
    session: Session,
):
    """
    Upload a text file to the project's knowledge base.
    This endpoint gets the knowledge settings from the project's raw_config,
    generates embeddings for the text content, and stores them in Pinecone.
    """
    target = get_and_authorize(resource, resource_id, context, session)
    try:
        result = admin_service.upload_knowledge_file(
            session, target, file_name, content
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


async def delete_knowledge_file(
    resource: ResourceType,
    resource_id: uuid.UUID,
    filename: str,
    context: UserContext,
    session: Session,
) -> str:
    target = get_and_authorize(resource, resource_id, context, session)
    try:
        ids_deleted = admin_service.delete_knowledge_file(session, target, filename)
        return f"Deleted {len(ids_deleted)} embeddings for the file {filename}"
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


def get_and_authorize(
    resource: ResourceType,
    resource_id: uuid.UUID,
    context: UserContext,
    session: Session,
) -> db.Project | db.Agent:
    if resource == ResourceType.Project:
        project = project_service.get_project(session, resource_id)
        if not project:
            raise not_found_error("Project not found")
        _auth.authorize_user_account(context, project.account.name)
        return project
    elif resource == ResourceType.Agent:
        agent = agent_service.get_agent(session, resource_id)
        if not agent:
            raise not_found_error("Agent not found")
        _auth.authorize_user_account(context, agent.account.name)
        return agent
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid resource type: {resource.value}",
        )
