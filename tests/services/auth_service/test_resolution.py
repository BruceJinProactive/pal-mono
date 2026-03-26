"""Tests for RBAC resource resolution."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from services.auth_service.resolution import (
    get_parent_resource,
    resolve_account_identifier,
    resolve_resource_identifier,
)


class TestResolveAccountIdentifier:
    """Tests for resolve_account_identifier function."""

    def test_resolve_account_by_name(self, mocker):
        """Should resolve account name to UUID."""
        mock_session = MagicMock()
        account_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_account = MagicMock()
        mock_account.id = account_id

        mock_account_repo = mocker.patch(
            "services.auth_service.resolution.AccountRepository"
        )
        # First try UUID parsing (will fail for "palona")
        # Then try name lookup
        mock_account_repo.return_value.get_account.return_value = mock_account

        result = resolve_account_identifier("palona", mock_session)
        assert result == account_id

    def test_resolve_account_by_uuid(self, mocker):
        """Should resolve UUID string to UUID."""
        mock_session = MagicMock()
        account_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_account = MagicMock()
        mock_account.id = account_id

        mock_account_repo = mocker.patch(
            "services.auth_service.resolution.AccountRepository"
        )
        mock_account_repo.return_value.get_account_by_id.return_value = mock_account

        result = resolve_account_identifier(str(account_id), mock_session)
        assert result == account_id

    def test_resolve_account_uuid_not_found(self, mocker):
        """Should raise ValueError for UUID that doesn't exist."""
        mock_session = MagicMock()
        account_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_account_repo = mocker.patch(
            "services.auth_service.resolution.AccountRepository"
        )
        mock_account_repo.return_value.get_account_by_id.return_value = None
        mock_account_repo.return_value.get_account.return_value = None

        with pytest.raises(ValueError, match="not found"):
            resolve_account_identifier(str(account_id), mock_session)

    def test_resolve_account_name_not_found(self, mocker):
        """Should raise ValueError for unknown account name."""
        mock_session = MagicMock()

        mock_account_repo = mocker.patch(
            "services.auth_service.resolution.AccountRepository"
        )
        mock_account_repo.return_value.get_account.return_value = None

        with pytest.raises(ValueError, match="not found"):
            resolve_account_identifier("nonexistent_account", mock_session)


