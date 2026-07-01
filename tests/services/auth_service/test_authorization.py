"""Tests for RBAC authorization logic."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest
from pytest_mock import MockerFixture

from services.auth_service.authorization import (
    VALID_RESOURCE_TYPES,
    check_permission,
    get_merged_permissions,
    get_role_permissions,
    get_user_role_on_account,
    parse_resource_id,
)


class TestParseResourceId:
    """Tests for parse_resource_id function."""

    def test_parse_resource_id_valid_account_name(self) -> None:
        """Should parse valid accounts/name format."""
        rtype, identifier = parse_resource_id("accounts/palona")
        assert rtype == "accounts"
        assert identifier == "palona"

    def test_parse_resource_id_valid_project_uuid(self) -> None:
        """Should parse valid projects/uuid format."""
        uuid_str = "12345678-1234-5678-1234-567812345678"
        rtype, identifier = parse_resource_id(f"projects/{uuid_str}")
        assert rtype == "projects"
        assert identifier == uuid_str

    def test_parse_resource_id_valid_routines(self) -> None:
        """Should accept routines as valid resource type."""
        assert "routines" in VALID_RESOURCE_TYPES
        uuid_str = "12345678-1234-5678-1234-567812345678"
        rtype, identifier = parse_resource_id(f"routines/{uuid_str}")
        assert rtype == "routines"
        assert identifier == uuid_str

    def test_parse_resource_id_valid_executions(self) -> None:
        """Should accept executions as valid resource type."""
        assert "executions" in VALID_RESOURCE_TYPES
        uuid_str = "12345678-1234-5678-1234-567812345678"
        rtype, identifier = parse_resource_id(f"executions/{uuid_str}")
        assert rtype == "executions"
        assert identifier == uuid_str

    def test_parse_resource_id_valid_submissions(self) -> None:
        """Should accept submissions as valid resource type."""
        assert "submissions" in VALID_RESOURCE_TYPES
        uuid_str = "12345678-1234-5678-1234-567812345678"
        rtype, identifier = parse_resource_id(f"submissions/{uuid_str}")
        assert rtype == "submissions"
        assert identifier == uuid_str

    def test_parse_resource_id_invalid_format_too_many_slashes(self) -> None:
        """Should raise ValueError for too many slashes."""
        with pytest.raises(ValueError, match="Invalid resource_id format"):
            parse_resource_id("invalid/format/too/many")

    def test_parse_resource_id_invalid_format_no_slash(self) -> None:
        """Should raise ValueError for no slash."""
        with pytest.raises(ValueError, match="Invalid resource_id format"):
            parse_resource_id("invalid_format")

    def test_parse_resource_id_invalid_resource_type(self) -> None:
        """Should raise ValueError for unknown resource type."""
        with pytest.raises(ValueError, match="Invalid resource_type"):
            parse_resource_id("unknown_type/identifier")

    def test_parse_resource_id_empty_identifier(self) -> None:
        """Should raise ValueError for empty identifier."""
        with pytest.raises(ValueError, match="identifier cannot be empty"):
            parse_resource_id("accounts/")

    def test_parse_resource_id_whitespace_identifier(self) -> None:
        """Should raise ValueError for whitespace-only identifier."""
        with pytest.raises(ValueError, match="identifier cannot be empty"):
            parse_resource_id("accounts/   ")


class TestValidResourceTypes:
    """Tests for VALID_RESOURCE_TYPES constant."""

    def test_valid_resource_types_contains_accounts(self) -> None:
        """Should contain accounts."""
        assert "accounts" in VALID_RESOURCE_TYPES

    def test_valid_resource_types_contains_projects(self) -> None:
        """Should contain projects."""
        assert "projects" in VALID_RESOURCE_TYPES

    def test_valid_resource_types_contains_agents(self) -> None:
        """Should contain agents."""
        assert "agents" in VALID_RESOURCE_TYPES

    def test_valid_resource_types_contains_routine_resources(self) -> None:
        """Should contain routine-related resources."""
        assert "routines" in VALID_RESOURCE_TYPES
        assert "executions" in VALID_RESOURCE_TYPES
        assert "submissions" in VALID_RESOURCE_TYPES


class TestGetRolePermissions:
    """Tests for get_role_permissions function."""

    def test_get_role_permissions_account_admin(self) -> None:
        """Account Admin should have account-wide customer permissions."""
        perms = get_role_permissions("account_admin")
        assert "project.write" in perms
        assert "project.create" in perms
        assert "project.delete" in perms
        assert "account.billing.write" in perms
        assert "account.team_manage" in perms
        assert "agent.read" in perms
        assert "agent.write" not in perms
        assert "operation.read" in perms
        assert "operation.write" not in perms
        assert "*" not in perms

    def test_get_role_permissions_store_owner(self) -> None:
        """Store Owner should have store-scoped write permissions."""
        perms = get_role_permissions("store_owner")
        assert "project.read" in perms
        assert "project.write" in perms
        assert "agent.read" in perms
        assert "agent.write" not in perms
        assert "team.manage" in perms
        assert "history.read" not in perms
        assert "feedback.write" not in perms
        assert "catering.write" in perms
        assert "billing.read" not in perms
        assert "routine.read" in perms
        assert "routine.write" not in perms
        assert "execution.read.today" in perms
        assert "submission.create" in perms
        assert "submission.review" not in perms

    def test_get_role_permissions_store_member(self) -> None:
        """Store Member should be read-mostly."""
        perms = get_role_permissions("store_member")
        assert "project.read" in perms
        assert "project.write" not in perms
        assert "agent.read" in perms
        assert "agent.write" not in perms
        assert "team.manage" not in perms
        assert "history.read" not in perms
        assert "feedback.write" not in perms
        assert "catering.read" in perms
        assert "catering.write" not in perms
        assert "billing.read" not in perms
        assert "routine.read" in perms
        assert "routine.write" not in perms
        assert "execution.read.today" in perms
        assert "submission.create" in perms
        assert "submission.review" not in perms

    def test_get_role_permissions_legacy_aliases(self) -> None:
        """Legacy roles should use the migration policy."""
        assert get_role_permissions("owner") == get_role_permissions("account_admin")
        assert get_role_permissions("manager") == get_role_permissions("store_member")
        assert get_role_permissions("viewer") == get_role_permissions("store_member")

    def test_get_role_permissions_staff(self) -> None:
        """Staff should fail closed for customer-console RBAC."""
        perms = get_role_permissions("staff")
        assert perms == set()

    def test_get_role_permissions_unknown(self) -> None:
        """Unknown role should return empty set."""
        perms = get_role_permissions("nonexistent_role")
        assert perms == set()


class TestGetMergedPermissions:
    """Tests for get_merged_permissions function."""

    def test_get_merged_permissions_empty_list(self) -> None:
        """Empty list should return empty set."""
        perms = get_merged_permissions([])
        assert perms == set()

    def test_get_merged_permissions_single_role(self) -> None:
        """Single role should return that role's permissions."""
        perms = get_merged_permissions(["store_member"])
        assert "project.read" in perms
        assert "agent.read" in perms

    def test_get_merged_permissions_multiple_roles(self) -> None:
        """Multiple roles should return merged permissions."""
        perms = get_merged_permissions(["store_member", "store_owner"])
        # Should have permissions from both roles
        assert "project.read" in perms
        assert "project.write" in perms
        assert "catering.read" in perms

    def test_get_merged_permissions_with_owner_alias(self) -> None:
        """Legacy owner should merge as Account Admin, not wildcard."""
        perms = get_merged_permissions(["staff", "owner"])
        assert perms == get_role_permissions("account_admin")

    def test_get_merged_permissions_owner_only(self) -> None:
        """Owner role should return Account Admin permissions during migration."""
        perms = get_merged_permissions(["owner"])
        assert perms == get_role_permissions("account_admin")
        assert "*" not in perms

    def test_get_merged_permissions_manager_staff(self) -> None:
        """Legacy Manager should not inherit Staff permissions."""
        perms = get_merged_permissions(["manager", "staff"])
        assert perms == get_role_permissions("store_member")
        assert "project.write" not in perms
        assert "submission.create" in perms
        assert "submission.review" not in perms
        assert "routine.write" not in perms


