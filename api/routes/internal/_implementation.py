"""Internal API implementation for knowledge update system."""

import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session, selectinload

from db.tables.integration import Integration, ProjectIntegration
from db.tables.projects import Project
from db.tables.types import IntegrationProvider, IntegrationType
from events import KnowledgeUpdateRequested, publish_event
from utils.log import logger

# Safe mode: When True, only processes projects specified in env vars
# Set to False for production to update all stores
SAFE_MODE = True


def _get_safe_mode_project_ids() -> set[str]:
    """
    Collect project IDs from ADORA_MENU_PROJECTS_1/2/3 environment variables.

    Each env var can contain a single ID or comma-separated IDs.
    Returns empty set if no env vars are set.
    """
    project_ids: set[str] = set()
    for env_var in [
        "ADORA_MENU_PROJECTS_1",
        "ADORA_MENU_PROJECTS_2",
        "ADORA_MENU_PROJECTS_3",
    ]:
        value = os.getenv(env_var, "")
        project_ids.update(s.strip() for s in value.split(",") if s.strip())
    return project_ids


async def start_knowledge_update_process(session: Session) -> dict:
    """
    Start knowledge update process for all projects.

    Queries database for projects with Adora POS integrations
    and publishes individual events for each project.

    Args:
        session: Database session

    Returns:
        dict: Summary of projects queried and events published
    """
    logger.info("[Adora Menu Updater] Starting discovery process")

    try:
        # Query to find projects with Adora V3 project integrations.
        # Join ProjectIntegration -> Integration -> Project -> Account
        projects_with_adora_pos = (
            session.query(ProjectIntegration, Integration, Project)
            .join(Integration, ProjectIntegration.integration_id == Integration.id)
            .join(Project, ProjectIntegration.project_id == Project.id)
            .options(selectinload(Project.account))
            .filter(
                ProjectIntegration.tool_name == "adora_v3",
                Integration.provider == IntegrationProvider.adora,
                Integration.integration_type == IntegrationType.pos,
            )
            .all()
        )

        total_found = len(projects_with_adora_pos)

        # Safe mode: filter to projects specified in ADORA_MENU_PROJECTS_* env vars
        if SAFE_MODE:
            safe_mode_ids = _get_safe_mode_project_ids()
            if safe_mode_ids:
                projects_with_adora_pos = [
                    (pi, i, p)
                    for pi, i, p in projects_with_adora_pos
                    if str(p.id) in safe_mode_ids
                ]
                logger.warning(
                    f"[Adora Menu Updater] SAFE_MODE enabled: filtering to {len(safe_mode_ids)} project IDs, found {len(projects_with_adora_pos)} match(es)",
                    extra={
                        "safe_mode": True,
                        "safe_mode_project_ids": list(safe_mode_ids),
                        "matched_count": len(projects_with_adora_pos),
                        "total_found": total_found,
                    },
                )
            else:
                logger.warning(
                    "[Adora Menu Updater] SAFE_MODE enabled but no project IDs configured in ADORA_MENU_PROJECTS_1/2/3 - processing 0 projects",
                    extra={"safe_mode": True, "total_found": total_found},
                )
                projects_with_adora_pos = []

        events_published = 0
        errors = []

        for project_integration, integration, project in projects_with_adora_pos:
            try:
                # Get account info for context
                account = project.account
                if not account:
                    error_msg = f"Project {project.id} has no associated account"
                    errors.append(error_msg)
                    logger.error(f"[Adora Menu Updater] {error_msg}")
                    continue

                # Create and publish knowledge update event
                event = KnowledgeUpdateRequested(
                    project_id=project.id,
                    account_id=account.id,
                    integration_id=integration.id,
                    project_integration_id=project_integration.id,
                    requested_at=datetime.now(timezone.utc),
                )

                success = await publish_event(event)

                if success:
                    events_published += 1
                    logger.info(
                        f"[Adora Menu Updater] Published event for project {project.id}",
                        extra={
                            "project_id": str(project.id),
                            "account_id": str(account.id),
                            "integration_id": str(integration.id),
                            "store_identifier": project_integration.store_identifier,
                        },
                    )
                else:
                    error_msg = f"Failed to publish event for project {project.id}"
                    errors.append(error_msg)
                    logger.error(f"[Adora Menu Updater] {error_msg}")

            except Exception as e:
                error_msg = f"Error processing project {project.id}: {str(e)}"
                errors.append(error_msg)
                logger.error(
                    f"[Adora Menu Updater] {error_msg}",
                    exc_info=True,
                    extra={"project_id": str(project.id)},
                )

        # Return summary
        result = {
            "success": True,
            "safe_mode": SAFE_MODE,
            "total_found": total_found,
            "total_processed": len(projects_with_adora_pos),
            "events_published": events_published,
            "errors": errors,
            "summary": f"Submitted {events_published} update knowledge events"
            + (" (SAFE_MODE enabled)" if SAFE_MODE else ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            f"[Adora Menu Updater] Discovery complete: {events_published} events published",
            extra=result,
        )

        return result

    except Exception as e:
        logger.error(
            "[Adora Menu Updater] Error in discovery process",
            exc_info=True,
        )
        return {
            "success": False,
            "safe_mode": SAFE_MODE,
            "events_published": 0,
            "errors": [f"Process error: {str(e)}"],
            "summary": "Discovery process failed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