class TestResolveResourceIdentifier:
    """Tests for resolve_resource_identifier function."""

    def test_resolve_account_delegates_to_account_resolver(self, mocker):
        """Should delegate accounts to resolve_account_identifier."""
        mock_session = MagicMock()
        account_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_resolve_account = mocker.patch(
            "services.auth_service.resolution.resolve_account_identifier",
            return_value=account_id,
        )

        result = resolve_resource_identifier("accounts", "palona", mock_session)
        assert result == account_id
        mock_resolve_account.assert_called_once_with("palona", mock_session)

    def test_resolve_project_by_uuid(self, mocker):
        """Should resolve project UUID."""
        mock_session = MagicMock()
        project_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_project = MagicMock()
        mock_project_repo = mocker.patch(
            "services.auth_service.resolution.ProjectRepository"
        )
        mock_project_repo.return_value.get_project.return_value = mock_project

        result = resolve_resource_identifier("projects", str(project_id), mock_session)
        assert result == project_id

    def test_resolve_project_invalid_uuid(self):
        """Should raise ValueError for invalid UUID."""
        mock_session = MagicMock()

        with pytest.raises(ValueError, match="Invalid UUID"):
            resolve_resource_identifier("projects", "not-a-uuid", mock_session)

    def test_resolve_project_not_found(self, mocker):
        """Should raise ValueError for non-existent project."""
        mock_session = MagicMock()
        project_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_project_repo = mocker.patch(
            "services.auth_service.resolution.ProjectRepository"
        )
        mock_project_repo.return_value.get_project.return_value = None

        with pytest.raises(ValueError, match="not found"):
            resolve_resource_identifier("projects", str(project_id), mock_session)

    def test_resolve_agent_by_uuid(self, mocker):
        """Should resolve agent UUID."""
        mock_session = MagicMock()
        agent_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_agent = MagicMock()
        mock_agent_repo = mocker.patch(
            "services.auth_service.resolution.AgentRepository"
        )
        mock_agent_repo.return_value.get_agent.return_value = mock_agent

        result = resolve_resource_identifier("agents", str(agent_id), mock_session)
        assert result == agent_id

    def test_resolve_agent_not_found(self, mocker):
        """Should raise ValueError for non-existent agent."""
        mock_session = MagicMock()
        agent_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_agent_repo = mocker.patch(
            "services.auth_service.resolution.AgentRepository"
        )
        mock_agent_repo.return_value.get_agent.return_value = None

        with pytest.raises(ValueError, match="not found"):
            resolve_resource_identifier("agents", str(agent_id), mock_session)

    def test_resolve_history_by_uuid(self, mocker):
        """Should resolve history UUID."""
        mock_session = MagicMock()
        history_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_change_log = MagicMock()
        mock_change_log_repo = mocker.patch(
            "services.auth_service.resolution.ChangeLogRepository"
        )
        mock_change_log_repo.return_value.get_change_log.return_value = mock_change_log

        result = resolve_resource_identifier("histories", str(history_id), mock_session)
        assert result == history_id

    def test_resolve_history_not_found(self, mocker):
        """Should raise ValueError for non-existent history."""
        mock_session = MagicMock()
        history_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_change_log_repo = mocker.patch(
            "services.auth_service.resolution.ChangeLogRepository"
        )
        mock_change_log_repo.return_value.get_change_log.return_value = None

        with pytest.raises(ValueError, match="not found"):
            resolve_resource_identifier("histories", str(history_id), mock_session)

    def test_resolve_feedback_by_uuid(self, mocker):
        """Should resolve feedback UUID."""
        mock_session = MagicMock()
        feedback_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_feedback = MagicMock()
        mock_feedback_repo = mocker.patch(
            "services.auth_service.resolution.FeedbackRepository"
        )
        mock_feedback_repo.return_value.get_feedback_by_id.return_value = mock_feedback

        result = resolve_resource_identifier(
            "feedbacks", str(feedback_id), mock_session
        )
        assert result == feedback_id

    def test_resolve_feedback_not_found(self, mocker):
        """Should raise ValueError for non-existent feedback."""
        mock_session = MagicMock()
        feedback_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_feedback_repo = mocker.patch(
            "services.auth_service.resolution.FeedbackRepository"
        )
        mock_feedback_repo.return_value.get_feedback_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            resolve_resource_identifier("feedbacks", str(feedback_id), mock_session)


