"""Integration tests for Store Owner RBAC and project isolation.

Tests that Store Owner role properly isolates access between projects
and returns 404 for unauthorized project access.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.repositories.resource_role_assignment_repository import ResourceType
from db.tables import Project, ResourceRoleAssignment
from services.auth_service.authorization import check_permission
from tests.factories import (
    make_account_user,
    make_project,
    make_role_assignment,
    make_user,
    make_world,
)


@pytest.mark.integration
class TestStoreOwnerRoleAssignment:
    """Tests for Store Owner role assignment and persistence."""

    def test_store_owner_role_persisted(self, db_session: Session) -> None:
        """Store Owner role assignment is created and queryable."""
        world = make_world(db_session)

        assignment = make_role_assignment(
            db_session,
            user_id=world.user.id,
            resource_type=ResourceType.PROJECT.value,
            resource_id=world.project.id,
            role="store_owner",
        )

        result = db_session.execute(
            select(ResourceRoleAssignment).where(
                ResourceRoleAssignment.id == assignment.id
            )
        ).scalar_one_or_none()

        assert result is not None
        assert result.role == "store_owner"
        assert result.resource_type == ResourceType.PROJECT.value
        assert result.resource_id == world.project.id

    def test_multiple_store_owners_different_projects(
        self, db_session: Session
    ) -> None:
        """Multiple Store Owners can be assigned to different projects."""
        world = make_world(db_session)

        # Create two Store Owners
        store_owner_1 = make_user(db_session, account_id=world.account.id)
        store_owner_2 = make_user(db_session, account_id=world.account.id)

        # Create two projects
        project_1 = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=world.agent.id,
            name="Downtown Store",
        )
        project_2 = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=world.agent.id,
            name="Uptown Store",
        )

        # Assign Store Owner 1 to Project 1
        make_role_assignment(
            db_session,
            user_id=store_owner_1.id,
            resource_type=ResourceType.PROJECT.value,
            resource_id=project_1.id,
            role="store_owner",
        )

        # Assign Store Owner 2 to Project 2
        make_role_assignment(
            db_session,
            user_id=store_owner_2.id,
            resource_type=ResourceType.PROJECT.value,
            resource_id=project_2.id,
            role="store_owner",
        )

        # Verify assignments
        assignments_project_1 = (
            db_session.execute(
                select(ResourceRoleAssignment).where(
                    ResourceRoleAssignment.resource_id == project_1.id,
                    ResourceRoleAssignment.resource_type == ResourceType.PROJECT.value,
                )
            )
            .scalars()
            .all()
        )

        assignments_project_2 = (
            db_session.execute(
                select(ResourceRoleAssignment).where(
                    ResourceRoleAssignment.resource_id == project_2.id,
                    ResourceRoleAssignment.resource_type == ResourceType.PROJECT.value,
                )
            )
            .scalars()
            .all()
        )

        assert len(assignments_project_1) == 1
        assert assignments_project_1[0].user_id == store_owner_1.id
        assert assignments_project_1[0].role == "store_owner"

        assert len(assignments_project_2) == 1
        assert assignments_project_2[0].user_id == store_owner_2.id
        assert assignments_project_2[0].role == "store_owner"

    def test_store_owner_assigned_to_multiple_projects(
        self, db_session: Session
    ) -> None:
        """Single Store Owner can be assigned to multiple projects."""
        world = make_world(db_session)

        store_owner = make_user(db_session, account_id=world.account.id)
        make_account_user(
            db_session, account_id=world.account.id, user_id=store_owner.id
        )

        # Create two projects
        project_1 = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=world.agent.id,
            name="Store A",
        )
        project_2 = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=world.agent.id,
            name="Store B",
        )

        # Assign Store Owner to both projects
        make_role_assignment(
            db_session,
            user_id=store_owner.id,
            resource_type=ResourceType.PROJECT.value,
            resource_id=project_1.id,
            role="store_owner",
        )
        make_role_assignment(
            db_session,
            user_id=store_owner.id,
            resource_type=ResourceType.PROJECT.value,
            resource_id=project_2.id,
            role="store_owner",
        )

        # Verify assignments
        assignments = (
            db_session.execute(
                select(ResourceRoleAssignment).where(
                    ResourceRoleAssignment.user_id == store_owner.id,
                    ResourceRoleAssignment.role == "store_owner",
                )
            )
            .scalars()
            .all()
        )

        assert len(assignments) == 2
        assigned_project_ids = {a.resource_id for a in assignments}
        assert project_1.id in assigned_project_ids
        assert project_2.id in assigned_project_ids


@pytest.mark.integration
class TestStoreOwnerProjectIsolation:
    """Tests for Store Owner access isolation between projects."""

    def test_store_owner_can_access_assigned_project(self, db_session: Session) -> None:
        """Store Owner can access their assigned project."""
        world = make_world(db_session)

        store_owner = make_user(db_session, account_id=world.account.id)
        make_account_user(
            db_session, account_id=world.account.id, user_id=store_owner.id
        )

        make_role_assignment(
            db_session,
            user_id=store_owner.id,
            resource_type=ResourceType.PROJECT.value,
            resource_id=world.project.id,
            role="store_owner",
        )

        result = check_permission(
            user_id=store_owner.id,
            resource_id=f"projects/{world.project.id}",
            permission_name="project.read",
            session=db_session,
            check_hierarchy=False,
        )

        assert result is True

    def test_store_owner_cannot_access_unassigned_project(
        self, db_session: Session
    ) -> None:
        """Store Owner CANNOT access projects they're not assigned to."""
        world = make_world(db_session)

        store_owner = make_user(db_session, account_id=world.account.id)
        make_account_user(
            db_session, account_id=world.account.id, user_id=store_owner.id
        )

        # Create two projects
        project_1 = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=world.agent.id,
            name="Assigned Store",
        )
        project_2 = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=world.agent.id,
            name="Unassigned Store",
        )

        # Assign Store Owner only to Project 1
        make_role_assignment(
            db_session,
            user_id=store_owner.id,
            resource_type=ResourceType.PROJECT.value,
            resource_id=project_1.id,
            role="store_owner",
        )

        # Verify Store Owner can access Project 1
        result_assigned = check_permission(
            user_id=store_owner.id,
            resource_id=f"projects/{project_1.id}",
            permission_name="project.read",
            session=db_session,
            check_hierarchy=True,
        )
        assert result_assigned is True

        # Verify Store Owner CANNOT access Project 2
        result_unassigned = check_permission(
            user_id=store_owner.id,
            resource_id=f"projects/{project_2.id}",
            permission_name="project.read",
            session=db_session,
            check_hierarchy=True,
        )
        assert result_unassigned is False

    def test_cross_project_isolation_between_store_owners(
        self, db_session: Session
    ) -> None:
        """Store Owners cannot access each other's projects."""
        world = make_world(db_session)

        # Create two Store Owners
        store_owner_1 = make_user(db_session, account_id=world.account.id)
        store_owner_2 = make_user(db_session, account_id=world.account.id)

        make_account_user(
            db_session, account_id=world.account.id, user_id=store_owner_1.id
        )
        make_account_user(
            db_session, account_id=world.account.id, user_id=store_owner_2.id
        )

        # Create two projects
        project_1 = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=world.agent.id,
            name="Store Owner 1 Store",
        )
        project_2 = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=world.agent.id,
            name="Store Owner 2 Store",
        )

        # Assign Store Owner 1 to Project 1
        make_role_assignment(
            db_session,
            user_id=store_owner_1.id,
            resource_type=ResourceType.PROJECT.value,
            resource_id=project_1.id,
            role="store_owner",
        )

        # Assign Store Owner 2 to Project 2
        make_role_assignment(
            db_session,
            user_id=store_owner_2.id,
            resource_type=ResourceType.PROJECT.value,
            resource_id=project_2.id,
            role="store_owner",
        )

        # Store Owner 1 can access Project 1
        assert (
            check_permission(
                user_id=store_owner_1.id,
                resource_id=f"projects/{project_1.id}",
                permission_name="project.read",
                session=db_session,
                check_hierarchy=True,
            )
            is True
        )

        # Store Owner 1 CANNOT access Project 2
        assert (
            check_permission(
                user_id=store_owner_1.id,
                resource_id=f"projects/{project_2.id}",
                permission_name="project.read",
                session=db_session,
                check_hierarchy=True,
            )
            is False
        )

        # Store Owner 2 can access Project 2
        assert (
            check_permission(
                user_id=store_owner_2.id,
                resource_id=f"projects/{project_2.id}",
                permission_name="project.read",
                session=db_session,
                check_hierarchy=True,
            )
            is True
        )

        # Store Owner 2 CANNOT access Project 1
        assert (
            check_permission(
                user_id=store_owner_2.id,
                resource_id=f"projects/{project_1.id}",
                permission_name="project.read",
                session=db_session,
                check_hierarchy=True,
            )
            is False
        )


