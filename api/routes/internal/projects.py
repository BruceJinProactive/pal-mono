"""Internal API endpoints for project updates."""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from pinecone import Pinecone
from pydantic import BaseModel
from sqlalchemy.orm import Session

import db
from db.repositories.project_repository import ProjectRepository
from db.tables.types import IntegrationProvider, IntegrationType
from services import knowledge_service, project_service
from utils.log import logger
from utils.secret import get_client_secret

# Constants for namespace deletion verification
NAMESPACE_DELETE_MAX_RETRIES = 10
NAMESPACE_DELETE_RETRY_DELAY_SECONDS = 1.0


def _wait_for_namespace_empty(
    index_name: str,
    namespace: str,
    max_retries: int = NAMESPACE_DELETE_MAX_RETRIES,
    retry_delay: float = NAMESPACE_DELETE_RETRY_DELAY_SECONDS,
) -> bool:
    """
    Wait for a Pinecone namespace to be empty after deletion.

    Pinecone deletions can have eventual consistency, so this function
    polls until the namespace shows 0 vectors or doesn't exist.

    Args:
        index_name: Name of the Pinecone index
        namespace: Namespace to check
        max_retries: Maximum number of polling attempts
        retry_delay: Seconds to wait between attempts

    Returns:
        bool: True if namespace is empty/gone, False if timeout
    """
    try:
        pc = Pinecone()
        index = pc.Index(index_name)

        # Mandatory initial delay before first check to allow deletion to propagate
        time.sleep(retry_delay)

        for attempt in range(max_retries):
            stats = index.describe_index_stats()
            namespaces = stats.get("namespaces", {})

            # Namespace doesn't exist or has 0 vectors
            if namespace not in namespaces:
                logger.debug(
                    f"[Adora Menu Updater] Namespace '{namespace}' confirmed deleted (not found)",
                    extra={"attempt": attempt + 1},
                )
                return True

            vector_count = namespaces[namespace].get("vector_count", 0)
            if vector_count == 0:
                logger.debug(
                    f"[Adora Menu Updater] Namespace '{namespace}' confirmed empty",
                    extra={"attempt": attempt + 1},
                )
                return True

            logger.debug(
                f"[Adora Menu Updater] Waiting for namespace deletion, {vector_count} vectors remaining",
                extra={"attempt": attempt + 1, "vector_count": vector_count},
            )
            time.sleep(retry_delay)

        logger.warning(
            f"[Adora Menu Updater] Timeout waiting for namespace '{namespace}' to empty"
        )
        return False

    except Exception as e:
        logger.warning(f"[Adora Menu Updater] Error checking namespace stats: {e}")
        # If we can't check, proceed anyway (namespace might not exist)
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
            f"[BusinessHoursUpdate] Updated business hours for project {project_id}",
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

        # Get knowledge config from project raw_config
        raw_config = project.raw_config or {}
        knowledge_config = raw_config.get("knowledge", {})
        knowledge_settings = knowledge_config.get("settings", {})

        pinecone_index_name = knowledge_settings.get("index_name")
        pinecone_namespace = knowledge_settings.get("namespace")

        if not pinecone_index_name:
            raise ValueError(
                f"Project {project_id} does not have knowledge.settings.index_name configured"
            )

        if not pinecone_namespace:
            raise ValueError(
                f"Project {project_id} does not have knowledge.settings.namespace configured"
            )

        # Get POS integration for this project
        project_integration_repository = db.ProjectIntegrationRepository(session)
        project_integrations = (
            project_integration_repository.get_project_integrations_by_project_id(
                project_uuid
            )
        )

        # Find the Adora POS integration
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
            _wait_for_namespace_empty(pinecone_index_name, pinecone_namespace)
        except Exception as e:
            # Log but don't fail - namespace might not exist yet or be empty
            logger.warning(
                f"[Adora Menu Updater] Could not clear namespace (may be empty): {e}",
                extra={
                    "project_id": project_id,
                    "pinecone_namespace": pinecone_namespace,
                },
            )

        # Call knowledge service to update the menu
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

        # Update project's product_info with the system_prompt_menu
        system_prompt_menu = result.get("system_prompt_menu", "")
        product_info_updated = False
        if system_prompt_menu:
            project_repo = ProjectRepository(session)
            project_repo.update_project(project_uuid, product_info=system_prompt_menu)
            product_info_updated = True
            logger.debug(
                f"[Adora Menu Updater] Updated product_info for project {project_id}",
                extra={
                    "project_id": project_id,
                    "product_info_length": len(system_prompt_menu),
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
