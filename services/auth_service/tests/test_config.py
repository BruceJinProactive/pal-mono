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

    def test_owner_has_wildcard_permission(self):
        """Owner role should have wildcard (*) permission."""
        assert ROLE_PERMISSIONS["owner"] == {"*"}

    def test_manager_permissions(self):
        """Manager should have project, agent, and routine-related permissions."""
        manager_perms = ROLE_PERMISSIONS["manager"]
        assert "project.create" in manager_perms
        assert "project.read" in manager_perms
        assert "project.write" in manager_perms
        assert "project.delete" in manager_perms
        assert "agent.create" in manager_perms
        assert "agent.read" in manager_perms
        assert "agent.write" in manager_perms
        assert "routine.read" in manager_perms
        assert "routine.write" in manager_perms
        assert "submission.review" in manager_perms

    def test_viewer_permissions(self):
        """Viewer should only have read-only permissions."""
        viewer_perms = ROLE_PERMISSIONS["viewer"]
        assert "account.read" in viewer_perms
        assert "project.read" in viewer_perms
        assert "agent.read" in viewer_perms
        assert "routine.read" in viewer_perms
        assert "execution.read.today" in viewer_perms
        assert "execution.read.history" in viewer_perms
        assert "data.export" in viewer_perms
        # Should NOT have write permissions
        assert "project.write" not in viewer_perms
        assert "project.create" not in viewer_perms
        assert "agent.write" not in viewer_perms
        assert "routine.write" not in viewer_perms
        assert "submission.create" not in viewer_perms
        assert "submission.review" not in viewer_perms

    def test_staff_permissions(self):
        """Staff should have limited routine/submission permissions."""
        staff_perms = ROLE_PERMISSIONS["staff"]
        assert "project.read" in staff_perms
        assert "routine.read" in staff_perms
        assert "execution.read.today" in staff_perms
        assert "submission.create" in staff_perms
        assert "submission.write" in staff_perms

    def test_staff_missing_review_permission(self):
        """Staff should NOT have submission.review permission."""
        staff_perms = ROLE_PERMISSIONS["staff"]
        assert "submission.review" not in staff_perms

    def test_staff_missing_write_routine_permission(self):
        """Staff should NOT have routine.write permission."""
        staff_perms = ROLE_PERMISSIONS["staff"]
        assert "routine.write" not in staff_perms

    def test_staff_missing_project_write_permission(self):
        """Staff should NOT have project.write permission."""
        staff_perms = ROLE_PERMISSIONS["staff"]
        assert "project.write" not in staff_perms

    def test_staff_missing_agent_permissions(self):
        """Staff should NOT have any agent permissions."""
        staff_perms = ROLE_PERMISSIONS["staff"]
        assert "agent.create" not in staff_perms
        assert "agent.read" not in staff_perms
        assert "agent.write" not in staff_perms


class TestResourceHierarchy:
    """Tests for resource hierarchy configuration."""

    def test_resource_hierarchy_routines(self):
        """Routines should belong to projects."""
        assert RESOURCE_HIERARCHY["routines"] == "projects"

    def test_resource_hierarchy_executions(self):
        """Executions should belong to routines."""
        assert RESOURCE_HIERARCHY["executions"] == "routines"

    def test_resource_hierarchy_submissions(self):
        """Submissions should belong to executions."""
        assert RESOURCE_HIERARCHY["submissions"] == "executions"

    def test_resource_hierarchy_checklists(self):
        """Checklists should belong to projects."""
        assert RESOURCE_HIERARCHY["checklists"] == "projects"

    def test_resource_hierarchy_projects(self):
        """Projects should belong to accounts."""
        assert RESOURCE_HIERARCHY["projects"] == "accounts"

    def test_resource_hierarchy_agents(self):
        """Agents should belong to accounts."""
        assert RESOURCE_HIERARCHY["agents"] == "accounts"

    def test_resource_hierarchy_accounts(self):
        """Accounts should be top-level (no parent)."""
        assert RESOURCE_HIERARCHY["accounts"] is None


