import json
import time
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import db
from api.schemas.admin.integration import IntegrationType
from api.schemas.admin.knowledge import (
    KnowledgeFile,
    ListKnowledgeFileResponse,
    ResourceType,
)
from db.tables.types import IntegrationProvider
from services import admin_service, agent_service, knowledge_service, project_service
from services.auth_service import check_permission
from services.auth_types import UserRole
from utils.log import logger
from utils.secret import get_client_secret

from . import UserContext, _auth
from ._utils import not_found_error


async def get_project_knowledge_files(
    resource: ResourceType,
    resource_id: uuid.UUID,
    filename: str | None,
    page: int,
    page_size: int,
    context: UserContext,
    session: Session,
) -> ListKnowledgeFileResponse:
    """
    Retrieve a list of knowledge file names for a specific project.
    This endpoint gets the knowledge settings from the project's raw_config
    and uses them to query the Pinecone index for all files.
    Optionally filter the results by filename (case-insensitive partial match).
    """
    target = get_and_authorize(resource, resource_id, context, session)

    try:
        total, file_data = admin_service.list_knowledge_files(
            session,
            context,
            target,
            filename,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        files = [
            KnowledgeFile(
                name=file.name,
                size_bytes=file.size,
                created_at=file.created_at,
            )
            for file in file_data
        ]

        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return ListKnowledgeFileResponse(
            files=files,
            total_files=total,
            total_pages=total_pages,
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
            session, context, target, file_name, content
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
        ids_deleted = admin_service.delete_knowledge_file(
            session, context, target, filename
        )
        return f"Deleted {len(ids_deleted)} embeddings for the file {filename}"
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


def _check_account_access(context: UserContext, account, session: Session) -> None:
    """Check if user has access to the account using RBAC."""
    # Admin has full access
    if context.role == UserRole.Admin:
        return
    # Check permission on account
    user_id = UUID(context.username)
    if not check_permission(user_id, f"accounts/{account.id}", "account.read", session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required permission: account.read",
            headers={"Content-Type": "application/json"},
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
        _check_account_access(context, project.account, session)
        return project
    elif resource == ResourceType.Agent:
        agent = agent_service.get_agent(session, resource_id)
        if not agent:
            raise not_found_error("Agent not found")
        _check_account_access(context, agent.account, session)
        return agent
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid resource type: {resource.value}",
        )


async def update_agent_kb(
    context: UserContext,
    session: Session,
    account_name: str,
    project_id: uuid.UUID,
    pinecone_index_name: str,
    debug: bool = False,
    include_category_in_doc_name: bool = False,
    menu_last_updated: Optional[str] = None,
    selected_menus: Optional[list[str]] = None,
) -> dict:
    """
    Update the knowledge base for an agent by downloading menu data, generating embeddings, and storing in Pinecone.

    Args:
        context: User authentication context
        session: Database session
        account_name: Account name
        project_id: Project UUID
        pinecone_index_name: Pinecone index name for storing embeddings
        debug: Enable debug mode to return additional metadata
        include_category_in_doc_name: Include category name in document names
        menu_last_updated: Last updated date of the menu
        selected_menus: List of menu names to process (optional)
    Returns:
        dict: Contains system_prompt_menu, pinecone_namespace, and pinecone_index_name.
              When debug=True, also includes POS integration details.

    Raises:
        HTTPException: 400 for validation errors, 500 for processing errors
    """
    start_time = time.time()
    try:
        # Authorize the user's access to the admin resource
        _auth.authorize_admin(context)

        # Get the project
        project = project_service.get_project(session, project_id)
        if not project:
            raise not_found_error("Project not found")

        # Get all project integrations for this project
        project_integration_repository = db.ProjectIntegrationRepository(session)
        project_integrations = (
            project_integration_repository.get_project_integrations_by_project_id(
                project_id
            )
        )

        # Find the POS project integration
        pos_project_integration = None
        pos_integration = None
        for pi in project_integrations:
            # Get the integration to check its type
            integration_repository = db.IntegrationRepository(session)
            integration = integration_repository.get_integration_by_id(
                project.account_id, pi.integration_id
            )
            if integration and integration.integration_type == IntegrationType.pos:
                pos_project_integration = pi
                pos_integration = integration
                break

        if not pos_project_integration:
            raise ValueError("POS project integration not found")

        # Get the integration details
        if not pos_integration:
            raise ValueError("POS integration not found")

        # Get the store identifier from the ProjectIntegration
        store_id = pos_project_integration.store_identifier
        if not store_id:
            raise ValueError("Store identifier not found in the project integration")

        # Provider-aware validation and parameter selection
        provider = pos_integration.provider
        cfg = pos_integration.raw_config or {}

        logger.info(
            "[update_agent_kb] Processing menu update",
            extra={
                "account_name": account_name,
                "project_id": str(project_id),
                "provider": provider.value,
                "store_id": store_id,
            },
        )

        if provider in (
            IntegrationProvider.square,
            IntegrationProvider.adora,
            IntegrationProvider.toast,
        ):
            # Square/Adora/Toast: Get credentials from secret manager using secret_key
            secret_key = pos_integration.secret_key
            if not secret_key:
                raise ValueError(
                    f"{provider.value.capitalize()}: secret_key missing in POS integration"
                )

            try:
                secrets_json = get_client_secret(secret_key)
                credentials = json.loads(secrets_json)
            except KeyError:
                raise ValueError(
                    f"{provider.value.capitalize()}: secret_key '{secret_key}' not found in secret manager"
                )
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"{provider.value.capitalize()}: invalid JSON format in secret manager for key '{secret_key}': {e}"
                )

            if provider == IntegrationProvider.square:
                # Square uses OAuth: access_token + location_id (from store_identifier)
                # The location_id is already captured in store_id variable
                access_token = (credentials.get("access_token") or "").strip()
                if not access_token:
                    raise ValueError("Square: access_token missing in secret manager")

                # For Square, pass access token as client_secret_value
                # The knowledge service will use store_id (location_id) + access_token
                client_id_value = ""
                client_secret_value = access_token
                token_api_endpoint = ""
                general_api_endpoint = ""

            else:
                # Adora/Toast use client_id/client_secret and require API endpoints
                client_id_value = (credentials.get("client_id") or "").strip()
                client_secret_value = (credentials.get("client_secret") or "").strip()

                if not client_id_value:
                    raise ValueError(
                        f"{provider.value.capitalize()}: client_id missing in secret manager"
                    )
                if not client_secret_value:
                    raise ValueError(
                        f"{provider.value.capitalize()}: client_secret missing in secret manager"
                    )

                api_endpoints = cfg.get("api_endpoints", {}) or {}
                token_api_endpoint = (
                    api_endpoints.get("token_api_endpoint") or ""
                ).strip()
                general_api_endpoint = (
                    api_endpoints.get("general_api_endpoint") or ""
                ).strip()
                if not token_api_endpoint:
                    raise ValueError(
                        f"{provider.value.capitalize()}: token_api_endpoint missing in raw_config"
                    )
                if not general_api_endpoint:
                    raise ValueError(
                        f"{provider.value.capitalize()}: general_api_endpoint missing in raw_config"
                    )

        elif provider == IntegrationProvider.olo:
            # OLO: require client_id, client_secret and general_api_endpoint only
            # OLO uses signed requests (HMAC), not OAuth tokens, so no token_api_endpoint needed
            client_id_value = (pos_integration.client_id or "").strip()
            client_secret_value = (pos_integration.client_secret or "").strip()
            if not client_id_value:
                raise ValueError("OLO: client_id missing")
            if not client_secret_value:
                raise ValueError("OLO: client_secret missing")

            api_endpoints = cfg.get("api_endpoints", {}) or {}
            token_api_endpoint = ""  # OLO doesn't use token endpoint
            general_api_endpoint = (
                api_endpoints.get("general_api_endpoint") or ""
            ).strip()
            if not general_api_endpoint:
                raise ValueError("OLO: general_api_endpoint missing in raw_config")

        else:
            raise ValueError(f"Unsupported provider for KB update: {provider}")

        # Handle timestamp logic: time + random hex string
        namespace_timestamp = (
            datetime.now().strftime("%Y-%m-%d_%H:%M:%S") + "_" + str(uuid.uuid4())[:4]
        )

        # Get Pinecone settings from project config or use defaults
        pinecone_namespace = f"{project.name}_{store_id}_{namespace_timestamp}"

        # Update the knowledge base for the agent
        return knowledge_service.update_agent_kb(
            pos_integration.provider,
            store_id,
            client_id_value or "",
            client_secret_value or "",
            token_api_endpoint or "",
            general_api_endpoint or "",
            pinecone_namespace,
            pinecone_index_name,
            debug,
            include_category_in_doc_name,
            menu_last_updated,
            selected_menus,
        )
    except ValueError as e:
        logger.warning(
            "[update_agent_kb] Validation error",
            extra={
                "account_name": account_name,
                "project_id": str(project_id),
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error updating knowledge base:\n{str(e)}",
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        logger.error(
            "[update_agent_kb] Failed",
            extra={
                "account_name": account_name,
                "project_id": str(project_id),
                "elapsed_sec": round(time.time() - start_time, 2),
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating knowledge base:\n{str(e)}",
        )


async def delete_vector_database_namespace(
    context: UserContext,
    pinecone_index_name: str,
    pinecone_namespace: str,
) -> dict:
    """
    Delete all vector data from a specific namespace in the Pinecone index.
    This is a direct delete operation that removes all vectors in the specified namespace.

    WARNING: This operation cannot be undone. All vector data in the namespace will be permanently deleted.
    """
    try:
        # Authorize the user's access to the admin resource
        _auth.authorize_admin(context)

        # Validate input parameters
        if not pinecone_index_name or not pinecone_index_name.strip():
            raise ValueError("Pinecone index name cannot be empty")
        if not pinecone_namespace or not pinecone_namespace.strip():
            raise ValueError("Pinecone namespace cannot be empty")

        # Use the knowledge service to delete the namespace
        return knowledge_service.delete_namespace(
            pinecone_index_name, pinecone_namespace
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error deleting namespace: {str(e)}",
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        logger.error(
            f"Error deleting namespace {pinecone_namespace} from index {pinecone_index_name}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting namespace: {str(e)}",
        )


async def query_vector_database_namespace(
    context: UserContext,
    pinecone_index_name: str,
    pinecone_namespace: str,
    query: str,
    top_k: int = 10,
) -> list:
    """
    Query vectors in a specific namespace of the Pinecone index using semantic search.
    This operation performs a semantic search and returns the most relevant results.
    """
    try:
        # Authorize the user's access to the admin resource
        _auth.authorize_admin(context)

        # Validate input parameters
        if not pinecone_index_name or not pinecone_index_name.strip():
            raise ValueError("Pinecone index name cannot be empty")
        if not pinecone_namespace or not pinecone_namespace.strip():
            raise ValueError("Pinecone namespace cannot be empty")
        if not query or not query.strip():
            raise ValueError("Query text cannot be empty")
        if top_k <= 0:
            raise ValueError("top_k must be greater than 0")

        # Use the knowledge service to query the namespace
        try:
            result = knowledge_service.query_vector_database(
                pinecone_index_name, pinecone_namespace, query, top_k
            )
            logger.debug(f"Query returned {len(result) if result else 0} results")
            return result
        except Exception as service_error:
            logger.error(f"Knowledge service error: {service_error}", exc_info=True)
            raise

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error querying namespace: {str(e)}",
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        logger.error(
            f"Error querying namespace {pinecone_namespace} from index {pinecone_index_name}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error querying namespace: {str(e)}",
        )


async def list_namespaces(
    context: UserContext,
    session: Session,
    page: int = 1,
    page_size: int = 50,
    account_name: Optional[str] = None,
    index_name: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> dict:
    """
    List all knowledge base namespaces across all projects.
    Returns namespace information including account, tool, and index details.
    Supports filtering by account name, index name, and tool name.
    """
    try:
        _auth.authorize_admin(context)

        # Delegate to knowledge service for main logic
        namespace_infos = knowledge_service.list_namespaces(
            session=session,
            account_name=account_name,
            index_name=index_name,
            tool_name=tool_name,
        )

        # Apply pagination
        total = len(namespace_infos)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_namespaces = namespace_infos[start_idx:end_idx]
        has_more = end_idx < total

        return {
            "namespaces": [asdict(ns) for ns in paginated_namespaces],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": has_more,
        }

    except Exception as e:
        logger.error(f"Error listing namespaces: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing namespaces: {str(e)}",
        )
