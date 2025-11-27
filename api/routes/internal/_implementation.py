"""Internal API implementation for knowledge update system."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session, selectinload

from db.tables.integration import Integration, ProjectIntegration
from db.tables.projects import Project
from db.tables.types import IntegrationProvider, IntegrationType
from events import KnowledgeUpdateRequested, publish_event
from utils.log import logger


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
    logger.info("[KnowledgeUpdate] Starting knowledge update process")

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

        events_published = 0
        errors = []

        for project_integration, integration, project in projects_with_adora_pos:
            # Check if project has adora_tool configured
            if not _has_adora_tool_configured(project):
                logger.debug(
                    f"[KnowledgeUpdate] Skipping project {project.id}: adora_tool not configured in raw_config",
                    extra={"project_id": str(project.id)},
                )
                continue
            try:
                # Get account info for context
                account = project.account
                if not account:
                    error_msg = f"Project {project.id} has no associated account"
                    errors.append(error_msg)
                    logger.error(f"[KnowledgeUpdate] {error_msg}")
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
                        f"[KnowledgeUpdate] Published knowledge update event for project {project.id}",
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
                    logger.error(f"[KnowledgeUpdate] {error_msg}")

            except Exception as e:
                error_msg = f"Error processing project {project.id}: {str(e)}"
                errors.append(error_msg)
                logger.error(
                    f"[KnowledgeUpdate] {error_msg}",
                    exc_info=True,
                    extra={"project_id": str(project.id)},
                )

        # Return summary
        result = {
            "success": True,
            "errors": errors,
            "message": f"Submitted {events_published} update knowledge events",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            f"[KnowledgeUpdate] Process complete: {events_published} events published ",
            extra=result,
        )

        return result

    except Exception as e:
        logger.error(
            "[KnowledgeUpdate] Error in knowledge update process",
            exc_info=True,
        )
        return {
            "success": False,
            "events_published": 0,
            "errors": [f"Process error: {str(e)}"],
            "message": "Knowledge update process failed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