class TestGetParentResource:
    """Tests for get_parent_resource function."""

    def test_get_parent_account_from_project(self, mocker):
        """Should return (accounts, uuid) for project."""
        mock_session = MagicMock()
        project_id = UUID("12345678-1234-5678-1234-567812345678")
        account_id = UUID("87654321-4321-8765-4321-876543218765")

        mock_project = MagicMock()
        mock_project.account_id = account_id

        mock_project_repo = mocker.patch(
            "services.auth_service.resolution.ProjectRepository"
        )
        mock_project_repo.return_value.get_project.return_value = mock_project

        result = get_parent_resource("projects", project_id, mock_session)
        assert result == ("accounts", account_id)

    def test_get_parent_account_from_agent(self, mocker):
        """Should return (accounts, uuid) for agent."""
        mock_session = MagicMock()
        agent_id = UUID("12345678-1234-5678-1234-567812345678")
        account_id = UUID("87654321-4321-8765-4321-876543218765")

        mock_agent = MagicMock()
        mock_agent.account_id = account_id

        mock_agent_repo = mocker.patch(
            "services.auth_service.resolution.AgentRepository"
        )
        mock_agent_repo.return_value.get_agent.return_value = mock_agent

        result = get_parent_resource("agents", agent_id, mock_session)
        assert result == ("accounts", account_id)

    def test_get_parent_account_from_history(self, mocker):
        """Should return (accounts, uuid) for history."""
        mock_session = MagicMock()
        history_id = UUID("12345678-1234-5678-1234-567812345678")
        account_id = UUID("87654321-4321-8765-4321-876543218765")

        mock_change_log = MagicMock()
        mock_change_log.account_id = account_id

        mock_change_log_repo = mocker.patch(
            "services.auth_service.resolution.ChangeLogRepository"
        )
        mock_change_log_repo.return_value.get_change_log.return_value = mock_change_log

        result = get_parent_resource("histories", history_id, mock_session)
        assert result == ("accounts", account_id)

    def test_get_parent_none_for_account(self):
        """Should return None for top-level accounts."""
        mock_session = MagicMock()
        account_id = UUID("12345678-1234-5678-1234-567812345678")

        result = get_parent_resource("accounts", account_id, mock_session)
        assert result is None

    def test_get_parent_project_not_found(self, mocker):
        """Should return None when project not found."""
        mock_session = MagicMock()
        project_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_project_repo = mocker.patch(
            "services.auth_service.resolution.ProjectRepository"
        )
        mock_project_repo.return_value.get_project.return_value = None

        result = get_parent_resource("projects", project_id, mock_session)
        assert result is None

    def test_get_parent_agent_not_found(self, mocker):
        """Should return None when agent not found."""
        mock_session = MagicMock()
        agent_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_agent_repo = mocker.patch(
            "services.auth_service.resolution.AgentRepository"
        )
        mock_agent_repo.return_value.get_agent.return_value = None

        result = get_parent_resource("agents", agent_id, mock_session)
        assert result is None

    def test_get_parent_project_no_account_id(self, mocker):
        """Should return None when project has no account_id."""
        mock_session = MagicMock()
        project_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_project = MagicMock()
        mock_project.account_id = None

        mock_project_repo = mocker.patch(
            "services.auth_service.resolution.ProjectRepository"
        )
        mock_project_repo.return_value.get_project.return_value = mock_project

        result = get_parent_resource("projects", project_id, mock_session)
        assert result is None

    def test_get_parent_exception_returns_none(self, mocker):
        """Should return None on exception."""
        mock_session = MagicMock()
        routine_id = UUID("12345678-1234-5678-1234-567812345678")

        mocker.patch(
            "services.auth_service.resolution.select",
            side_effect=Exception("DB error"),
        )

        result = get_parent_resource("routines", routine_id, mock_session)
        assert result is None

    def test_get_parent_unknown_resource_type(self):
        """Should return None for unknown resource type."""
        mock_session = MagicMock()
        resource_id = UUID("12345678-1234-5678-1234-567812345678")

        result = get_parent_resource("unknown_type", resource_id, mock_session)
        assert result is None

    def test_get_parent_feedback_with_message(self, mocker):
        """Should return (accounts, uuid) for feedback with valid message chain."""
        mock_session = MagicMock()
        feedback_id = UUID("12345678-1234-5678-1234-567812345678")
        project_id = UUID("87654321-4321-8765-4321-876543218765")
        account_id = UUID("11111111-1111-1111-1111-111111111111")

        # Create mock chain: feedback -> message -> conversation -> project -> account
        mock_project = MagicMock()
        mock_project.account_id = account_id

        mock_conversation = MagicMock()
        mock_conversation.project_id = project_id

        mock_message = MagicMock()
        mock_message.conversation = mock_conversation

        mock_feedback = MagicMock()
        mock_feedback.message = mock_message

        mock_feedback_repo = mocker.patch(
            "services.auth_service.resolution.FeedbackRepository"
        )
        mock_feedback_repo.return_value.get_feedback_by_id.return_value = mock_feedback

        mock_project_repo = mocker.patch(
            "services.auth_service.resolution.ProjectRepository"
        )
        mock_project_repo.return_value.get_project.return_value = mock_project

        result = get_parent_resource("feedbacks", feedback_id, mock_session)
        assert result == ("accounts", account_id)

    def test_get_parent_feedback_no_message(self, mocker):
        """Should return None for feedback without message."""
        mock_session = MagicMock()
        feedback_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_feedback = MagicMock()
        mock_feedback.message = None

        mock_feedback_repo = mocker.patch(
            "services.auth_service.resolution.FeedbackRepository"
        )
        mock_feedback_repo.return_value.get_feedback_by_id.return_value = mock_feedback

        result = get_parent_resource("feedbacks", feedback_id, mock_session)
        assert result is None

    # =========================================================================
    # Routine hierarchy tests
    # =========================================================================

    def test_get_parent_project_from_routine(self):
        """Should return (projects, uuid) for routine."""
        mock_session = MagicMock()
        routine_id = UUID("12345678-1234-5678-1234-567812345678")
        project_id = UUID("87654321-4321-8765-4321-876543218765")

        mock_routine = MagicMock()
        mock_routine.project_id = project_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_routine
        mock_session.execute.return_value = mock_result

        result = get_parent_resource("routines", routine_id, mock_session)
        assert result == ("projects", project_id)

    def test_get_parent_routine_not_found(self):
        """Should return None when routine not found."""
        mock_session = MagicMock()
        routine_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = get_parent_resource("routines", routine_id, mock_session)
        assert result is None

    def test_get_parent_routine_no_project_id(self):
        """Should return None when routine has no project_id."""
        mock_session = MagicMock()
        routine_id = UUID("12345678-1234-5678-1234-567812345678")

        mock_routine = MagicMock()
        mock_routine.project_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_routine
        mock_session.execute.return_value = mock_result

        result = get_parent_resource("routines", routine_id, mock_session)
        assert result is None

    # =========================================================================
    # Execution hierarchy tests
    # =========================================================================

    def test_get_parent_project_from_execution(self):
        """Should return (projects, uuid) for execution via routine (single JOIN query)."""
        mock_session = MagicMock()
        execution_id = UUID("12345678-1234-5678-1234-567812345678")
        project_id = UUID("87654321-4321-8765-4321-876543218765")

        # JOIN query returns project_id directly
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = project_id
        mock_session.execute.return_value = mock_result

        result = get_parent_resource("executions", execution_id, mock_session)
        assert result == ("projects", project_id)

    def test_get_parent_execution_not_found(self):
        """Should return None when execution not found (JOIN returns None)."""
        mock_session = MagicMock()
        execution_id = UUID("12345678-1234-5678-1234-567812345678")

        # JOIN query returns None when execution or routine not found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = get_parent_resource("executions", execution_id, mock_session)
        assert result is None

    def test_get_parent_execution_no_routine_id(self):
        """Should return None when execution has no routine_id (JOIN returns None)."""
        mock_session = MagicMock()
        execution_id = UUID("12345678-1234-5678-1234-567812345678")

        # JOIN query returns None when routine_id is NULL
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = get_parent_resource("executions", execution_id, mock_session)
        assert result is None

    def test_get_parent_execution_routine_not_found(self):
        """Should return None when execution's routine not found (JOIN returns None)."""
        mock_session = MagicMock()
        execution_id = UUID("12345678-1234-5678-1234-567812345678")

        # JOIN query returns None when routine doesn't exist
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = get_parent_resource("executions", execution_id, mock_session)
        assert result is None

    # =========================================================================
    # Submission hierarchy tests
    # =========================================================================

    def test_get_parent_project_from_submission(self):
        """Should return (projects, uuid) for submission via JOINs (single query)."""
        mock_session = MagicMock()
        submission_id = UUID("12345678-1234-5678-1234-567812345678")
        project_id = UUID("87654321-4321-8765-4321-876543218765")

        # JOIN query returns project_id directly
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = project_id
        mock_session.execute.return_value = mock_result

        result = get_parent_resource("submissions", submission_id, mock_session)
        assert result == ("projects", project_id)

    def test_get_parent_submission_not_found(self):
        """Should return None when submission not found (JOIN returns None)."""
        mock_session = MagicMock()
        submission_id = UUID("12345678-1234-5678-1234-567812345678")

        # JOIN query returns None when submission not found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = get_parent_resource("submissions", submission_id, mock_session)
        assert result is None

    def test_get_parent_submission_no_execution_id(self):
        """Should return None when submission has no execution_id (JOIN returns None)."""
        mock_session = MagicMock()
        submission_id = UUID("12345678-1234-5678-1234-567812345678")

        # JOIN query returns None when execution_id is NULL
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = get_parent_resource("submissions", submission_id, mock_session)
        assert result is None

    def test_get_parent_submission_execution_not_found(self):
        """Should return None when submission's execution not found (JOIN returns None)."""
        mock_session = MagicMock()
        submission_id = UUID("12345678-1234-5678-1234-567812345678")

        # JOIN query returns None when execution doesn't exist
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = get_parent_resource("submissions", submission_id, mock_session)
        assert result is None

    def test_get_parent_submission_routine_not_found(self):
        """Should return None when submission's routine not found (JOIN returns None)."""
        mock_session = MagicMock()
        submission_id = UUID("12345678-1234-5678-1234-567812345678")

        # JOIN query returns None when routine doesn't exist
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = get_parent_resource("submissions", submission_id, mock_session)
        assert result is None
