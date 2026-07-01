"""Tests for Store Owner role permissions and access control."""

from unittest.mock import MagicMock
from uuid import UUID

from pytest_mock import MockerFixture

from services.auth_service.authorization import check_permission, get_role_permissions


class TestStoreOwnerPermissions:
    """Tests for Store Owner role permission configuration."""

    def test_store_owner_has_project_read(self) -> None:
        """Store Owner should have project.read permission."""
        perms = get_role_permissions("store_owner")
        assert "project.read" in perms

    def test_store_owner_has_project_write(self) -> None:
        """Store Owner should have project.write permission."""
        perms = get_role_permissions("store_owner")
        assert "project.write" in perms

    def test_store_owner_has_agent_read_only_permission(self) -> None:
        """Store Owner should be able to read but not modify agents."""
        perms = get_role_permissions("store_owner")
        assert "agent.read" in perms
        assert "agent.create" not in perms
        assert "agent.write" not in perms
        assert "agent.delete" not in perms

    def test_store_owner_does_not_have_account_history_read(self) -> None:
        """Store Owner should not have account-scoped history permissions."""
        perms = get_role_permissions("store_owner")
        assert "history.read" not in perms

    def test_store_owner_has_account_read(self) -> None:
        """Store Owner should have account.read permission."""
        perms = get_role_permissions("store_owner")
        assert "account.read" in perms

    def test_store_owner_has_account_status_read(self) -> None:
        """Store Owner should have account.status.read permission."""
        perms = get_role_permissions("store_owner")
        assert "account.status.read" in perms

    def test_store_owner_cannot_modify_account(self) -> None:
        """Store Owner should NOT have account.write permission."""
        perms = get_role_permissions("store_owner")
        assert "account.write" not in perms

    def test_store_owner_cannot_manage_billing(self) -> None:
        """Store Owner should NOT have billing permissions."""
        perms = get_role_permissions("store_owner")
        assert "account.billing.read" not in perms
        assert "account.billing.write" not in perms

    def test_store_owner_has_scoped_team_permission(self) -> None:
        """Store Owner should have scoped team management permission."""
        perms = get_role_permissions("store_owner")
        assert "team.manage" in perms
        assert "account.team_manage" not in perms

    def test_store_owner_has_legacy_operations_read_permissions(self) -> None:
        """Store Owner should pass legacy Operations read route checks."""
        perms = get_role_permissions("store_owner")
        assert "routine.read" in perms
        assert "execution.read.today" in perms
        assert "execution.read.history" in perms
        assert "routine.write" not in perms

    def test_store_owner_has_submission_workflow_permissions(self) -> None:
        """Store Owner should pass legacy submission workflow route checks."""
        perms = get_role_permissions("store_owner")
        assert "submission.create" in perms
        assert "submission.write" in perms
        assert "submission.review" not in perms

    def test_store_owner_cannot_export_data(self) -> None:
        """Store Owner should NOT have data export permission (simplified scope)."""
        perms = get_role_permissions("store_owner")
        assert "data.export" not in perms

    def test_store_owner_cannot_approve_plans(self) -> None:
        """Store Owner should NOT have plan approval permission."""
        perms = get_role_permissions("store_owner")
        assert "plan.approve" not in perms


