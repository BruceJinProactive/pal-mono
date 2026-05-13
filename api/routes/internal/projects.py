"""Internal API endpoints for project updates."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pal_agents.menu_assets.adora import build_menu_assets, compile_coupons_v1
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from api.schemas.operations.signal_source import SignalSourceIdResponse
from db.repositories.project_repository import ProjectRepository
from db.tables.types import IntegrationProvider, IntegrationType
from services import project_service, signal_source_service
from services.knowledge_service.adora._client import (
    download_coupons,
    download_menu,
    get_bearer_token,
)
from utils.log import logger
from utils.secret import get_client_secret

projects_router = APIRouter(prefix="/projects")

_NO_USABLE_COUPON_DATA_MESSAGES = (
    "Coupons array must not be empty",
    "No AI offers found",
)


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


def _compile_adora_coupon_data(
    *,
    store_id: str,
    raw_coupons: list[Any] | None,
) -> dict[str, Any] | None:
    """Compile raw Adora coupons when usable coupon data is available."""
    if not raw_coupons:
        return None

    try:
        return compile_coupons_v1({"store_id": store_id, "coupons": raw_coupons})
    except ValueError as exc:
        if any(message in str(exc) for message in _NO_USABLE_COUPON_DATA_MESSAGES):
            logger.info(
                "[Adora Menu Updater] No usable Adora coupon data found",
                extra={"store_id": store_id, "error": str(exc)},
            )
            return None
        raise


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
def update_knowledge(
    project_id: str,
    session: Session = Depends(db.get_db),
):
    """
    Update knowledge base for a specific project.

    Processes menu asset updates for a single project with an Adora V3 project integration.
    Fetches raw menu data from Adora API, regenerates the English prompt and compiled
    tool JSON, and writes both back to the database.
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

        # Find the Adora V3 project integration row.
        project_integration_repository = db.ProjectIntegrationRepository(session)
        project_integrations = (
            project_integration_repository.get_project_integrations_by_project_id(
                project_uuid
            )
        )

        adora_v3_project_integration = None
        for pi in project_integrations:
            if pi.tool_name == "adora_v3":
                adora_v3_project_integration = pi
                break

        if not adora_v3_project_integration:
            raise ValueError(
                f"Project {project_id} does not have an adora_v3 project integration"
            )

        # Find the linked Adora POS integration.
        pos_integration = None
        integration_repository = db.IntegrationRepository(session)
        pos_integration = integration_repository.get_integration_by_id(
            project.account_id, adora_v3_project_integration.integration_id
        )
        if (
            not pos_integration
            or pos_integration.integration_type != IntegrationType.pos
            or pos_integration.provider != IntegrationProvider.adora
        ):
            raise ValueError(
                f"Project {project_id} adora_v3 integration is not linked to an Adora POS integration"
            )

        # Get store identifier
        store_id = adora_v3_project_integration.store_identifier
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
            f"[Adora Menu Updater] Updating Adora V3 menu assets for project {project_id}",
            extra={
                "project_id": project_id,
                "project_name": project.name,
                "store_id": store_id,
                "project_integration_id": str(adora_v3_project_integration.id),
            },
        )

        bearer_token = get_bearer_token(
            client_id=client_id,
            client_secret=client_secret,
            token_api_endpoint=token_api_endpoint,
        )
        raw_menu = download_menu(
            store_id=store_id,
            token=bearer_token,
            general_api_endpoint=general_api_endpoint,
        )
        if not isinstance(raw_menu, dict):
            raise ValueError("Adora menu response was not a JSON object")
        raw_menu.setdefault("store_id", store_id)

        raw_coupons = download_coupons(
            store_id=store_id,
            token=bearer_token,
            general_api_endpoint=general_api_endpoint,
        )
        coupon_data = _compile_adora_coupon_data(
            store_id=store_id,
            raw_coupons=raw_coupons,
        )

        menu_assets = build_menu_assets(
            raw_menu,
            coupon_data=coupon_data,
            remove_unused_weights=True,
        )

        # Update project's product_info with the English menu prompt.
        project_repo = ProjectRepository(session)
        project_repo.update_project(
            project_uuid, product_info=menu_assets.english_menu_prompt
        )
        logger.debug(
            f"[Adora Menu Updater] Updated product_info for project {project_id}",
            extra={
                "project_id": project_id,
                "product_info_length": len(menu_assets.english_menu_prompt),
            },
        )

        updated_config = dict(adora_v3_project_integration.config or {})
        updated_config["menu_data"] = menu_assets.menu_data
        if coupon_data is None:
            updated_config.pop("coupon_data", None)
        else:
            updated_config["coupon_data"] = coupon_data
        project_integration_repository.update_project_integration(
            adora_v3_project_integration.id, config=updated_config
        )
        logger.debug(
            "[Adora Menu Updater] Updated adora_v3 project integration config",
            extra={
                "project_id": project_id,
                "project_integration_id": str(adora_v3_project_integration.id),
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

        compiled_item_count = sum(
            len(item_entries)
            for item_entries in menu_assets.menu_data.get("items", {}).values()
        )

        logger.debug(
            f"[Adora Menu Updater] Knowledge update complete for project {project_id}",
            extra={
                "project_id": project_id,
                "project_name": project.name,
                "compiled_items": compiled_item_count,
            },
        )

        return {
            "success": True,
            "project_id": project_id,
            "project_name": project.name,
            "compiled_items": compiled_item_count,
            "product_info_updated": True,
            "menu_data_updated": True,
            "coupon_data_updated": coupon_data is not None,
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
