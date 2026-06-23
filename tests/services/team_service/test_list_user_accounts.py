"""Tests for multi-account access list filtering."""

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from types import ModuleType
from unittest.mock import MagicMock
from uuid import UUID

from pytest_mock import MockerFixture

from db.tables.types import AccountUserStatus
from services.auth_types import UserContext, UserRole

_admin_service_stub = ModuleType("services.admin_service")
_admin_utils_stub = ModuleType("services.admin_service._utils")


def _stub_generate_password(length: int = 12) -> str:
    return "TempPass123!"


setattr(_admin_utils_stub, "generate_password", _stub_generate_password)

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

USER_ID = UUID("54b83458-0001-701e-632e-876468aefda0")
VALID_ACCOUNT_ID = UUID("40d3c0d2-f7f1-4b8c-a75a-94b49b5f75eb")
STALE_ACCOUNT_ID = UUID("de156ba2-37ab-4e9d-a743-07bba73bd7fa")
ADDED_AT = datetime(2026, 6, 12, tzinfo=timezone.utc)


@dataclass
class AccountStub:
    id: UUID
    name: str
    display_name: str | None = None


@dataclass
class AccountMembershipStub:
    account_id: UUID
    added_at: datetime = ADDED_AT


def _account(account_id: UUID, name: str) -> AccountStub:
    return AccountStub(id=account_id, name=name, display_name=name.replace("-", " "))


def _context(role: UserRole = UserRole.AccountManager) -> UserContext:
    return UserContext(
        username=str(USER_ID),
        email="user@example.com",
        groups=[],
        display_name="Test User",
        role=role,
    )


def _patch_account_access_repositories(
    mocker: MockerFixture,
) -> dict[str, MagicMock]:
    memberships = [
        AccountMembershipStub(account_id=VALID_ACCOUNT_ID),
        AccountMembershipStub(account_id=STALE_ACCOUNT_ID),
    ]
    accounts = {
        VALID_ACCOUNT_ID: _account(VALID_ACCOUNT_ID, "peppertavern"),
        STALE_ACCOUNT_ID: _account(STALE_ACCOUNT_ID, "mikes_deli"),
    }

    account_user_repo = mocker.patch.object(svc, "AccountUserRepository").return_value
    account_user_repo.get_accounts_for_user.return_value = memberships

    account_repo = mocker.patch.object(svc, "AccountRepository").return_value
    account_repo.get_account_by_id.side_effect = lambda account_id: accounts.get(
        account_id
    )

    role_repo = mocker.patch.object(
        svc, "ResourceRoleAssignmentRepository"
    ).return_value
    role_repo.get_roles_for_resource.side_effect = (
        lambda _user_id, resource_type, resource_id: (
            ["owner"]
            if resource_type == svc.ResourceType.ACCOUNT
            and resource_id == VALID_ACCOUNT_ID
            else []
        )
    )

    project_repo = mocker.patch.object(svc, "ProjectRepository").return_value
    project_repo.get_projects_by_account_id.return_value = []

    return {
        "account_user_repo": account_user_repo,
        "project_repo": project_repo,
    }


def test_list_user_accounts_excludes_active_membership_without_role(
    mocker: MockerFixture,
) -> None:
    repos = _patch_account_access_repositories(mocker)

    accounts = svc.list_user_accounts(session=MagicMock(), context=_context())

    assert [account.name for account, _role, _last_accessed in accounts] == [
        "peppertavern"
    ]
    assert accounts[0][1] == "owner"
    repos["account_user_repo"].get_accounts_for_user.assert_called_once_with(
        USER_ID, status=AccountUserStatus.active
    )


def test_list_user_accounts_by_email_excludes_active_membership_without_role(
    mocker: MockerFixture,
) -> None:
    repos = _patch_account_access_repositories(mocker)
    cognito_client = mocker.patch.object(svc.boto3, "client").return_value
    cognito_client.admin_get_user.return_value = {
        "UserAttributes": [{"Name": "sub", "Value": str(USER_ID)}]
    }

    accounts = svc.list_user_accounts_by_email(
        context=_context(role=UserRole.Admin),
        session=MagicMock(),
        user_email="user@example.com",
    )

    assert [account.name for _user_id, account, _role, _last_accessed in accounts] == [
        "peppertavern"
    ]
    assert accounts[0][2] == "owner"
    repos["account_user_repo"].get_accounts_for_user.assert_called_once_with(
        USER_ID, status=AccountUserStatus.active
    )
