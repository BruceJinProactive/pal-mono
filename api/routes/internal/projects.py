"""Internal API endpoints for project updates."""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pinecone import Pinecone
from pinecone.exceptions import PineconeException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from api.schemas.operations.signal_source import SignalSourceIdResponse
from db.repositories.project_repository import ProjectRepository
from db.tables.types import IntegrationProvider, IntegrationType
from services import knowledge_service, project_service, signal_source_service
from utils.log import logger
from utils.secret import get_client_secret

# Pinecone eventual consistency settings
NAMESPACE_RETRY_DELAY_SECONDS = 2.0
NAMESPACE_POPULATE_MAX_ATTEMPTS = 5


async def _ensure_namespace_deleted(
    index_name: str,
    namespace: str,
    retry_delay: float = NAMESPACE_RETRY_DELAY_SECONDS,
) -> None:
    """
    Ensure a Pinecone namespace is fully deleted by retrying deletion.

    Waits, then attempts to delete again. If deletion fails because
    namespace doesn't exist, we know it's gone and can proceed.

    Args:
        index_name: Name of the Pinecone index
        namespace: Namespace to delete
        retry_delay: Seconds to wait before retry
    """
    try:
        pc = Pinecone()
        index = pc.Index(index_name)

        # Mandatory wait for deletion to propagate
        await asyncio.sleep(retry_delay)

        # Try to delete again - if it fails with 404, namespace is gone
        try:
            index.delete(delete_all=True, namespace=namespace)
            logger.debug(
                f"[Adora Menu Updater] Second delete succeeded for namespace '{namespace}' - proceeding with indexing"
            )
        except PineconeException as e:
            # Check if it's a 404 (namespace not found) - this is expected
            if "(404)" in str(e) or "Not Found" in str(e):
                logger.debug(
                    f"[Adora Menu Updater] Namespace '{namespace}' confirmed deleted (404 not found) - proceeding with indexing"
                )
            else:
                # Real error (network, auth, 5xx) - log warning but still proceed
                logger.warning(
                    f"[Adora Menu Updater] Unexpected Pinecone error during second delete for namespace '{namespace}': {e} - proceeding with indexing anyway",
                    extra={"index_name": index_name, "namespace": namespace},
                )

        # Additional delay before indexing to ensure deletion is fully propagated
        await asyncio.sleep(retry_delay)

    except PineconeException as e:
        logger.warning(
            f"[Adora Menu Updater] Pinecone error ensuring namespace deleted: {e}",
            extra={"index_name": index_name, "namespace": namespace},
        )
        # Proceed anyway
    except Exception as e:
        logger.warning(
            f"[Adora Menu Updater] Unexpected error ensuring namespace deleted: {e}",
            extra={"index_name": index_name, "namespace": namespace},
        )
        # Proceed anyway


async def _verify_namespace_populated(
    index_name: str,
    namespace: str,
    retry_delay: float = NAMESPACE_RETRY_DELAY_SECONDS,
) -> bool:
    """
    Verify that a Pinecone namespace has been populated with vectors.

    Args:
        index_name: Name of the Pinecone index
        namespace: Namespace to check
        retry_delay: Seconds to wait before checking

    Returns:
        bool: True if namespace exists and has vectors, False if not populated

    Raises:
        PineconeException: For Pinecone infrastructure errors (should be 500)
        Exception: For unexpected errors (should be 500)
    """
    pc = Pinecone()
    index = pc.Index(index_name)

    # Wait before checking
    await asyncio.sleep(retry_delay)

    stats = index.describe_index_stats()
    namespaces = stats.get("namespaces", {})

    if namespace not in namespaces:
        logger.warning(
            f"[Adora Menu Updater] Namespace '{namespace}' not found after indexing",
            extra={"index_name": index_name, "namespace": namespace},
        )
        return False

    vector_count = namespaces[namespace].get("vector_count", 0)
    if vector_count == 0:
        logger.warning(
            f"[Adora Menu Updater] Namespace '{namespace}' exists but has 0 vectors",
            extra={"index_name": index_name, "namespace": namespace},
        )
        return False

    logger.info(
        f"[Adora Menu Updater] Namespace '{namespace}' verified with {vector_count} vectors",
        extra={
            "index_name": index_name,
            "namespace": namespace,
            "vector_count": vector_count,
        },
    )
    return True