class TestStoreOwnerAccessControl:
    """Tests for Store Owner access control on assigned projects."""

    def test_store_owner_can_access_assigned_project(
        self, mocker: MockerFixture
    ) -> None:
        """Store Owner should be able to access their assigned project."""
        mock_session = MagicMock()
        user_id = UUID("12345678-1234-5678-1234-567812345678")
        project_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch(
            "services.auth_service.authorization.resolve_resource_identifier",
            return_value=project_id,
        )
        mock_role_repo = mocker.patch(
            "services.auth_service.authorization.ResourceRoleAssignmentRepository"
        )
        mock_role_repo.return_value.get_roles_for_resource.return_value = [
            "store_owner"
        ]

        result = check_permission(
            user_id=user_id,
            resource_id=f"projects/{project_id}",
            permission_name="project.read",
            session=mock_session,
            check_hierarchy=False,
        )
        assert result is True

    def test_store_owner_can_write_to_assigned_project(
        self, mocker: MockerFixture
    ) -> None:
        """Store Owner should be able to modify their assigned project settings."""
        mock_session = MagicMock()
        user_id = UUID("12345678-1234-5678-1234-567812345678")
        project_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch(
            "services.auth_service.authorization.resolve_resource_identifier",
            return_value=project_id,
        )
        mock_role_repo = mocker.patch(
            "services.auth_service.authorization.ResourceRoleAssignmentRepository"
        )
        mock_role_repo.return_value.get_roles_for_resource.return_value = [
            "store_owner"
        ]

        result = check_permission(
            user_id=user_id,
            resource_id=f"projects/{project_id}",
            permission_name="project.write",
            session=mock_session,
            check_hierarchy=False,
        )
        assert result is True

    def test_store_owner_cannot_create_agents_for_assigned_project(
        self, mocker: MockerFixture
    ) -> None:
        """Store Owner should not be able to create agents directly."""
        mock_session = MagicMock()
        user_id = UUID("12345678-1234-5678-1234-567812345678")
        project_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch(
            "services.auth_service.authorization.resolve_resource_identifier",
            return_value=project_id,
        )
        mock_role_repo = mocker.patch(
            "services.auth_service.authorization.ResourceRoleAssignmentRepository"
        )
        mock_role_repo.return_value.get_roles_for_resource.return_value = [
            "store_owner"
        ]

        result = check_permission(
            user_id=user_id,
            resource_id=f"projects/{project_id}",
            permission_name="agent.create",
            session=mock_session,
            check_hierarchy=False,
        )
        assert result is False

    def test_store_owner_can_manage_team_for_assigned_project(
        self, mocker: MockerFixture
    ) -> None:
        """Store Owner can pass scoped team management checks on assigned projects."""
        mock_session = MagicMock()
        user_id = UUID("12345678-1234-5678-1234-567812345678")
        project_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch(
            "services.auth_service.authorization.resolve_resource_identifier",
            return_value=project_id,
        )
        mock_role_repo = mocker.patch(
            "services.auth_service.authorization.ResourceRoleAssignmentRepository"
        )
        mock_role_repo.return_value.get_roles_for_resource.return_value = [
            "store_owner"
        ]

        result = check_permission(
            user_id=user_id,
            resource_id=f"projects/{project_id}",
            permission_name="team.manage",
            session=mock_session,
            check_hierarchy=False,
        )
        assert result is True

    def test_store_owner_cannot_read_account_history_for_assigned_project(
        self, mocker: MockerFixture
    ) -> None:
        """Store Owner should not get account-scoped history.read via project role."""
        mock_session = MagicMock()
        user_id = UUID("12345678-1234-5678-1234-567812345678")
        project_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch(
            "services.auth_service.authorization.resolve_resource_identifier",
            return_value=project_id,
        )
        mock_role_repo = mocker.patch(
            "services.auth_service.authorization.ResourceRoleAssignmentRepository"
        )
        mock_role_repo.return_value.get_roles_for_resource.return_value = [
            "store_owner"
        ]

        result = check_permission(
            user_id=user_id,
            resource_id=f"projects/{project_id}",
            permission_name="history.read",
            session=mock_session,
            check_hierarchy=False,
        )
        assert result is False

    def test_store_owner_cannot_access_unassigned_project(
        self, mocker: MockerFixture
    ) -> None:
        """Store Owner should NOT be able to access projects they're not assigned to."""
        mock_session = MagicMock()
        user_id = UUID("12345678-1234-5678-1234-567812345678")
        project_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch(
            "services.auth_service.authorization.resolve_resource_identifier",
            return_value=project_id,
        )
        mock_role_repo = mocker.patch(
            "services.auth_service.authorization.ResourceRoleAssignmentRepository"
        )
        # No role on this project
        mock_role_repo.return_value.get_roles_for_resource.return_value = []
        mocker.patch(
            "services.auth_service.authorization.get_parent_resource",
            return_value=None,
        )

        result = check_permission(
            user_id=user_id,
            resource_id=f"projects/{project_id}",
            permission_name="project.read",
            session=mock_session,
            check_hierarchy=True,
        )
        assert result is False

    def test_store_owner_cannot_modify_billing(self, mocker: MockerFixture) -> None:
        """Store Owner should NOT be able to modify billing settings."""
        mock_session = MagicMock()
        user_id = UUID("12345678-1234-5678-1234-567812345678")
        account_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch(
            "services.auth_service.authorization.resolve_resource_identifier",
            return_value=account_id,
        )
        mock_role_repo = mocker.patch(
            "services.auth_service.authorization.ResourceRoleAssignmentRepository"
        )
        # Store owner has no account-level role
        mock_role_repo.return_value.get_roles_for_resource.return_value = []
        mocker.patch(
            "services.auth_service.authorization.get_parent_resource",
            return_value=None,
        )

        result = check_permission(
            user_id=user_id,
            resource_id=f"accounts/{account_id}",
            permission_name="account.billing.write",
            session=mock_session,
            check_hierarchy=True,
        )
        assert result is False


class TestStoreOwnerHierarchyBehavior:
    """Tests for Store Owner role within the resource hierarchy."""

    def test_store_owner_role_does_not_grant_account_level_access(
        self, mocker: MockerFixture
    ) -> None:
        """Store Owner role on project should NOT grant account-level permissions."""
        mock_session = MagicMock()
        user_id = UUID("12345678-1234-5678-1234-567812345678")
        account_id = UUID("87654321-4321-8765-4321-876543218765")

        mocker.patch(
            "services.auth_service.authorization.resolve_resource_identifier",
            return_value=account_id,
        )
        mock_role_repo = mocker.patch(
            "services.auth_service.authorization.ResourceRoleAssignmentRepository"
        )
        # Store owner only has project-level role, not account-level
        mock_role_repo.return_value.get_roles_for_resource.return_value = []
        mocker.patch(
            "services.auth_service.authorization.get_parent_resource",
            return_value=None,
        )

        result = check_permission(
            user_id=user_id,
            resource_id=f"accounts/{account_id}",
            permission_name="account.write",
            session=mock_session,
            check_hierarchy=True,
        )
        assert result is False

    def test_account_owner_can_access_all_projects(self, mocker: MockerFixture) -> None:
        """Account owner should retain full access to all projects."""
        mock_session = MagicMock()
        user_id = UUID("12345678-1234-5678-1234-567812345678")
        project_id = UUID("87654321-4321-8765-4321-876543218765")
        account_id = UUID("11111111-1111-1111-1111-111111111111")

        mocker.patch(
            "services.auth_service.authorization.resolve_resource_identifier",
            return_value=project_id,
        )
        mock_role_repo = mocker.patch(
            "services.auth_service.authorization.ResourceRoleAssignmentRepository"
        )
        # First call (project): no role
        # Second call (account): owner role
        mock_role_repo.return_value.get_roles_for_resource.side_effect = [
            [],
            ["owner"],
        ]
        mocker.patch(
            "services.auth_service.authorization.get_parent_resource",
            return_value=("accounts", account_id),
        )

        result = check_permission(
            user_id=user_id,
            resource_id=f"projects/{project_id}",
            permission_name="project.write",
            session=mock_session,
            check_hierarchy=True,
        )
        assert result is True