class TestHelperFunctions:
    """Tests for config helper functions."""

    def test_get_all_permissions(self):
        """Should return all permission names from registry."""
        perms = get_all_permissions()
        assert isinstance(perms, set)
        assert "project.read" in perms
        assert "project.write" in perms
        assert "routine.read" in perms
        assert "submission.review" in perms
        assert "account.read" in perms

    def test_get_all_permissions_returns_all_registry_keys(self):
        """Should return exactly the keys from PERMISSION_REGISTRY."""
        perms = get_all_permissions()
        assert perms == set(PERMISSION_REGISTRY.keys())

    def test_get_permissions_for_resource_projects(self):
        """Should filter permissions for projects resource type."""
        project_perms = get_permissions_for_resource("projects")
        assert "project.create" in project_perms
        assert "project.read" in project_perms
        assert "project.write" in project_perms
        assert "project.delete" in project_perms
        # Should NOT include other resource permissions
        assert "agent.read" not in project_perms
        assert "routine.read" not in project_perms

    def test_get_permissions_for_resource_submissions(self):
        """Should filter permissions for submissions resource type."""
        submission_perms = get_permissions_for_resource("submissions")
        assert "submission.create" in submission_perms
        assert "submission.write" in submission_perms
        assert "submission.review" in submission_perms
        # Should NOT include other resource permissions
        assert "project.read" not in submission_perms
        assert "routine.read" not in submission_perms

    def test_get_permissions_for_resource_routines(self):
        """Should filter permissions for routines resource type."""
        routine_perms = get_permissions_for_resource("routines")
        assert "routine.read" in routine_perms
        assert "routine.write" in routine_perms
        # Should NOT include other resource permissions
        assert "submission.create" not in routine_perms

    def test_get_permissions_for_resource_empty(self):
        """Should return empty set for unknown resource type."""
        unknown_perms = get_permissions_for_resource("unknown_resource")
        assert unknown_perms == set()

    def test_get_permission_display_name(self):
        """Should return display name for known permission."""
        name = get_permission_display_name("submission.review")
        assert name == "Review Submissions"

    def test_get_permission_display_name_project_read(self):
        """Should return display name for project.read permission."""
        name = get_permission_display_name("project.read")
        assert name == "View Projects"

    def test_get_permission_display_name_fallback(self):
        """Should return permission name when not found in registry."""
        name = get_permission_display_name("unknown.permission")
        assert name == "unknown.permission"

    def test_get_permission_display_name_all_registry_entries(self):
        """All registry entries should have display names."""
        for permission_name in PERMISSION_REGISTRY:
            display_name = get_permission_display_name(permission_name)
            assert display_name != permission_name  # Should not fall back
            assert len(display_name) > 0


class TestPermissionRegistry:
    """Tests for permission registry structure."""

    def test_all_permissions_have_required_fields(self):
        """All registry entries should have display_name, description, and resource_type."""
        for permission_name, metadata in PERMISSION_REGISTRY.items():
            assert "display_name" in metadata, f"{permission_name} missing display_name"
            assert "description" in metadata, f"{permission_name} missing description"
            assert (
                "resource_type" in metadata
            ), f"{permission_name} missing resource_type"

    def test_routine_permissions_in_registry(self):
        """Routine permissions should be in registry."""
        assert "routine.read" in PERMISSION_REGISTRY
        assert "routine.write" in PERMISSION_REGISTRY

    def test_execution_permissions_in_registry(self):
        """Execution permissions should be in registry."""
        assert "execution.read.today" in PERMISSION_REGISTRY
        assert "execution.read.history" in PERMISSION_REGISTRY

    def test_submission_permissions_in_registry(self):
        """Submission permissions should be in registry."""
        assert "submission.create" in PERMISSION_REGISTRY
        assert "submission.write" in PERMISSION_REGISTRY
        assert "submission.review" in PERMISSION_REGISTRY
