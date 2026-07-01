"""Tests for RBAC permission configuration."""

from services.auth_service.config import (
    PERMISSION_REGISTRY,
    RESOURCE_HIERARCHY,
    ROLE_PERMISSIONS,
    get_all_permissions,
    get_permission_display_name,
    get_permissions_for_resource,
)


class TestRolePermissions:
    """Tests for role permission configuration."""

    def test_account_admin_permissions(self) -> None:
        """Account Admin should have account-wide customer permissions."""
        perms = ROLE_PERMISSIONS["account_admin"]
        assert "account.read" in perms
        assert "account.write" in perms
        assert "account.billing.read" in perms
        assert "account.billing.write" in perms
        assert "account.team_manage" in perms
        assert "project.create" in perms
        assert "project.read" in perms
        assert "project.write" in perms
        assert "project.delete" in perms
        assert "agent.read" in perms
        assert "agent.create" not in perms
        assert "agent.write" not in perms
        assert "agent.delete" not in perms
        assert "operation.read" in perms
        assert "operation.write" not in perms
        assert "routine.read" in perms
        assert "routine.write" in perms
        assert "execution.read.today" in perms
        assert "execution.read.history" in perms
        assert "submission.create" in perms
        assert "submission.write" in perms
        assert "submission.review" in perms
        assert "*" not in perms

    def test_store_owner_permissions(self) -> None:
        """Store Owner should have store-scoped write permissions."""
        perms = ROLE_PERMISSIONS["store_owner"]
        assert "account.read" in perms
        assert "project.read" in perms
        assert "project.write" in perms
        assert "team.manage" in perms
        assert "history.read" not in perms
        assert "feedback.write" not in perms
        assert "catering.write" in perms
        assert "agent.read" in perms
        assert "agent.create" not in perms
        assert "agent.write" not in perms
        assert "agent.delete" not in perms
        assert "account.billing.read" not in perms
        assert "account.billing.write" not in perms
        assert "billing.read" not in perms
        assert "billing.write" not in perms
        assert "operation.read" in perms
        assert "operation.write" not in perms
        assert "routine.read" in perms
        assert "routine.write" not in perms
        assert "execution.read.today" in perms
        assert "execution.read.history" in perms
        assert "submission.create" in perms
        assert "submission.write" in perms
        assert "submission.review" not in perms

    def test_store_member_permissions(self) -> None:
        """Store Member should be read-mostly and store-scoped."""
        perms = ROLE_PERMISSIONS["store_member"]
        assert "account.read" in perms
        assert "project.read" in perms
        assert "project.write" not in perms
        assert "team.manage" not in perms
        assert "history.read" not in perms
        assert "feedback.write" not in perms
        assert "catering.read" in perms
        assert "catering.write" not in perms
        assert "agent.read" in perms
        assert "agent.create" not in perms
        assert "agent.write" not in perms
        assert "agent.delete" not in perms
        assert "account.billing.read" not in perms
        assert "billing.read" not in perms
        assert "operation.read" in perms
        assert "operation.write" not in perms
        assert "routine.read" in perms
        assert "routine.write" not in perms
        assert "execution.read.today" in perms
        assert "execution.read.history" in perms
        assert "submission.create" in perms
        assert "submission.write" in perms
        assert "submission.review" not in perms

    def test_legacy_owner_alias_matches_account_admin(self) -> None:
        """Legacy Owner should map to Account Admin permissions during migration."""
        assert ROLE_PERMISSIONS["owner"] == ROLE_PERMISSIONS["account_admin"]
        assert "*" not in ROLE_PERMISSIONS["owner"]

    def test_legacy_manager_viewer_alias_store_member(self) -> None:
        """Legacy Manager/Viewer collapse to Store Member during migration."""
        assert ROLE_PERMISSIONS["manager"] == ROLE_PERMISSIONS["store_member"]
        assert ROLE_PERMISSIONS["viewer"] == ROLE_PERMISSIONS["store_member"]

    def test_staff_is_fail_closed(self) -> None:
        """Legacy Staff should not retain customer-console permissions."""
        assert ROLE_PERMISSIONS["staff"] == set()

    def test_all_role_permissions_are_registered(self) -> None:
        """Every configured role permission should have registry metadata."""
        for role, permissions in ROLE_PERMISSIONS.items():
            assert permissions <= set(PERMISSION_REGISTRY.keys()), role


