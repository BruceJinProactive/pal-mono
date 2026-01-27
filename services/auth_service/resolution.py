"""
RBAC Resource Resolution

Handles resolution of resource identifiers (name or UUID) to UUIDs
and hierarchical resource relationship lookups.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from db.repositories import checklist_repository
from db.repositories.account_repository import AccountRepository
from db.repositories.agent_repository import AgentRepository
from db.repositories.change_log_repository import ChangeLogRepository
from db.repositories.feedback_repository import FeedbackRepository
from db.repositories.project_repository import ProjectRepository
from utils.log import logger


def resolve_account_identifier(identifier: str, session: Session) -> UUID:
    """
    Resolve account name or UUID to UUID.

    Supports both account names (e.g., "palona") and UUIDs.
    Tries UUID parsing first, then falls back to name lookup.

    Args:
        identifier: Account name or UUID string
        session: Database session

    Returns:
        Account UUID

    Raises:
        ValueError: If account not found by name or ID

    Examples:
        >>> resolve_account_identifier("palona", session)
        UUID("123e4567-...")

        >>> resolve_account_identifier("123e4567-e89b-12d3-a456-426614174000", session)
        UUID("123e4567-...")
    """
    account_repo = AccountRepository(session, auto_commit=False)

    # Try UUID first
    try:
        account_id = UUID(identifier)
        account = account_repo.get_account_by_id(account_id)
        if account:
            return account_id
        raise ValueError(f"Account with ID {account_id} not found")
    except ValueError:
        pass  # Not a valid UUID, continue to name lookup

    # Try name lookup
    account = account_repo.get_account(identifier)
    if not account:
        raise ValueError(f"Account '{identifier}' not found")

    return account.id


def resolve_resource_identifier(
    resource_type: str, identifier: str, session: Session
) -> UUID:
    """
    Resolve resource identifier to UUID based on resource type.

    - accounts: Supports name or UUID
    - projects/agents/checklists: UUID only

    Args:
        resource_type: Resource type (e.g., "accounts", "projects")
        identifier: Resource name or UUID string
        session: Database session

    Returns:
        Resource UUID

    Raises:
        ValueError: If resource not found or invalid identifier

    Examples:
        >>> resolve_resource_identifier("accounts", "palona", session)
        UUID("123e4567-...")

        >>> resolve_resource_identifier("checklists", "abc-123-...", session)
        UUID("abc-123-...")
    """
    if resource_type == "accounts":
        return resolve_account_identifier(identifier, session)

    # All other resources require UUIDs
    try:
        resource_id = UUID(identifier)
    except ValueError as err:
        raise ValueError(
            f"Invalid UUID for {resource_type}: {identifier}. "
            f"Only accounts support name-based identifiers."
        ) from err

    # Verify resource exists
    if resource_type == "projects":
        project_repo = ProjectRepository(session, auto_commit=False)
        project = project_repo.get_project(resource_id)
        if not project:
            raise ValueError(f"Project with ID {resource_id} not found")

    elif resource_type == "agents":
        agent_repo = AgentRepository(session, auto_commit=False)
        agent = agent_repo.get_agent(resource_id)
        if not agent:
            raise ValueError(f"Agent with ID {resource_id} not found")

    elif resource_type == "checklists":
        checklist = checklist_repository.get_checklist_by_id(session, resource_id)
        if not checklist:
            raise ValueError(f"Checklist with ID {resource_id} not found")

    elif resource_type == "histories":
        change_log_repo = ChangeLogRepository(session)
        change_log = change_log_repo.get_change_log(resource_id)
        if not change_log:
            raise ValueError(f"History with ID {resource_id} not found")

    elif resource_type == "feedbacks":
        feedback_repo = FeedbackRepository(session)
        feedback = feedback_repo.get_feedback_by_id(resource_id)
        if not feedback:
            raise ValueError(f"Feedback with ID {resource_id} not found")

    return resource_id


def get_parent_resource(
    resource_type: str, resource_id: UUID, session: Session
) -> Optional[tuple[str, UUID]]:
    """
    Get parent resource for hierarchical permission checking.

    Resource hierarchy:
    - checklist → project → account
    - project → account
    - agent → account
    - history → account
    - feedback → account (via message → conversation → project)
    - account → None (top-level)

    Args:
        resource_type: Resource type (e.g., "checklists")
        resource_id: Resource UUID
        session: Database session

    Returns:
        Tuple of (parent_resource_type, parent_resource_id) or None if no parent

    Examples:
        >>> get_parent_resource("checklists", checklist_id, session)
        ("projects", UUID("project-uuid"))

        >>> get_parent_resource("accounts", account_id, session)
        None  # Top-level, no parent
    """
    try:
        if resource_type == "checklists":
            checklist = checklist_repository.get_checklist_by_id(session, resource_id)
            if checklist and checklist.project_id:
                return ("projects", checklist.project_id)
            logger.debug(f"Checklist {resource_id} has no parent project or not found")

        elif resource_type == "projects":
            project_repo = ProjectRepository(session, auto_commit=False)
            project = project_repo.get_project(resource_id)
            if project and project.account_id:
                return ("accounts", project.account_id)
            logger.debug(f"Project {resource_id} has no parent account or not found")

        elif resource_type == "agents":
            agent_repo = AgentRepository(session, auto_commit=False)
            agent = agent_repo.get_agent(resource_id)
            if agent and agent.account_id:
                return ("accounts", agent.account_id)
            logger.debug(f"Agent {resource_id} has no parent account or not found")

        elif resource_type == "histories":
            change_log_repo = ChangeLogRepository(session)
            change_log = change_log_repo.get_change_log(resource_id)
            if change_log and change_log.account_id:
                return ("accounts", change_log.account_id)
            logger.debug(f"History {resource_id} has no parent account or not found")

        elif resource_type == "feedbacks":
            feedback_repo = FeedbackRepository(session)
            feedback = feedback_repo.get_feedback_by_id(resource_id)
            if feedback and feedback.message:
                message = feedback.message
                if message.conversation and message.conversation.project_id:
                    project_repo = ProjectRepository(session, auto_commit=False)
                    project = project_repo.get_project(message.conversation.project_id)
                    if project and project.account_id:
                        return ("accounts", project.account_id)
            logger.debug(f"Feedback {resource_id} has no parent account or not found")

        elif resource_type == "accounts":
            # Top-level resource, no parent
            return None

        return None

    except Exception as e:
        logger.error(
            f"Error getting parent resource for {resource_type}/{resource_id}: {e}"
        )
        return None
