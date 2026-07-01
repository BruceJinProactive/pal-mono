"""Tests for Admin Console team request schemas."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from api.schemas.admin.team import InviteTeamMemberRequest, UpdateTeamMemberRequest

PROJECT_ID = UUID("22222222-3333-4444-5555-666666666666")


def test_invite_account_admin_omits_project_ids() -> None:
    request = InviteTeamMemberRequest.model_validate(
        {
            "email": "admin@example.com",
            "account_role": "account_admin",
        }
    )

    assert request.project_ids is None


def test_invite_account_admin_rejects_project_ids() -> None:
    with pytest.raises(ValidationError, match="account_admin invitations must omit"):
        InviteTeamMemberRequest.model_validate(
            {
                "email": "admin@example.com",
                "account_role": "account_admin",
                "project_ids": [PROJECT_ID],
            }
        )


@pytest.mark.parametrize("role", ["store_owner", "store_member"])
def test_invite_store_roles_require_project_ids(role: str) -> None:
    with pytest.raises(ValidationError, match="require project_ids"):
        InviteTeamMemberRequest.model_validate(
            {"email": "store@example.com", "account_role": role}
        )


@pytest.mark.parametrize("role", ["store_owner", "store_member"])
def test_invite_store_roles_reject_empty_project_ids(role: str) -> None:
    with pytest.raises(ValidationError, match="require project_ids"):
        InviteTeamMemberRequest.model_validate(
            {
                "email": "store@example.com",
                "account_role": role,
                "project_ids": [],
            }
        )


@pytest.mark.parametrize("role", ["store_owner", "store_member"])
def test_invite_store_roles_accept_project_ids(role: str) -> None:
    request = InviteTeamMemberRequest.model_validate(
        {
            "email": "store@example.com",
            "account_role": role,
            "project_ids": [PROJECT_ID],
        }
    )

    assert request.project_ids == [PROJECT_ID]


def test_update_team_member_accepts_account_admin_only() -> None:
    request = UpdateTeamMemberRequest.model_validate({"account_role": "account_admin"})

    assert request.account_role.value == "account_admin"


@pytest.mark.parametrize("role", ["store_owner", "store_member"])
def test_update_team_member_rejects_store_scoped_roles(role: str) -> None:
    with pytest.raises(ValidationError):
        UpdateTeamMemberRequest.model_validate({"account_role": role})
