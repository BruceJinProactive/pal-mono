"""Tests for RBAC authorization logic."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest

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

    def test_parse_resource_id_valid_account_name(self):
        """Should parse valid accounts/name format."""
        rtype, identifier = parse_resource_id("accounts/palona")
        assert rtype == "accounts"
        assert identifier == "palona"

    def test_parse_resource_id_valid_project_uuid(self):
        """Should parse valid projects/uuid format."""
        uuid_str = "12345678-1234-5678-1234-567812345678"
        rtype, identifier = parse_resource_id(f"projects/{uuid_str}")
        assert rtype == "projects"
        assert identifier == uuid_str

    def test_parse_resource_id_valid_routines(self):
        """Should accept routines as valid resource type."""
        assert "routines" in VALID_RESOURCE_TYPES
        uuid_str = "12345678-1234-5678-1234-567812345678"
        rtype, identifier = parse_resource_id(f"routines/{uuid_str}")
        assert rtype == "routines"
        assert identifier == uuid_str

    def test_parse_resource_id_valid_executions(self):
        """Should accept executions as valid resource type."""
        assert "executions" in VALID_RESOURCE_TYPES
        uuid_str = "12345678-1234-5678-1234-567812345678"
        rtype, identifier = parse_resource_id(f"executions/{uuid_str}")
        assert rtype == "executions"
        assert identifier == uuid_str

    def test_parse_resource_id_valid_submissions(self):
        """Should accept submissions as valid resource type."""
        assert "submissions" in VALID_RESOURCE_TYPES
        uuid_str = "12345678-1234-5678-1234-567812345678"
        rtype, identifier = parse_resource_id(f"submissions/{uuid_str}")
        assert rtype == "submissions"
        assert identifier == uuid_str

    def test_parse_resource_id_invalid_format_too_many_slashes(self):
        """Should raise ValueError for too many slashes."""
        with pytest.raises(ValueError, match="Invalid resource_id format"):
            parse_resource_id("invalid/format/too/many")

    def test_parse_resource_id_invalid_format_no_slash(self):
        """Should raise ValueError for no slash."""
        with pytest.raises(ValueError, match="Invalid resource_id format"):
            parse_resource_id("invalid_format")

    def test_parse_resource_id_invalid_resource_type(self):
        """Should raise ValueError for unknown resource type."""
        with pytest.raises(ValueError, match="Invalid resource_type"):
            parse_resource_id("unknown_type/identifier")

    def test_parse_resource_id_empty_identifier(self):
        """Should raise ValueError for empty identifier."""
        with pytest.raises(ValueError, match="identifier cannot be empty"):
            parse_resource_id("accounts/")

    def test_parse_resource_id_whitespace_identifier(self):
        """Should raise ValueError for whitespace-only identifier."""
        with pytest.raises(ValueError, match="identifier cannot be empty"):
            parse_resource_id("accounts/   ")


class TestValidResourceTypes:
    """Tests for VALID_RESOURCE_TYPES constant."""

    def test_valid_resource_types_contains_accounts(self):
        """Should contain accounts."""
        assert "accounts" in VALID_RESOURCE_TYPES

    def test_valid_resource_types_contains_projects(self):
        """Should contain projects."""
        assert "projects" in VALID_RESOURCE_TYPES

    def test_valid_resource_types_contains_agents(self):
        """Should contain agents."""
        assert "agents" in VALID_RESOURCE_TYPES

    def test_valid_resource_types_contains_routine_resources(self):
        """Should contain routine-related resources."""
        assert "routines" in VALID_RESOURCE_TYPES
        assert "executions" in VALID_RESOURCE_TYPES
        assert "submissions" in VALID_RESOURCE_TYPES


class TestGetRolePermissions:
    """Tests for get_role_permissions function."""

    def test_get_role_permissions_owner(self):
        """Owner should have wildcard permission."""
        perms = get_role_permissions("owner")
        assert perms == {"*"}

    def test_get_role_permissions_manager(self):
        """Manager should have management permissions."""
        perms = get_role_permissions("manager")
        assert "project.write" in perms
        assert "project.create" in perms
        assert "project.delete" in perms
        assert "agent.write" in perms
        assert "routine.write" in perms
        assert "submission.review" in perms
        # Manager should have granular execution permissions
        assert "execution.read.today" in perms
        assert "execution.read.history" in perms
        # Manager should have submission write permission
        assert "submission.write" in perms

    def test_get_role_permissions_viewer(self):
        """Viewer should have read-only permissions."""
        perms = get_role_permissions("viewer")
        assert "project.read" in perms
        assert "agent.read" in perms
        assert "routine.read" in perms
        # Viewer should have granular execution permissions
        assert "execution.read.today" in perms
        assert "execution.read.history" in perms
        # Should not have write permissions
        assert "project.write" not in perms
        assert "routine.write" not in perms
        assert "submission.review" not in perms
        # Viewer should NOT have submission write permission
        assert "submission.write" not in perms

    def test_get_role_permissions_staff(self):
        """Staff should have limited permissions."""
        perms = get_role_permissions("staff")
        assert "project.read" in perms
        assert "routine.read" in perms
        assert "submission.create" in perms
        # Staff should only have today permission, not history
        assert "execution.read.today" in perms
        assert "execution.read.history" not in perms
        # Staff should have submission write permission
        assert "submission.write" in perms
        # Should not have elevated permissions
        assert "submission.review" not in perms
        assert "routine.write" not in perms
        assert "project.write" not in perms

    def test_get_role_permissions_unknown(self):
        """Unknown role should return empty set."""
        perms = get_role_permissions("nonexistent_role")
        assert perms == set()


class TestGetMergedPermissions:
    """Tests for get_merged_permissions function."""

    def test_get_merged_permissions_empty_list(self):
        """Empty list should return empty set."""
        perms = get_merged_permissions([])
        assert perms == set()

    def test_get_merged_permissions_single_role(self):
        """Single role should return that role's permissions."""
        perms = get_merged_permissions(["staff"])
        assert "routine.read" in perms
        assert "submission.create" in perms

    def test_get_merged_permissions_multiple_roles(self):
        """Multiple roles should return merged permissions."""
        perms = get_merged_permissions(["staff", "viewer"])
        # Should have permissions from both roles
        assert "routine.read" in perms  # From both
        assert "submission.create" in perms  # From staff
        assert "project.read" in perms  # From viewer

    def test_get_merged_permissions_with_owner(self):
        """If owner is in roles, should return wildcard."""
        perms = get_merged_permissions(["staff", "owner"])
        assert perms == {"*"}

    def test_get_merged_permissions_owner_only(self):
        """Owner role should return wildcard."""
        perms = get_merged_permissions(["owner"])
        assert perms == {"*"}

    def test_get_merged_permissions_manager_staff(self):
        """Manager + staff should have all manager and staff permissions."""
        perms = get_merged_permissions(["manager", "staff"])
        # Staff permissions
        assert "submission.create" in perms
        # Manager permissions
        assert "submission.review" in perms
        assert "routine.write" in perms