class TestGetUserRoleOnAccount:
    """Tests for get_user_role_on_account function."""

    def test_get_user_role_on_account_owner(self, mocker: MockerFixture) -> None:
        """Should return 'owner' for account owner."""
        mock_session = MagicMock()
        user_id = UUID("12345678-1234-5678-1234-567812345678")
        account_id = UUID("87654321-4321-8765-4321-876543218765")

        # Mock account user repo to confirm membership
        mock_account_user_repo = mocker.patch(
            "services.auth_service.authorization.AccountUserRepository"
        )
        mock_account_user_repo.return_value.is_member.return_value = True

        # Mock role repo to return owner role
        mock_role_repo = mocker.patch(
            "services.auth_service.authorization.ResourceRoleAssignmentRepository"
        )
        mock_role_repo.return_value.get_roles_for_resource.return_value = ["owner"]

        role = get_user_role_on_account(user_id, account_id, mock_session)
        assert role == "owner"

    def test_get_user_role_on_account_not_member(self, mocker: MockerFixture) -> None:
        """Should return None for non-member."""
        mock_session = MagicMock()
        user_id = UUID("12345678-1234-5678-1234-567812345678")
        account_id = UUID("87654321-4321-8765-4321-876543218765")

        mock_account_user_repo = mocker.patch(
            "services.auth_service.authorization.AccountUserRepository"
        )
        mock_account_user_repo.return_value.is_member.return_value = False

        role = get_user_role_on_account(user_id, account_id, mock_session)
        assert role is None

    def test_get_user_role_on_account_no_role(self, mocker: MockerFixture) -> None:
        """Should return None when user has no role assigned."""
        mock_session = MagicMock()
        user_id = UUID("12345678-1234-5678-1234-567812345678")
        account_id = UUID("87654321-4321-8765-4321-876543218765")

        mock_account_user_repo = mocker.patch(
            "services.auth_service.authorization.AccountUserRepository"
        )
        mock_account_user_repo.return_value.is_member.return_value = True

        mock_role_repo = mocker.patch(
            "services.auth_service.authorization.ResourceRoleAssignmentRepository"
        )
        mock_role_repo.return_value.get_roles_for_resource.return_value = []

        role = get_user_role_on_account(user_id, account_id, mock_session)
        assert role is None

    def test_get_user_role_on_account_exception(self, mocker: MockerFixture) -> None:
        """Should return None on database error."""
        mock_session = MagicMock()
        user_id = UUID("12345678-1234-5678-1234-567812345678")
        account_id = UUID("87654321-4321-8765-4321-876543218765")

        mock_account_user_repo = mocker.patch(
            "services.auth_service.authorization.AccountUserRepository"
        )
        mock_account_user_repo.return_value.is_member.side_effect = Exception(
            "DB error"
        )

        role = get_user_role_on_account(user_id, account_id, mock_session)
        assert role is None