@pytest.mark.integration
class TestStoreOwnerVsOtherRoles:
    """Tests for Store Owner role compared to other roles."""

    def test_account_owner_can_access_all_projects(self, db_session: Session) -> None:
        """Account Owner maintains full access to all projects."""
        world = make_world(db_session)

        # Assign account owner role
        make_role_assignment(
            db_session,
            user_id=world.user.id,
            resource_type=ResourceType.ACCOUNT.value,
            resource_id=world.account.id,
            role="owner",
        )

        # Create additional project
        project_2 = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=world.agent.id,
            name="Another Store",
        )

        # Account Owner can access both projects
        result_project_1 = check_permission(
            user_id=world.user.id,
            resource_id=f"projects/{world.project.id}",
            permission_name="project.write",
            session=db_session,
            check_hierarchy=True,
        )
        assert result_project_1 is True

        result_project_2 = check_permission(
            user_id=world.user.id,
            resource_id=f"projects/{project_2.id}",
            permission_name="project.write",
            session=db_session,
            check_hierarchy=True,
        )
        assert result_project_2 is True

    def test_store_owner_can_write_project_but_not_agents(
        self, db_session: Session
    ) -> None:
        """Store Owner can write project settings but cannot edit agents."""
        world = make_world(db_session)

        store_owner = make_user(db_session, account_id=world.account.id)
        staff_user = make_user(db_session, account_id=world.account.id)

        make_account_user(
            db_session, account_id=world.account.id, user_id=store_owner.id
        )
        make_account_user(
            db_session, account_id=world.account.id, user_id=staff_user.id
        )

        # Assign roles to same project
        make_role_assignment(
            db_session,
            user_id=store_owner.id,
            resource_type=ResourceType.PROJECT.value,
            resource_id=world.project.id,
            role="store_owner",
        )
        make_role_assignment(
            db_session,
            user_id=staff_user.id,
            resource_type=ResourceType.PROJECT.value,
            resource_id=world.project.id,
            role="staff",
        )

        # Store Owner can write to project
        assert (
            check_permission(
                user_id=store_owner.id,
                resource_id=f"projects/{world.project.id}",
                permission_name="project.write",
                session=db_session,
                check_hierarchy=False,
            )
            is True
        )

        # Staff cannot write to project
        assert (
            check_permission(
                user_id=staff_user.id,
                resource_id=f"projects/{world.project.id}",
                permission_name="project.write",
                session=db_session,
                check_hierarchy=False,
            )
            is False
        )

        # Store Owner cannot create agents
        assert (
            check_permission(
                user_id=store_owner.id,
                resource_id=f"projects/{world.project.id}",
                permission_name="agent.create",
                session=db_session,
                check_hierarchy=False,
            )
            is False
        )

        # Staff cannot create agents
        assert (
            check_permission(
                user_id=staff_user.id,
                resource_id=f"projects/{world.project.id}",
                permission_name="agent.create",
                session=db_session,
                check_hierarchy=False,
            )
            is False
        )

    def test_store_owner_cannot_access_account_level_features(
        self, db_session: Session
    ) -> None:
        """Store Owner should NOT have account-level permissions."""
        world = make_world(db_session)

        store_owner = make_user(db_session, account_id=world.account.id)
        make_account_user(
            db_session, account_id=world.account.id, user_id=store_owner.id
        )

        make_role_assignment(
            db_session,
            user_id=store_owner.id,
            resource_type=ResourceType.PROJECT.value,
            resource_id=world.project.id,
            role="store_owner",
        )

        # Store Owner cannot modify account settings
        assert (
            check_permission(
                user_id=store_owner.id,
                resource_id=f"accounts/{world.account.id}",
                permission_name="account.write",
                session=db_session,
                check_hierarchy=True,
            )
            is False
        )

        # Store Owner cannot manage billing
        assert (
            check_permission(
                user_id=store_owner.id,
                resource_id=f"accounts/{world.account.id}",
                permission_name="account.billing.write",
                session=db_session,
                check_hierarchy=True,
            )
            is False
        )

        # Store Owner cannot manage team
        assert (
            check_permission(
                user_id=store_owner.id,
                resource_id=f"accounts/{world.account.id}",
                permission_name="account.team_manage",
                session=db_session,
                check_hierarchy=True,
            )
            is False
        )