class TestGetUserRoleOnAccount:
    """Tests for get_user_role_on_account function."""

    def test_get_user_role_on_account_owner(self, mocker):
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

    def test_get_user_role_on_account_not_member(self, mocker):
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

    def test_get_user_role_on_account_no_role(self, mocker):
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

    def test_get_user_role_on_account_exception(self, mocker):
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

    def test_check_permission_owner_has_all(self, mocker):
        """Owner should have access to any permission."""
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
        assert result is True

    def test_check_permission_manager_can_write(self, mocker):
        """Manager should be able to use project.write."""
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

        result = check_permission(
            user_id=user_id,
            resource_id=f"accounts/{account_id}",
            permission_name="project.write",
            session=mock_session,
            check_hierarchy=False,
        )
        assert result is True

    def test_check_permission_manager_cannot_billing(self, mocker):
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

    def test_check_permission_viewer_can_read(self, mocker):
        """Viewer should be able to use project.read."""
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

    def test_check_permission_viewer_cannot_write(self, mocker):
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

    def test_check_permission_staff_can_read_execution_today(self, mocker):
        """Staff should be able to use execution.read.today."""
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
        assert result is True

    def test_check_permission_staff_can_create_submission(self, mocker):
        """Staff should be able to use submission.create."""
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
        assert result is True

    def test_check_permission_staff_cannot_review(self, mocker):
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

    def test_check_permission_staff_cannot_write_routine(self, mocker):
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

    def test_check_permission_hierarchy_project_to_account(self, mocker):
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

    def test_check_permission_no_hierarchy_when_disabled(self, mocker):
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

    def test_check_permission_invalid_resource_id_format(self):
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

    def test_check_permission_resolution_failure(self, mocker):
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

    def test_check_permission_no_role_no_hierarchy(self, mocker):
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