class TestResourceHierarchy:
    """Tests for resource hierarchy configuration."""

    def test_resource_hierarchy_routines(self) -> None:
        """Routines should belong to projects."""
        assert RESOURCE_HIERARCHY["routines"] == "projects"

    def test_resource_hierarchy_executions(self) -> None:
        """Executions should belong to routines."""
        assert RESOURCE_HIERARCHY["executions"] == "routines"

    def test_resource_hierarchy_submissions(self) -> None:
        """Submissions should belong to executions."""
        assert RESOURCE_HIERARCHY["submissions"] == "executions"

    def test_resource_hierarchy_projects(self) -> None:
        """Projects should belong to accounts."""
        assert RESOURCE_HIERARCHY["projects"] == "accounts"

    def test_resource_hierarchy_agents(self) -> None:
        """Agents should belong to accounts."""
        assert RESOURCE_HIERARCHY["agents"] == "accounts"

    def test_resource_hierarchy_accounts(self) -> None:
        """Accounts should be top-level (no parent)."""
        assert RESOURCE_HIERARCHY["accounts"] is None


class TestHelperFunctions:
    """Tests for config helper functions."""

    def test_get_all_permissions(self) -> None:
        """Should return all permission names from registry."""
        perms = get_all_permissions()
        assert isinstance(perms, set)
        assert "project.read" in perms
        assert "project.write" in perms
        assert "routine.read" in perms
        assert "submission.review" in perms
        assert "account.read" in perms

    def test_get_all_permissions_returns_all_registry_keys(self) -> None:
        """Should return exactly the keys from PERMISSION_REGISTRY."""
        perms = get_all_permissions()
        assert perms == set(PERMISSION_REGISTRY.keys())

    def test_get_permissions_for_resource_projects(self) -> None:
        """Should filter permissions for projects resource type."""
        project_perms = get_permissions_for_resource("projects")
        assert "project.create" in project_perms
        assert "project.read" in project_perms
        assert "project.write" in project_perms
        assert "project.delete" in project_perms
        # Should NOT include other resource permissions
        assert "agent.read" not in project_perms
        assert "routine.read" not in project_perms

    def test_get_permissions_for_resource_submissions(self) -> None:
        """Should filter permissions for submissions resource type."""
        submission_perms = get_permissions_for_resource("submissions")
        assert "submission.create" in submission_perms
        assert "submission.write" in submission_perms
        assert "submission.review" in submission_perms
        # Should NOT include other resource permissions
        assert "project.read" not in submission_perms
        assert "routine.read" not in submission_perms

    def test_get_permissions_for_resource_routines(self) -> None:
        """Should filter permissions for routines resource type."""
        routine_perms = get_permissions_for_resource("routines")
        assert "routine.read" in routine_perms
        assert "routine.write" in routine_perms
        # Should NOT include other resource permissions
        assert "submission.create" not in routine_perms

    def test_get_permissions_for_resource_empty(self) -> None:
        """Should return empty set for unknown resource type."""
        unknown_perms = get_permissions_for_resource("unknown_resource")
        assert unknown_perms == set()

    def test_get_permission_display_name(self) -> None:
        """Should return display name for known permission."""
        name = get_permission_display_name("submission.review")
        assert name == "Review Submissions"

    def test_get_permission_display_name_project_read(self) -> None:
        """Should return display name for project.read permission."""
        name = get_permission_display_name("project.read")
        assert name == "View Projects"

    def test_get_permission_display_name_fallback(self) -> None:
        """Should return permission name when not found in registry."""
        name = get_permission_display_name("unknown.permission")
        assert name == "unknown.permission"

    def test_get_permission_display_name_all_registry_entries(self) -> None:
        """All registry entries should have display names."""
        for permission_name in PERMISSION_REGISTRY:
            display_name = get_permission_display_name(permission_name)
            assert display_name != permission_name  # Should not fall back
            assert len(display_name) > 0


class TestPermissionRegistry:
    """Tests for permission registry structure."""

    def test_all_permissions_have_required_fields(self) -> None:
        """All registry entries should have display_name, description, and resource_type."""
        for permission_name, metadata in PERMISSION_REGISTRY.items():
            assert "display_name" in metadata, f"{permission_name} missing display_name"
            assert "description" in metadata, f"{permission_name} missing description"
            assert (
                "resource_type" in metadata
            ), f"{permission_name} missing resource_type"

    def test_routine_permissions_in_registry(self) -> None:
        """Routine permissions should be in registry."""
        assert "routine.read" in PERMISSION_REGISTRY
        assert "routine.write" in PERMISSION_REGISTRY

    def test_execution_permissions_in_registry(self) -> None:
        """Execution permissions should be in registry."""
        assert "execution.read.today" in PERMISSION_REGISTRY
        assert "execution.read.history" in PERMISSION_REGISTRY

    def test_submission_permissions_in_registry(self) -> None:
        """Submission permissions should be in registry."""
        assert "submission.create" in PERMISSION_REGISTRY
        assert "submission.write" in PERMISSION_REGISTRY
        assert "submission.review" in PERMISSION_REGISTRY
