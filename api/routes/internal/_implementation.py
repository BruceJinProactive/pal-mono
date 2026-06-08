"""Internal API implementation for knowledge update system."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session, selectinload

from db.tables.integration import Integration, ProjectIntegration
from db.tables.projects import Project
from db.tables.types import IntegrationProvider, IntegrationType
from events import KnowledgeUpdateRequested, publish_event
from utils.log import logger


def _is_auto_update_knowledge_enabled(
    project_integration: ProjectIntegration,
) -> bool:
    """Project integrations are included in knowledge auto-updates by default."""
    config = project_integration.config or {}
    auto_update_knowledge = config.get("auto_update_knowledge", True)
    if not isinstance(auto_update_knowledge, bool):
        logger.error(
            "[Adora Menu Updater] Invalid auto_update_knowledge config",
            extra={
                "project_integration_id": str(project_integration.id),
                "project_id": str(project_integration.project_id),
                "auto_update_knowledge_type": type(auto_update_knowledge).__name__,
            },
        )
        raise ValueError("auto_update_knowledge must be a boolean")
    return auto_update_knowledge


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
        projects_with_auto_update_enabled = [
            (pi, i, p)
            for pi, i, p in projects_with_adora_pos
            if _is_auto_update_knowledge_enabled(pi)
        ]
        skipped_auto_update_disabled = total_found - len(
            projects_with_auto_update_enabled
        )
        projects_with_adora_pos = projects_with_auto_update_enabled

        logger.info(
            "[Adora Menu Updater] Applied Adora knowledge auto-update project config",
            extra={
                "total_found": total_found,
                "total_processed": len(projects_with_adora_pos),
                "skipped_auto_update_disabled": skipped_auto_update_disabled,
            },
        )

        if skipped_auto_update_disabled:
            logger.info(
                "[Adora Menu Updater] Skipping projects with knowledge auto-update disabled",
                extra={
                    "skipped_auto_update_disabled": skipped_auto_update_disabled,
                    "total_found": total_found,
                    "total_processed": len(projects_with_adora_pos),
                },
            )

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
            "total_found": total_found,
            "total_processed": len(projects_with_adora_pos),
            "skipped_auto_update_disabled": skipped_auto_update_disabled,
            "events_published": events_published,
            "errors": errors,
            "summary": f"Submitted {events_published} update knowledge events",
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
            "events_published": 0,
            "errors": [f"Process error: {str(e)}"],
            "summary": "Discovery process failed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