projects_router = APIRouter(prefix="/projects")


class UpdateBusinessHoursRequest(BaseModel):
    """Request model for updating business hours from Google Places API."""

    source: str
    place_id: str | None = None
    last_fetched: str
    regular_hours: Dict[str, Any] | None = None
    special_hours: list | None = None
    formatted_phone_number: str | None = None
    phone_number: str | None = None
    website: str | None = None


@projects_router.get(
    "/{project_id}/signal-sources/camera",
    response_model=SignalSourceIdResponse,
    responses={
        404: {"description": "Signal source not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_signal_source_by_camera_id(
    project_id: str,
    camera_id: str = Query(
        ..., description="Camera identifier from signal source config"
    ),
    session: AsyncSession = Depends(db.get_db_async),
) -> SignalSourceIdResponse:
    """
    Internal endpoint: Get signal source ID by camera_id.

    Called by Lambda functions (e.g., Monitoring Image Processor) to lookup
    signal_source_id using camera_id for further processing.

    Args:
        project_id: UUID of the project
        camera_id: Camera identifier from signal source configuration
        session: Async database session

    Returns:
        SignalSourceIdResponse with signal_source_id

    Raises:
        400: Invalid project_id format
        404: Signal source not found
        500: Database error
    """
    try:
        # Validate and convert project_id to UUID
        try:
            project_uuid = uuid.UUID(project_id)
        except ValueError:
            logger.warning(
                f"[Internal API] Invalid project_id format: {project_id}",
                extra={"project_id": project_id, "camera_id": camera_id},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid project_id format: {project_id}",
                headers={"Content-Type": "application/json"},
            )

        # Get signal source by camera_id
        source = await signal_source_service.get_source_by_camera_id(
            session=session,
            project_id=project_uuid,
            camera_id=camera_id,
        )

        if not source:
            logger.warning(
                f"[Internal API] Signal source not found for camera_id: {camera_id}",
                extra={"project_id": project_id, "camera_id": camera_id},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signal source with camera_id '{camera_id}' not found in project {project_id}",
                headers={"Content-Type": "application/json"},
            )

        logger.info(
            f"[Internal API] Found signal source for camera_id: {camera_id}",
            extra={
                "project_id": project_id,
                "camera_id": camera_id,
                "signal_source_id": str(source.id),
            },
        )

        return SignalSourceIdResponse(signal_source_id=source.id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "[Internal API] Error getting signal source by camera_id",
            exc_info=True,
            extra={"project_id": project_id, "camera_id": camera_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get signal source: {str(e)}",
            headers={"Content-Type": "application/json"},
        )


@projects_router.post("/{project_id}/business-hours")
async def update_project_business_hours(
    project_id: str,
    request: UpdateBusinessHoursRequest,
    session: Session = Depends(db.get_db),
):
    """
    Update project (store location) business hours.

    Called by Lambda after fetching hours from Google Places API.
    Updates both structured hours (JSONB) and human-readable text.

    Args:
        project_id: UUID of the project to update
        request: Business hours data from Google Places API
        session: Database session

    Returns:
        dict: Update result with success status and change detection
    """
    project_repo = ProjectRepository(session)

    try:
        # Convert project_id to UUID
        try:
            project_uuid = uuid.UUID(project_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid project_id format: {project_id}",
                headers={"Content-Type": "application/json"},
            )

        # Get project
        project = project_repo.get_project(project_uuid)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project {project_id} not found",
                headers={"Content-Type": "application/json"},
            )

        # Convert request to dict for storage
        new_hours_data = request.model_dump()

        # Check if hours actually changed
        old_hours_data = project.business_hours or {}
        hours_changed = _hours_have_changed(old_hours_data, new_hours_data)

        # Check if phone changed
        old_phone = old_hours_data.get("formatted_phone_number")
        new_phone = new_hours_data.get("formatted_phone_number")
        phone_changed = old_phone != new_phone

        # Update project
        project_repo.update_project_business_hours(
            project_id=project_uuid,
            business_hours=new_hours_data,
            last_updated=datetime.now(timezone.utc),
        )

        logger.info(
            f"[BusinessHoursUpdate] Updated business hours for project {project.name}",
            extra={
                "project_id": project_id,
                "project_name": project.name,
                "hours_changed": hours_changed,
                "phone_changed": phone_changed,
            },
        )

        return {
            "success": True,
            "project_id": project_id,
            "hours_changed": hours_changed,
            "phone_changed": phone_changed,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"[BusinessHoursUpdate] Error updating hours for project {project_id}",
            exc_info=True,
            extra={"project_id": project_id},
        )
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update business hours: {str(e)}",
            headers={"Content-Type": "application/json"},
        )


@projects_router.post("/{project_id}/knowledge-update")
async def update_knowledge(
    project_id: str,
    session: Session = Depends(db.get_db),
):
    """
    Update knowledge base for a specific project.

    Processes knowledge update for a single project with Adora POS integration.
    Fetches menu data from Adora API and updates the Pinecone knowledge base.
    Called by Lambda function consuming knowledge update events.

    Args:
        project_id: UUID of the project to update
        session: Database session

    Returns:
        dict: Status of the update operation including items processed
    """
    logger.debug(
        f"[Adora Menu Updater] Starting knowledge update for project {project_id}"
    )

    try:
        # Validate and convert project_id to UUID
        try:
            project_uuid = uuid.UUID(project_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid project_id format: {project_id}",
                headers={"Content-Type": "application/json"},
            )

        # Get project
        project = project_service.get_project(session, project_uuid)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project {project_id} not found",
                headers={"Content-Type": "application/json"},
            )

        # Get index_name and namespace with priority:
        # 1. adora_v2_tool from project_integration (config column)
        # 2. adora_v2_tool from raw_config
        # 3. adora_tool from raw_config (legacy fallback)

        pinecone_index_name = None
        pinecone_namespace = None
        tool_source = None

        # Check project_integration for adora_v2_tool
        project_integration_repository = db.ProjectIntegrationRepository(session)
        project_integrations = (
            project_integration_repository.get_project_integrations_by_project_id(
                project_uuid
            )
        )

        for pi in project_integrations:
            if pi.tool_name == "adora_v2_tool":
                pi_config = pi.config or {}
                pinecone_namespace = pi_config.get("namespace")
                pinecone_index_name = pi_config.get("index_name")
                tool_source = "project_integration.adora_v2_tool"
                logger.debug(
                    "[Adora Menu Updater] Found adora_v2_tool in project_integration",
                    extra={
                        "project_id": project_id,
                        "namespace": pinecone_namespace,
                        "index_name": pinecone_index_name,
                    },
                )
                break

        # Check raw_config for adora_v2_tool, then adora_tool
        if not pinecone_namespace or not pinecone_index_name:
            raw_config = project.raw_config or {}
            tools_config = raw_config.get("tools", {})
            identifiers = tools_config.get("identifiers") or []

            # First try adora_v2_tool in raw_config
            for identifier in identifiers:
                if (
                    isinstance(identifier, dict)
                    and identifier.get("tool_name") == "adora_v2_tool"
                ):
                    tool_args = identifier.get("tool_args", {})
                    pinecone_namespace = pinecone_namespace or tool_args.get(
                        "namespace"
                    )
                    pinecone_index_name = pinecone_index_name or tool_args.get(
                        "index_name"
                    )
                    tool_source = tool_source or "raw_config.adora_v2_tool"
                    break

            # Fallback to adora_tool in raw_config (legacy)
            if not pinecone_namespace or not pinecone_index_name:
                for identifier in identifiers:
                    if (
                        isinstance(identifier, dict)
                        and identifier.get("tool_name") == "adora_tool"
                    ):
                        tool_args = identifier.get("tool_args", {})
                        pinecone_namespace = pinecone_namespace or tool_args.get(
                            "namespace"
                        )
                        pinecone_index_name = pinecone_index_name or tool_args.get(
                            "index_name"
                        )
                        tool_source = tool_source or "raw_config.adora_tool"
                        break

        logger.debug(
            f"[Adora Menu Updater] Resolved tool config from {tool_source}",
            extra={
                "project_id": project_id,
                "tool_source": tool_source,
                "namespace": pinecone_namespace,
                "index_name": pinecone_index_name,
            },
        )

        if not pinecone_index_name:
            raise ValueError(
                f"Project {project_id} does not have index_name configured (checked project_integration.adora_v2_tool, raw_config.adora_v2_tool, raw_config.adora_tool)"
            )

        if not pinecone_namespace:
            raise ValueError(
                f"Project {project_id} does not have namespace configured (checked project_integration.adora_v2_tool, raw_config.adora_v2_tool, raw_config.adora_tool)"
            )

        # Find the Adora POS integration (reusing project_integrations from above)
        pos_project_integration = None
        pos_integration = None
        integration_repository = db.IntegrationRepository(session)
        for pi in project_integrations:
            integration = integration_repository.get_integration_by_id(
                project.account_id, pi.integration_id
            )
            if (
                integration
                and integration.integration_type == IntegrationType.pos
                and integration.provider == IntegrationProvider.adora
            ):
                pos_project_integration = pi
                pos_integration = integration
                break

        if not pos_project_integration or not pos_integration:
            raise ValueError(
                f"Project {project_id} does not have an Adora POS integration"
            )

        # Get store identifier
        store_id = pos_project_integration.store_identifier
        if not store_id:
            raise ValueError(
                f"Project {project_id} integration does not have a store_identifier"
            )

        # Get credentials from AWS Secrets Manager
        secret_key = pos_integration.secret_key
        if not secret_key:
            raise ValueError(
                f"Adora integration for project {project_id} does not have a secret_key"
            )

        try:
            secrets_json = get_client_secret(secret_key)
            credentials = json.loads(secrets_json)
            client_id = (credentials.get("client_id") or "").strip()
            client_secret = (credentials.get("client_secret") or "").strip()
        except ClientError:
            raise ValueError(f"Secret '{secret_key}' not found in AWS Secrets Manager")
        except (KeyError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid secret format for key '{secret_key}': {e}")

        if not client_id:
            raise ValueError("Adora client_id missing in secret manager")
        if not client_secret:
            raise ValueError("Adora client_secret missing in secret manager")

        # Get API endpoints from integration raw_config
        integration_config = pos_integration.raw_config or {}
        api_endpoints = integration_config.get("api_endpoints", {}) or {}
        token_api_endpoint = (api_endpoints.get("token_api_endpoint") or "").strip()
        general_api_endpoint = (api_endpoints.get("general_api_endpoint") or "").strip()

        if not token_api_endpoint:
            raise ValueError("Adora token_api_endpoint missing in integration config")
        if not general_api_endpoint:
            raise ValueError("Adora general_api_endpoint missing in integration config")

        logger.debug(
            f"[Adora Menu Updater] Updating menu for project {project_id}",
            extra={
                "project_id": project_id,
                "project_name": project.name,
                "store_id": store_id,
                "pinecone_index": pinecone_index_name,
                "pinecone_namespace": pinecone_namespace,
            },
        )

        # Delete existing vectors in namespace before re-indexing
        # This prevents duplicate vectors since LlamaIndex generates new IDs each run
        try:
            delete_result = knowledge_service.delete_namespace(
                pinecone_index_name, pinecone_namespace
            )
            logger.debug(
                "[Adora Menu Updater] Cleared namespace before re-indexing",
                extra={
                    "project_id": project_id,
                    "pinecone_namespace": pinecone_namespace,
                    "delete_result": delete_result,
                },
            )
            # Wait for deletion to propagate (Pinecone eventual consistency)
            await _ensure_namespace_deleted(pinecone_index_name, pinecone_namespace)
        except Exception as e:
            # Log but don't fail - namespace might not exist yet or be empty
            logger.warning(
                f"[Adora Menu Updater] Could not clear namespace (may be empty): {e}",
                extra={
                    "project_id": project_id,
                    "pinecone_namespace": pinecone_namespace,
                },
            )

        # Call knowledge service to update the menu with retry logic
        result: dict = {}
        namespace_populated = False

        for attempt in range(1, NAMESPACE_POPULATE_MAX_ATTEMPTS + 1):
            logger.info(
                f"[Adora Menu Updater] Indexing attempt {attempt}/{NAMESPACE_POPULATE_MAX_ATTEMPTS} for project {project_id}",
                extra={
                    "project_id": project_id,
                    "pinecone_namespace": pinecone_namespace,
                    "attempt": attempt,
                },
            )

            result = knowledge_service.update_agent_kb(
                pos_provider=IntegrationProvider.adora,
                store_id=store_id,
                client_id=client_id,
                client_secret=client_secret,
                token_api_endpoint=token_api_endpoint,
                general_api_endpoint=general_api_endpoint,
                pinecone_namespace=pinecone_namespace,
                pinecone_index_name=pinecone_index_name,
                debug=False,
                include_category_in_doc_name=False,
            )

            # Verify namespace was populated (2x delay for populate check)
            if await _verify_namespace_populated(
                pinecone_index_name,
                pinecone_namespace,
                retry_delay=NAMESPACE_RETRY_DELAY_SECONDS * 2,
            ):
                namespace_populated = True
                break

            # Log retry if more attempts remaining
            if attempt < NAMESPACE_POPULATE_MAX_ATTEMPTS:
                logger.warning(
                    f"[Adora Menu Updater] Indexing attempt {attempt} failed for project {project_id}, retrying...",
                    extra={
                        "project_id": project_id,
                        "pinecone_namespace": pinecone_namespace,
                        "attempt": attempt,
                    },
                )

        if not namespace_populated:
            raise ValueError(
                f"Failed to populate namespace '{pinecone_namespace}' after {NAMESPACE_POPULATE_MAX_ATTEMPTS} attempts"
            )

        # Update project's product_info with the system_prompt_menu
        system_prompt_menu = result.get("system_prompt_menu", "")
        product_info_updated = False
        project_repo = ProjectRepository(session)
        if system_prompt_menu:
            project_repo.update_project(project_uuid, product_info=system_prompt_menu)
            product_info_updated = True
            logger.debug(
                f"[Adora Menu Updater] Updated product_info for project {project_id}",
                extra={
                    "project_id": project_id,
                    "product_info_length": len(system_prompt_menu),
                },
            )

        # Update menu_last_updated in project's raw_config
        # Use update_project_config which fetches fresh data to avoid clobbering concurrent changes
        menu_last_updated = datetime.now(timezone.utc).isoformat()
        project_repo.update_project_config(
            project_uuid, {"menu_last_updated": menu_last_updated}
        )
        logger.debug(
            f"[Adora Menu Updater] Updated menu_last_updated for project {project_id}",
            extra={
                "project_id": project_id,
                "menu_last_updated": menu_last_updated,
            },
        )

        logger.debug(
            f"[Adora Menu Updater] Knowledge update complete for project {project_id}",
            extra={
                "project_id": project_id,
                "project_name": project.name,
                "items_processed": result.get("processed_items", 0),
                "product_info_updated": product_info_updated,
            },
        )

        return {
            "success": True,
            "project_id": project_id,
            "project_name": project.name,
            "pinecone_index_name": pinecone_index_name,
            "pinecone_namespace": pinecone_namespace,
            "items_processed": result.get("processed_items", 0),
            "product_info_updated": product_info_updated,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(
            f"[Adora Menu Updater] Validation error for project {project_id}: {e}",
            extra={"project_id": project_id},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        logger.error(
            f"[Adora Menu Updater] Error updating knowledge for project {project_id}",
            exc_info=True,
            extra={"project_id": project_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update knowledge base: {str(e)}",
            headers={"Content-Type": "application/json"},
        )


def _hours_have_changed(old_data: Dict[str, Any], new_data: Dict[str, Any]) -> bool:
    """
    Compare old and new hours data to detect changes.

    Ignores last_fetched timestamp for comparison.

    Args:
        old_data: Previous business hours data
        new_data: New business hours data

    Returns:
        bool: True if hours have changed, False otherwise
    """
    # Remove timestamps for comparison
    old_compare = {k: v for k, v in old_data.items() if k != "last_fetched"}
    new_compare = {k: v for k, v in new_data.items() if k != "last_fetched"}

    return old_compare != new_compare
