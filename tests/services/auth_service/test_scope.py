"""Tests for store-scope RBAC helpers."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import HTTPException
from pytest_mock import MockerFixture

from services.auth_service.dependencies import resolve_project_scope_or_raise
from services.auth_service.scope import (
    ProjectScopeForbiddenError,
    authorize_requested_project_ids,
    get_accessible_project_ids,
    resolve_project_scope,
)
from services.auth_types import UserContext, UserRole

USER_ID = UUID("11111111-2222-3333-4444-555555555555")
OTHER_USER_ID = UUID("22222222-3333-4444-5555-666666666666")
ACCOUNT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
PROJECT_ONE_ID = UUID("33333333-4444-5555-6666-777777777777")
PROJECT_TWO_ID = UUID("44444444-5555-6666-7777-888888888888")
PROJECT_THREE_ID = UUID("55555555-6666-7777-8888-999999999999")


def _project(project_id: UUID) -> MagicMock:
    project = MagicMock()
    project.id = project_id
    return project


def _assignment(user_id: UUID, project_id: UUID, role: str) -> MagicMock:
    assignment = MagicMock()
    assignment.user_id = user_id
    assignment.resource_id = project_id
    assignment.role = role
    return assignment


def _context(role: UserRole = UserRole.AccountManager) -> UserContext:
    return UserContext(
        username=str(USER_ID),
        email="user@example.com",
        groups=[],
        display_name="User",
        role=role,
    )


def _patch_scope_repositories(mocker: MockerFixture) -> dict[str, MagicMock]:
    account_user_repo = mocker.patch(
        "services.auth_service.scope.AccountUserRepository"
    ).return_value
    account_user_repo.is_member.return_value = True

    project_repo = mocker.patch(
        "services.auth_service.scope.ProjectRepository"
    ).return_value
    project_repo.get_projects_by_account_id.return_value = [
        _project(PROJECT_ONE_ID),
        _project(PROJECT_TWO_ID),
        _project(PROJECT_THREE_ID),
    ]

    role_repo = mocker.patch(
        "services.auth_service.scope.ResourceRoleAssignmentRepository"
    ).return_value
    role_repo.get_roles_for_resource.return_value = []
    role_repo.get_assignments_for_resources.return_value = []

    return {
        "account_user_repo": account_user_repo,
        "project_repo": project_repo,
        "role_repo": role_repo,
    }


def test_get_accessible_project_ids_account_admin_gets_all_projects(
    mocker: MockerFixture,
) -> None:
    repos = _patch_scope_repositories(mocker)
    repos["role_repo"].get_roles_for_resource.return_value = ["account_admin"]

    result = get_accessible_project_ids(
        session=MagicMock(),
        user_id=USER_ID,
        account_id=ACCOUNT_ID,
        permission="conversation.read",
    )

    assert result == frozenset({PROJECT_ONE_ID, PROJECT_TWO_ID, PROJECT_THREE_ID})
    repos["role_repo"].get_assignments_for_resources.assert_not_called()


def test_get_accessible_project_ids_internal_admin_gets_account_projects(
    mocker: MockerFixture,
) -> None:
    repos = _patch_scope_repositories(mocker)

    result = get_accessible_project_ids(
        session=MagicMock(),
        user_id=USER_ID,
        account_id=ACCOUNT_ID,
        permission="anything.custom",
        user_role=UserRole.Admin.value,
    )

    assert result == frozenset({PROJECT_ONE_ID, PROJECT_TWO_ID, PROJECT_THREE_ID})
    repos["account_user_repo"].is_member.assert_not_called()
    repos["role_repo"].get_roles_for_resource.assert_not_called()


def test_get_accessible_project_ids_filters_project_roles_by_permission(
    mocker: MockerFixture,
) -> None:
    repos = _patch_scope_repositories(mocker)
    repos["role_repo"].get_assignments_for_resources.return_value = [
        _assignment(USER_ID, PROJECT_ONE_ID, "store_owner"),
        _assignment(USER_ID, PROJECT_TWO_ID, "store_member"),
        _assignment(OTHER_USER_ID, PROJECT_THREE_ID, "store_owner"),
    ]

    result = get_accessible_project_ids(
        session=MagicMock(),
        user_id=USER_ID,
        account_id=ACCOUNT_ID,
        permission="project.write",
    )

    assert result == frozenset({PROJECT_ONE_ID})


def test_get_accessible_project_ids_includes_member_read_scope(
    mocker: MockerFixture,
) -> None:
    repos = _patch_scope_repositories(mocker)
    repos["role_repo"].get_assignments_for_resources.return_value = [
        _assignment(USER_ID, PROJECT_ONE_ID, "store_owner"),
        _assignment(USER_ID, PROJECT_TWO_ID, "store_member"),
        _assignment(USER_ID, PROJECT_THREE_ID, "staff"),
    ]

    result = get_accessible_project_ids(
        session=MagicMock(),
        user_id=USER_ID,
        account_id=ACCOUNT_ID,
        permission="project.read",
    )

    assert result == frozenset({PROJECT_ONE_ID, PROJECT_TWO_ID})


def test_get_accessible_project_ids_legacy_manager_account_role_is_not_account_wide(
    mocker: MockerFixture,
) -> None:
    repos = _patch_scope_repositories(mocker)
    repos["role_repo"].get_roles_for_resource.return_value = ["manager"]
    repos["role_repo"].get_assignments_for_resources.return_value = [
        _assignment(USER_ID, PROJECT_TWO_ID, "manager"),
    ]

    result = get_accessible_project_ids(
        session=MagicMock(),
        user_id=USER_ID,
        account_id=ACCOUNT_ID,
        permission="project.read",
    )

    assert result == frozenset({PROJECT_TWO_ID})


def test_get_accessible_project_ids_requires_active_account_membership(
    mocker: MockerFixture,
) -> None:
    repos = _patch_scope_repositories(mocker)
    repos["account_user_repo"].is_member.return_value = False

    result = get_accessible_project_ids(
        session=MagicMock(),
        user_id=USER_ID,
        account_id=ACCOUNT_ID,
        permission="project.read",
    )

    assert result == frozenset()
    repos["role_repo"].get_roles_for_resource.assert_not_called()
    repos["project_repo"].get_projects_by_account_id.assert_not_called()


def test_authorize_requested_project_ids_defaults_to_all_accessible() -> None:
    result = authorize_requested_project_ids(
        requested_project_ids=None,
        accessible_project_ids={PROJECT_TWO_ID, PROJECT_ONE_ID},
    )

    assert result == [PROJECT_ONE_ID, PROJECT_TWO_ID]


def test_authorize_requested_project_ids_preserves_order_and_dedupes() -> None:
    result = authorize_requested_project_ids(
        requested_project_ids=[PROJECT_TWO_ID, PROJECT_ONE_ID, PROJECT_TWO_ID],
        accessible_project_ids={PROJECT_ONE_ID, PROJECT_TWO_ID},
    )

    assert result == [PROJECT_TWO_ID, PROJECT_ONE_ID]


def test_authorize_requested_project_ids_rejects_out_of_scope_project() -> None:
    with pytest.raises(ProjectScopeForbiddenError) as exc_info:
        authorize_requested_project_ids(
            requested_project_ids=[PROJECT_ONE_ID, PROJECT_THREE_ID],
            accessible_project_ids={PROJECT_ONE_ID, PROJECT_TWO_ID},
        )

    assert exc_info.value.denied_project_ids == frozenset({PROJECT_THREE_ID})
    assert exc_info.value.accessible_project_ids == frozenset(
        {PROJECT_ONE_ID, PROJECT_TWO_ID}
    )


def test_resolve_project_scope_combines_accessible_and_requested(
    mocker: MockerFixture,
) -> None:
    repos = _patch_scope_repositories(mocker)
    repos["role_repo"].get_assignments_for_resources.return_value = [
        _assignment(USER_ID, PROJECT_ONE_ID, "store_owner"),
        _assignment(USER_ID, PROJECT_TWO_ID, "store_member"),
    ]

    result = resolve_project_scope(
        session=MagicMock(),
        user_id=USER_ID,
        account_id=ACCOUNT_ID,
        permission="project.read",
        requested_project_ids=[PROJECT_TWO_ID],
    )

    assert result == [PROJECT_TWO_ID]


def test_resolve_project_scope_or_raise_translates_scope_denial_to_403(
    mocker: MockerFixture,
) -> None:
    mocker.patch(
        "services.auth_service.dependencies.get_accessible_project_ids",
        return_value=frozenset({PROJECT_ONE_ID}),
    )

    with pytest.raises(HTTPException) as exc_info:
        resolve_project_scope_or_raise(
            session=MagicMock(),
            current_user=_context(),
            account_id=ACCOUNT_ID,
            permission="project.read",
            requested_project_ids=[PROJECT_TWO_ID],
        )

    assert exc_info.value.status_code == 403
