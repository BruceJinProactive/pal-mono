"""Internal API endpoints for scheduled tasks and event publishing."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import db
from db.repositories.project_repository import ProjectRepository
from events import GoogleBusinessHoursUpdateRequested, publish_event
from utils.log import logger

from . import _implementation
from .catering import catering_router
from .events import events_router
from .projects import projects_router

internal_router = APIRouter(prefix="/internal", tags=["internal"])

# TODO: Add authentication/authorization to restrict access to only:
#   - AWS EventBridge Scheduler
#   - Internal Lambda functions
# Consider using AWS Signature V4 verification or VPC-only access controls
# to prevent unauthorized external access to these internal endpoints

internal_router.include_router(catering_router)
internal_router.include_router(events_router)
internal_router.include_router(projects_router)


@internal_router.post("/start-knowledge-update-process")
async def start_knowledge_update_process(
    _session: Session = Depends(db.get_db),
):
    """
    Start knowledge update process for all projects.

    Queries database for accounts and projects that need knowledge updates
    and publishes individual events for each project. Called by EventBridge Scheduler daily.

    Args:
        session: Database session

    Returns:
        dict: Summary of projects queried and events published
    """
    return await _implementation.start_knowledge_update_process(_session)


@internal_router.post("/business-hours-update")
async def trigger_business_hours_update(
    force_update: bool = Query(
        False, description="Update all projects, even if recently updated"
    ),
    session: Session = Depends(db.get_db),
):
    """
    Discovery endpoint for business hours updates.

    Queries database for projects (stores) with Google Place IDs and publishes events.
    Called by EventBridge Scheduler daily.

    Args:
        force_update: If True, update all projects regardless of last update time
        session: Database session

    Returns:
        dict: Summary of projects queried and events published
    """
    project_repo = ProjectRepository(session)

    try:
        # Get projects needing updates
        if force_update:
            projects = project_repo.get_projects_with_google_place_id()
            logger.info(
                f"[BusinessHoursUpdate] Force update enabled: processing all {len(projects)} projects with place IDs"
            )
        else:
            # Only update if not updated in last 24 hours
            projects = project_repo.get_projects_needing_hours_update(
                hours_threshold=24
            )
            logger.info(
                f"[BusinessHoursUpdate] Found {len(projects)} projects needing hours update"
            )

        events_published = 0
        skipped = 0
        errors = []

        for project in projects:
            # Skip if missing place_id (shouldn't happen with query filters)
            if not project.google_place_id:
                skipped += 1
                continue

            # Get account info for context
            account = project.account

            try:
                # Publish event for this store/project
                event = GoogleBusinessHoursUpdateRequested(
                    project_id=project.id,
                    project_name=project.name,
                    account_id=account.id,
                    account_name=account.name,
                    google_place_id=project.google_place_id,
                    requested_at=datetime.now(timezone.utc),
                    requested_by="scheduler",
                    last_updated=project.business_hours_last_updated,
                )

                success = await publish_event(event)

                if success:
                    events_published += 1
                    logger.info(
                        f"[BusinessHoursUpdate] Published hours update event for project {project.id}",
                        extra={
                            "project_id": str(project.id),
                            "account_id": str(account.id),
                            "place_id": project.google_place_id,
                        },
                    )
                else:
                    error_msg = f"Failed to publish event for project {project.id}"
                    errors.append(error_msg)
                    logger.error(f"[BusinessHoursUpdate] {error_msg}")

            except Exception as e:
                error_msg = f"Error processing project {project.id}: {str(e)}"
                errors.append(error_msg)
                logger.error(
                    f"[BusinessHoursUpdate] {error_msg}",
                    exc_info=True,
                    extra={"project_id": str(project.id)},
                )

        # Return summary
        result = {
            "success": True,
            "total_projects": len(projects),
            "events_published": events_published,
            "skipped": skipped,
            "errors": errors,
            "force_update": force_update,
        }

        logger.info(
            f"[BusinessHoursUpdate] Discovery complete: {events_published}/{len(projects)} events published",
            extra=result,
        )

        return result

    except Exception as e:
        logger.error(
            "[BusinessHoursUpdate] Error in business hours update discovery",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger hours update: {str(e)}",
        ) from e
