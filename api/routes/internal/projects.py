"""Internal API endpoints for project updates."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import db
from db.repositories.project_repository import ProjectRepository
from utils.log import logger

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
    _session: Session = Depends(db.get_db),
):
    """
    Update knowledge base for a specific project.

    Processes knowledge update for a single project, updating both
    the knowledge base and menu data. Called by Lambda function consuming
    knowledge update events.

    Args:
        project_id: UUID of the project to update
        session: Database session

    Returns:
        dict: Status of the update operation
    """
    # TODO: Implement knowledge update logic for specific project
    # TODO: Validate project_id and get project
    # TODO: Update knowledge base with latest information
    # TODO: Update menu data in database
    # TODO: Handle errors and rollback if needed

    logger.info(f"[KnowledgeUpdate] Starting knowledge update for project {project_id}")

    # Placeholder implementation
    logger.info(f"[KnowledgeUpdate] Knowledge update complete for project {project_id}")

    return {
        "success": True,
        "project_id": project_id,
        "message": "Implementation pending",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


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