@pytest.mark.integration
class TestStoreOwnerDBIntegrity:
    """Tests for database integrity with Store Owner role assignments."""

    def test_no_db_changes_after_permission_denied(self, db_session: Session) -> None:
        """Database state should not change when Store Owner is denied access.

        This verifies that permission denial is atomic.
        """
        world = make_world(db_session)

        store_owner = make_user(db_session, account_id=world.account.id)
        make_account_user(
            db_session, account_id=world.account.id, user_id=store_owner.id
        )

        # Create unassigned project
        unassigned_project = make_project(
            db_session,
            account_id=world.account.id,
            agent_id=world.agent.id,
            name="Unassigned Store",
        )

        # Snapshot DB state before denied access attempt
        project_count_before = (
            db_session.execute(select(Project)).scalars().all().__len__()
        )
        assignment_count_before = (
            db_session.execute(select(ResourceRoleAssignment)).scalars().all().__len__()
        )

        # Attempt to access unassigned project (should be denied)
        result = check_permission(
            user_id=store_owner.id,
            resource_id=f"projects/{unassigned_project.id}",
            permission_name="project.read",
            session=db_session,
            check_hierarchy=True,
        )
        assert result is False

        # Verify DB state unchanged
        project_count_after = (
            db_session.execute(select(Project)).scalars().all().__len__()
        )
        assignment_count_after = (
            db_session.execute(select(ResourceRoleAssignment)).scalars().all().__len__()
        )

        assert project_count_before == project_count_after
        assert assignment_count_before == assignment_count_after
