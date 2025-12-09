"""Internal API implementation for knowledge update system."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session, selectinload

from db.tables.integration import Integration, ProjectIntegration
from db.tables.projects import Project
from db.tables.types import IntegrationProvider, IntegrationType
from events import KnowledgeUpdateRequested, publish_event
from utils.log import logger

# Safe mode: When True, limits knowledge updates to only the first few stores
# Set to False for production to update all stores
SAFE_MODE = True
SAFE_MODE_MAX_PROJECTS = 3


def _has_adora_tool_configured(project: Project) -> bool:
    """
    Check if a project has adora_tool configured in raw_config.tools.identifiers.

    Args:
        project: The project to check

    Returns:
        bool: True if adora_tool is configured, False otherwise
    """
    raw_config = project.raw_config or {}
    tools_config = raw_config.get("tools", {})
    identifiers = tools_config.get("identifiers", [])

    return any(
        isinstance(identifier, dict) and identifier.get("tool_name") == "adora_tool"
        for identifier in identifiers
    )


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
        # Query to find projects with Adora POS integrations
        # Join ProjectIntegration -> Integration -> Project -> Account
        projects_with_adora_pos = (
            session.query(ProjectIntegration, Integration, Project)
            .join(Integration, ProjectIntegration.integration_id == Integration.id)
            .join(Project, ProjectIntegration.project_id == Project.id)
            .options(selectinload(Project.account))
            .filter(
                Integration.provider == IntegrationProvider.adora,
                Integration.integration_type == IntegrationType.pos,
            )
            .all()
        )

        total_found = len(projects_with_adora_pos)

        # Safe mode: limit to first N projects for testing
        if SAFE_MODE:
            projects_with_adora_pos = projects_with_adora_pos[:SAFE_MODE_MAX_PROJECTS]
            logger.warning(
                f"[Adora Menu Updater] SAFE_MODE enabled: processing {len(projects_with_adora_pos)}/{total_found} projects",
                extra={
                    "safe_mode": True,
                    "max_projects": SAFE_MODE_MAX_PROJECTS,
                    "total_found": total_found,
                },
            )

        events_published = 0
        errors = []

        for project_integration, integration, project in projects_with_adora_pos:
            # Check if project has adora_tool configured
            if not _has_adora_tool_configured(project):
                logger.debug(
                    f"[Adora Menu Updater] Skipping project {project.id}: adora_tool not configured",
                    extra={"project_id": str(project.id)},
                )
                continue
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
            "message": f"Submitted {events_published} update knowledge events"
            + (
                f" (SAFE_MODE: limited to {SAFE_MODE_MAX_PROJECTS})"
                if SAFE_MODE
                else ""
            ),
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
            "message": "Discovery process failed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
