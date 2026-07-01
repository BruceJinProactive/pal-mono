"""Tests for team member removal role cleanup."""

import sys
from types import ModuleType
from unittest.mock import MagicMock, call
from uuid import UUID

import pytest
from pytest_mock import MockerFixture

from db.tables.types import AccountUserStatus
from services.auth_types import UserContext, UserRole

_admin_service_stub = ModuleType("services.admin_service")
_admin_utils_stub = ModuleType("services.admin_service._utils")


def _stub_generate_password(length: int = 12) -> str:
    return "TempPass123!"


_admin_utils_stub.__dict__["generate_password"] = _stub_generate_password

_existing_admin_service = sys.modules.get("services.admin_service")
_existing_admin_utils = sys.modules.get("services.admin_service._utils")
if _existing_admin_service is None:
    sys.modules["services.admin_service"] = _admin_service_stub
if _existing_admin_utils is None:
    sys.modules["services.admin_service._utils"] = _admin_utils_stub

from services.team_service import _implementation as svc  # isort: skip  # noqa: E402

if _existing_admin_utils is None:
    del sys.modules["services.admin_service._utils"]
if _existing_admin_service is None:
    del sys.modules["services.admin_service"]

ACCOUNT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
TARGET_USER_ID = UUID("22222222-3333-4444-5555-666666666666")
ACTOR_ID = UUID("11111111-2222-3333-4444-555555555555")
PROJECT_ONE_ID = UUID("33333333-4444-5555-6666-777777777777")
PROJECT_TWO_ID = UUID("44444444-5555-6666-7777-888888888888")
ACCOUNT_NAME = "acme_test"
TARGET_EMAIL = "member@example.com"


def _context() -> UserContext:
    return UserContext(
        username=str(ACTOR_ID),
        email="owner@example.com",
        groups=[],
        display_name="Owner User",
        role=UserRole.AccountManager,
    )


def _patch_remove_repositories(mocker: MockerFixture) -> dict[str, MagicMock]:
    account = MagicMock()
    account.id = ACCOUNT_ID
    account.name = ACCOUNT_NAME
    account_repo = mocker.patch.object(svc, "AccountRepository").return_value
    account_repo.get_account.return_value = account

    invitation_repo = mocker.patch.object(svc, "UserInvitationRepository").return_value
    invitation_repo.get_pending_for_account.return_value = []

    account_user = MagicMock()
    account_user.email = TARGET_EMAIL
    account_user.user_id = TARGET_USER_ID
    account_user_repo = mocker.patch.object(svc, "AccountUserRepository").return_value
    account_user_repo.get_users_for_account.return_value = [account_user]

    role_repo = mocker.patch.object(
        svc, "ResourceRoleAssignmentRepository"
    ).return_value
    role_repo.get_roles_for_resource.return_value = ["store_member"]

    project_one = MagicMock()
    project_one.id = PROJECT_ONE_ID
    project_two = MagicMock()
    project_two.id = PROJECT_TWO_ID
    project_repo = mocker.patch.object(svc, "ProjectRepository").return_value
    project_repo.get_projects_by_account_id.return_value = [project_one, project_two]

    return {
        "account_user_repo": account_user_repo,
        "project_repo": project_repo,
        "role_repo": role_repo,
    }


def test_remove_team_member_removes_account_and_project_role_assignments(
    mocker: MockerFixture,
) -> None:
    session = MagicMock()
    repos = _patch_remove_repositories(mocker)

    svc.remove_team_member(
        session=session,
        context=_context(),
        account_name=ACCOUNT_NAME,
        user_email=TARGET_EMAIL,
    )

    repos["account_user_repo"].update_status.assert_called_once_with(
        TARGET_USER_ID, ACCOUNT_ID, AccountUserStatus.deactivated
    )
    repos["project_repo"].get_projects_by_account_id.assert_called_once_with(ACCOUNT_ID)
    assert repos["role_repo"].remove_all_roles_for_user_on_resource.call_args_list == [
        call(
            TARGET_USER_ID,
            svc.ResourceType.ACCOUNT,
            ACCOUNT_ID,
            raise_on_error=True,
        ),
        call(
            TARGET_USER_ID,
            svc.ResourceType.PROJECT,
            PROJECT_ONE_ID,
            raise_on_error=True,
        ),
        call(
            TARGET_USER_ID,
            svc.ResourceType.PROJECT,
            PROJECT_TWO_ID,
            raise_on_error=True,
        ),
    ]
    session.commit.assert_called_once_with()
    session.rollback.assert_not_called()


def test_remove_team_member_rolls_back_when_role_cleanup_fails(
    mocker: MockerFixture,
) -> None:
    session = MagicMock()
    repos = _patch_remove_repositories(mocker)
    repos["role_repo"].remove_all_roles_for_user_on_resource.side_effect = [
        1,
        RuntimeError("role cleanup failed"),
    ]

    with pytest.raises(RuntimeError, match="role cleanup failed"):
        svc.remove_team_member(
            session=session,
            context=_context(),
            account_name=ACCOUNT_NAME,
            user_email=TARGET_EMAIL,
        )

    repos["account_user_repo"].update_status.assert_called_once_with(
        TARGET_USER_ID, ACCOUNT_ID, AccountUserStatus.deactivated
    )
    session.commit.assert_not_called()
    session.rollback.assert_called_once_with()


def test_remove_team_member_protects_last_account_admin_alias(
    mocker: MockerFixture,
) -> None:
    repos = _patch_remove_repositories(mocker)
    repos["role_repo"].get_roles_for_resource.return_value = ["account_admin"]
    repos["role_repo"].count_owners_for_resource.return_value = 1

    with pytest.raises(ValueError, match="Cannot remove the last owner"):
        svc.remove_team_member(
            session=MagicMock(),
            context=_context(),
            account_name=ACCOUNT_NAME,
            user_email=TARGET_EMAIL,
        )

    repos["account_user_repo"].update_status.assert_not_called()
    repos["role_repo"].count_owners_for_resource.assert_called_once_with(
        svc.ResourceType.ACCOUNT,
        ACCOUNT_ID,
        svc.ACCOUNT_ADMIN_ROLE_ALIASES,
    )
    repos["role_repo"].remove_all_roles_for_user_on_resource.assert_not_called()