class TestCheckPermission:
    """Tests for check_permission function."""

    def test_check_permission_owner_alias_can_write_project(
        self, mocker: MockerFixture
    ) -> None:
        """Legacy Owner should use Account Admin permissions during migration."""
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
        mock_role_repo.return_value.get_roles_for_resource.return_value = ["owner"]

        result = check_permission(
            user_id=user_id,
            resource_id=f"accounts/{account_id}",
            permission_name="project.write",
            session=mock_session,
            check_hierarchy=False,
        )
        assert result is True

    def test_check_permission_owner_alias_no_longer_wildcard(
        self, mocker: MockerFixture
    ) -> None:
        """Legacy Owner should not grant arbitrary wildcard permissions."""
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
        mock_role_repo.return_value.get_roles_for_resource.return_value = ["owner"]

        result = check_permission(
            user_id=user_id,
            resource_id=f"accounts/{account_id}",
            permission_name="any.permission",
            session=mock_session,
            check_hierarchy=False,
        )
        assert result is False

    def test_check_permission_manager_cannot_write(self, mocker: MockerFixture) -> None:
        """Legacy Manager should map to Store Member and not write projects."""
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
        mock_role_repo.return_value.get_roles_for_resource.return_value = ["manager"]
        mocker.patch(
            "services.auth_service.authorization.get_parent_resource",
            return_value=None,
        )

        result = check_permission(
            user_id=user_id,
            resource_id=f"accounts/{account_id}",
            permission_name="project.write",
            session=mock_session,
            check_hierarchy=True,
        )
        assert result is False

    def test_check_permission_manager_cannot_billing(
        self, mocker: MockerFixture
    ) -> None:
        """Manager should not be able to use account.billing.write."""
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
        mock_role_repo.return_value.get_roles_for_resource.return_value = ["manager"]
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

    def test_check_permission_viewer_can_read(self, mocker: MockerFixture) -> None:
        """Legacy Viewer should be able to use Store Member read permissions."""
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
        mock_role_repo.return_value.get_roles_for_resource.return_value = ["viewer"]

        result = check_permission(
            user_id=user_id,
            resource_id=f"accounts/{account_id}",
            permission_name="project.read",
            session=mock_session,
            check_hierarchy=False,
        )
        assert result is True

    def test_check_permission_viewer_cannot_write(self, mocker: MockerFixture) -> None:
        """Viewer should not be able to use project.write."""
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
        mock_role_repo.return_value.get_roles_for_resource.return_value = ["viewer"]
        mocker.patch(
            "services.auth_service.authorization.get_parent_resource",
            return_value=None,
        )

        result = check_permission(
            user_id=user_id,
            resource_id=f"accounts/{account_id}",
            permission_name="project.write",
            session=mock_session,
            check_hierarchy=True,
        )
        assert result is False

    def test_check_permission_staff_cannot_read_execution_today(
        self, mocker: MockerFixture
    ) -> None:
        """Legacy Staff should fail closed for customer-console RBAC."""
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
        mock_role_repo.return_value.get_roles_for_resource.return_value = ["staff"]

        result = check_permission(
            user_id=user_id,
            resource_id=f"projects/{project_id}",
            permission_name="execution.read.today",
            session=mock_session,
            check_hierarchy=False,
        )
        assert result is False

    def test_check_permission_staff_cannot_create_submission(
        self, mocker: MockerFixture
    ) -> None:
        """Legacy Staff should not create submissions."""
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
        mock_role_repo.return_value.get_roles_for_resource.return_value = ["staff"]

        result = check_permission(
            user_id=user_id,
            resource_id=f"projects/{project_id}",
            permission_name="submission.create",
            session=mock_session,
            check_hierarchy=False,
        )
        assert result is False

    def test_check_permission_staff_cannot_review(self, mocker: MockerFixture) -> None:
        """Staff should not be able to review submissions."""
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
        mock_role_repo.return_value.get_roles_for_resource.return_value = ["staff"]
        mocker.patch(
            "services.auth_service.authorization.get_parent_resource",
            return_value=None,
        )

        result = check_permission(
            user_id=user_id,
            resource_id=f"projects/{project_id}",
            permission_name="submission.review",
            session=mock_session,
            check_hierarchy=True,
        )
        assert result is False

    def test_check_permission_staff_cannot_write_routine(
        self, mocker: MockerFixture
    ) -> None:
        """Staff should not be able to write routines."""
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
        mock_role_repo.return_value.get_roles_for_resource.return_value = ["staff"]
        mocker.patch(
            "services.auth_service.authorization.get_parent_resource",
            return_value=None,
        )

        result = check_permission(
            user_id=user_id,
            resource_id=f"projects/{project_id}",
            permission_name="routine.write",
            session=mock_session,
            check_hierarchy=True,
        )
        assert result is False

    def test_check_permission_hierarchy_project_to_account(
        self, mocker: MockerFixture
    ) -> None:
        """Permission on account should grant access to project via hierarchy."""
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

    def test_check_permission_no_hierarchy_when_disabled(
        self, mocker: MockerFixture
    ) -> None:
        """Should not check parents when check_hierarchy=False."""
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
        mock_role_repo.return_value.get_roles_for_resource.return_value = []

        mock_get_parent = mocker.patch(
            "services.auth_service.authorization.get_parent_resource"
        )

        result = check_permission(
            user_id=user_id,
            resource_id=f"projects/{project_id}",
            permission_name="project.write",
            session=mock_session,
            check_hierarchy=False,
        )
        assert result is False
        # get_parent_resource should not be called
        mock_get_parent.assert_not_called()

    def test_check_permission_invalid_resource_id_format(self) -> None:
        """Should return False for invalid resource_id format."""
        mock_session = MagicMock()
        user_id = UUID("12345678-1234-5678-1234-567812345678")

        result = check_permission(
            user_id=user_id,
            resource_id="invalid/format/too/many",
            permission_name="project.read",
            session=mock_session,
        )
        assert result is False

    def test_check_permission_resolution_failure(self, mocker: MockerFixture) -> None:
        """Should return False when resource resolution fails."""
        mock_session = MagicMock()
        user_id = UUID("12345678-1234-5678-1234-567812345678")

        mocker.patch(
            "services.auth_service.authorization.resolve_resource_identifier",
            side_effect=ValueError("Resource not found"),
        )

        result = check_permission(
            user_id=user_id,
            resource_id="accounts/nonexistent",
            permission_name="project.read",
            session=mock_session,
        )
        assert result is False

    def test_check_permission_no_role_no_hierarchy(self, mocker: MockerFixture) -> None:
        """Should return False when user has no role and no hierarchy to check."""
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
        mock_role_repo.return_value.get_roles_for_resource.return_value = []
        mocker.patch(
            "services.auth_service.authorization.get_parent_resource",
            return_value=None,
        )

        result = check_permission(
            user_id=user_id,
            resource_id=f"accounts/{account_id}",
            permission_name="project.read",
            session=mock_session,
            check_hierarchy=True,
        )
        assert result is False
